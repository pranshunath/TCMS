"""Static AST test scanner for TCMS.

Extracts test_case_id metadata from pytest test source files using Python AST.
Never imports modules, executes code, connects to databases, or runs pytest.
"""
import ast
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

CASE_ID_REGEX = re.compile(r"(TC_|GRPC_)[A-Za-z0-9_.-]+")


class TestFunctionVisitor(ast.NodeVisitor):
    def __init__(self, filepath: Path, rel_path: str):
        self.filepath = filepath
        self.rel_path = rel_path
        self.found_tests: List[Dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._inspect_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._inspect_function(node)
        self.generic_visit(node)

    def _inspect_function(self, node: ast.AST) -> None:
        func_name = getattr(node, "name", "")
        if not func_name.startswith("test_") and not func_name.endswith("_test"):
            return

        # Check skipped decorators
        is_skipped = False
        for dec in getattr(node, "decorator_list", []):
            dec_str = self._ast_to_str(dec)
            if "skip" in dec_str:
                is_skipped = True

        # Extract docstring / title
        docstring = ast.get_docstring(node)
        title = ""
        if docstring:
            title = docstring.strip().split("\n")[0].strip()
        if not title:
            title = func_name.replace("_", " ").capitalize()

        # Infer area and test_type
        test_type = "api"
        lower_path = self.rel_path.lower()
        if "grpc" in lower_path or "grpc" in func_name.lower():
            test_type = "grpc"
        elif "ui" in lower_path or "playwright" in lower_path or "selenium" in lower_path:
            test_type = "ui"

        parts = Path(self.rel_path).parts
        area = "general"
        for p in parts:
            if p not in ("tests", "test", "src") and not p.endswith(".py"):
                area = p
                break

        # Extract IDs
        extracted_ids = self._extract_case_ids(node)

        self.found_tests.append({
            "func_name": func_name,
            "line": getattr(node, "lineno", 1),
            "source_path": self.rel_path.replace("\\", "/"),
            "source_symbol": func_name,
            "title": title,
            "area": area,
            "test_type": test_type,
            "is_skipped": is_skipped,
            "extracted_ids": extracted_ids,
        })

    def _extract_case_ids(self, func_node: ast.AST) -> List[str]:
        ids: List[str] = []

        # 1. Inspect decorators for @pytest.mark.parametrize
        for dec in getattr(func_node, "decorator_list", []):
            if isinstance(dec, ast.Call):
                func_str = self._ast_to_str(dec.func)
                if "parametrize" in func_str and len(dec.args) >= 2:
                    argnames_node = dec.args[0]
                    argvalues_node = dec.args[1]

                    argnames = self._parse_argnames(argnames_node)
                    extracted = self._parse_argvalues(argnames, argvalues_node)
                    ids.extend(extracted)

        # 2. Check docstring if no IDs found from parametrize
        if not ids:
            docstring = ast.get_docstring(func_node) or ""
            matches = CASE_ID_REGEX.findall(docstring)
            if matches:
                ids.extend(matches)

        # 3. Check function name if it contains a case id
        if not ids:
            matches = CASE_ID_REGEX.findall(func_node.name)
            if matches:
                ids.extend(matches)

        return ids

    def _parse_argnames(self, node: ast.AST) -> List[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [name.strip() for name in node.value.split(",") if name.strip()]
        if isinstance(node, (ast.List, ast.Tuple)):
            res = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    res.append(elt.value.strip())
            return res
        return []

    def _parse_argvalues(self, argnames: List[str], node: ast.AST) -> List[str]:
        ids: List[str] = []

        # Check for with_test_case_ids(ids, rows) helper
        if isinstance(node, ast.Call):
            call_name = self._ast_to_str(node.func)
            if "with_test_case_ids" in call_name and node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, (ast.List, ast.Tuple)):
                    for elt in first_arg.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            ids.append(elt.value.strip())
                return ids

        # If test_case_id is in argnames
        if "test_case_id" in argnames:
            idx = argnames.index("test_case_id")
            if isinstance(node, (ast.List, ast.Tuple)):
                for row in node.elts:
                    if isinstance(row, (ast.List, ast.Tuple)) and len(row.elts) > idx:
                        val_node = row.elts[idx]
                        if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                            ids.append(val_node.value.strip())
                    elif isinstance(row, ast.Constant) and isinstance(row.value, str) and len(argnames) == 1:
                        ids.append(row.value.strip())

        # If description in argnames, look for (TC_|GRPC_)\S+ regex
        if "description" in argnames:
            idx = argnames.index("description")
            if isinstance(node, (ast.List, ast.Tuple)):
                for row in node.elts:
                    if isinstance(row, (ast.List, ast.Tuple)) and len(row.elts) > idx:
                        val_node = row.elts[idx]
                        if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                            m = CASE_ID_REGEX.search(val_node.value)
                            if m:
                                ids.append(m.group(0))

        return ids

    def _ast_to_str(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._ast_to_str(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return self._ast_to_str(node.func)
        return ""


def scan_repository(repo_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Statically scans Python test files in repo_path and categorizes IDs."""
    test_files = []
    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")):
                test_files.append(Path(root) / f)

    all_tests: List[Dict[str, Any]] = []
    for tf in test_files:
        try:
            rel = str(tf.relative_to(repo_path))
            content = tf.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(tf))
            visitor = TestFunctionVisitor(tf, rel)
            visitor.visit(tree)
            all_tests.extend(visitor.found_tests)
        except Exception:
            # Skip unparseable files without crashing
            continue

    # Map ID -> occurrences
    id_occurrences: Dict[str, List[Dict[str, Any]]] = {}
    missing_id_tests: List[Dict[str, Any]] = []

    for t in all_tests:
        if not t["extracted_ids"]:
            missing_id_tests.append({
                "source_path": t["source_path"],
                "source_symbol": t["source_symbol"],
                "line": t["line"],
            })
        else:
            for cid in t["extracted_ids"]:
                if cid not in id_occurrences:
                    id_occurrences[cid] = []
                id_occurrences[cid].append(t)

    # Detect prefix / substring unsafe IDs
    all_cids = sorted(id_occurrences.keys(), key=len)
    substring_unsafe_ids: Set[str] = set()
    for i, cid_short in enumerate(all_cids):
        for cid_long in all_cids[i + 1:]:
            if cid_long.startswith(cid_short) and cid_long != cid_short:
                substring_unsafe_ids.add(cid_short)
                break

    ambiguous_ids: List[str] = []
    shared_ids: List[str] = []
    unique_ids: List[str] = []

    cases: List[Dict[str, Any]] = []

    for cid, occurrences in sorted(id_occurrences.items()):
        # Check if occurrences are across multiple different functions/symbols
        symbols = {(occ["source_path"], occ["source_symbol"]) for occ in occurrences}
        if len(symbols) > 1:
            id_status = "ambiguous"
            ambiguous_ids.append(cid)
        elif len(occurrences) > 1:
            id_status = "shared"
            shared_ids.append(cid)
        else:
            id_status = "unique"
            unique_ids.append(cid)

        is_sub_unsafe = cid in substring_unsafe_ids
        primary = occurrences[0]

        cases.append({
            "case_id": cid,
            "platform": "rewards",
            "test_type": primary["test_type"],
            "area": primary["area"],
            "source_path": primary["source_path"],
            "source_symbol": primary["source_symbol"],
            "title": primary["title"],
            "is_skipped": primary["is_skipped"],
            "id_status": id_status,
            "substring_unsafe": is_sub_unsafe,
            "occurrences": [
                {
                    "source_path": occ["source_path"],
                    "source_symbol": occ["source_symbol"],
                    "line": occ["line"],
                }
                for occ in occurrences
            ],
        })

    hygiene = {
        "total_scanned_tests": len(all_tests),
        "total_found_ids": len(id_occurrences),
        "unique_ids_count": len(unique_ids),
        "shared_ids_count": len(shared_ids),
        "ambiguous_ids_count": len(ambiguous_ids),
        "substring_unsafe_ids_count": len(substring_unsafe_ids),
        "missing_ids_count": len(missing_id_tests),
        "ambiguous_ids": ambiguous_ids,
        "shared_ids": shared_ids,
        "substring_unsafe_ids": sorted(list(substring_unsafe_ids)),
        "missing_id_tests": missing_id_tests,
    }

    return cases, hygiene


def get_git_info(repo_path: Path) -> Tuple[str, str]:
    """Extracts git commit and remote if available, without executing unsafe commands."""
    commit = "unknown"
    remote = "local"
    try:
        git_dir = repo_path / ".git"
        if git_dir.exists():
            head_file = git_dir / "HEAD"
            if head_file.exists():
                head_content = head_file.read_text().strip()
                if head_content.startswith("ref:"):
                    ref_path = git_dir / head_content.split(" ")[1]
                    if ref_path.exists():
                        commit = ref_path.read_text().strip()[:8]
                else:
                    commit = head_content[:8]
    except Exception:
        pass
    return str(repo_path), commit


def main():
    parser = argparse.ArgumentParser(description="Static TCMS Scanner for Rewards test suite")
    parser.add_argument("--repo", required=True, help="Path to repository to scan")
    parser.add_argument("--out", default="cases.json", help="Path to output JSON file")
    parser.add_argument("--hygiene-csv", default=None, help="Optional path to output hygiene CSV report")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        raise SystemExit(f"Error: Repository path '{repo_path}' does not exist")

    repo_name, commit = get_git_info(repo_path)
    scanned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cases, hygiene = scan_repository(repo_path)

    output_data = {
        "source": {
            "repo": repo_name,
            "commit": commit,
            "scanned_at": scanned_at,
        },
        "cases": cases,
        "hygiene": hygiene,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"Scanned {hygiene['total_scanned_tests']} tests. Wrote {len(cases)} cases to {out_path}")

    if args.hygiene_csv:
        csv_path = Path(args.hygiene_csv)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["case_id", "id_status", "substring_unsafe", "occurrences_count", "source_path", "source_symbol"])
            for c in cases:
                writer.writerow([
                    c["case_id"],
                    c["id_status"],
                    c["substring_unsafe"],
                    len(c["occurrences"]),
                    c["source_path"],
                    c["source_symbol"],
                ])
        print(f"Wrote hygiene CSV report to {csv_path}")


if __name__ == "__main__":
    main()
