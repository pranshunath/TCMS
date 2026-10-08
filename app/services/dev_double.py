"""In-memory database double for hermetic tests and local development preview."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class FakeDatabaseDouble:
    """Hermetic in-memory test double mimicking MySQL for offline testing and local dev."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.cases: Dict[str, Dict[str, Any]] = {}
        self.versions: List[Dict[str, Any]] = []
        self.jira_links: List[Dict[str, Any]] = []
        self.roles: Dict[str, Dict[str, Any]] = {}
        self.migrations: List[str] = []
        self.test_runs: List[Dict[str, Any]] = []
        self.test_case_results: List[Dict[str, Any]] = []
        self.trigger_run_history: List[Dict[str, Any]] = []
        self.run_jira_tickets: List[Dict[str, Any]] = []
        self.leases: Dict[str, Dict[str, Any]] = {}
        self.audit_events: List[Dict[str, Any]] = []
        self._next_id = 1

    def _get_id(self) -> int:
        curr = self._next_id
        self._next_id += 1
        return curr

    def query(self, sql: str, params: Optional[Union[tuple, dict, list]] = None) -> List[Dict[str, Any]]:
        clean_sql = " ".join(sql.strip().split())
        params = list(params) if params else []

        # SchemaMigrations
        if "FROM SchemaMigrations" in clean_sql:
            return [{"id": i + 1, "name": name, "applied_at": datetime.now()} for i, name in enumerate(self.migrations)]

        # TmCase single fetch
        if clean_sql.startswith("SELECT * FROM TmCase WHERE case_id = %s"):
            cid = params[0]
            if cid in self.cases:
                return [dict(self.cases[cid])]
            return []

        if clean_sql.startswith("SELECT id FROM TmCase WHERE case_id = %s"):
            cid = params[0]
            if cid in self.cases:
                return [{"id": self.cases[cid]["id"]}]
            return []

        # Count TmCase query
        if "SELECT COUNT(*) as total FROM TmCase" in clean_sql:
            filtered = list(self.cases.values())
            return [{"total": len(self._filter_cases(filtered, clean_sql, params))}]

        # List TmCase query
        if "SELECT c.* FROM TmCase c" in clean_sql:
            filtered = list(self.cases.values())
            res = self._filter_cases(filtered, clean_sql, params)
            limit = params[-2] if len(params) >= 2 and isinstance(params[-2], int) else 50
            offset = params[-1] if len(params) >= 1 and isinstance(params[-1], int) else 0
            sliced = res[offset:offset + limit]
            return [dict(r) for r in sliced]

        # TmCaseVersion
        if "FROM TmCaseVersion WHERE case_id = %s" in clean_sql:
            cid = params[0]
            res = [dict(v) for v in self.versions if v["case_id"] == cid]
            res.sort(key=lambda x: x["version"], reverse=True)
            return res

        # TmCaseJira single / list
        if "FROM TmCaseJira WHERE case_id = %s AND jira_key = %s" in clean_sql:
            cid, jkey = params[0], params[1]
            matches = [dict(j) for j in self.jira_links if j["case_id"] == cid and j["jira_key"] == jkey]
            return matches

        if "FROM TmCaseJira WHERE case_id = %s AND removed_at IS NULL" in clean_sql:
            cid = params[0]
            matches = [dict(j) for j in self.jira_links if j["case_id"] == cid and j["removed_at"] is None]
            return matches

        if "FROM TmCaseJira WHERE case_id = %s" in clean_sql and "removed_at" not in clean_sql:
            cid = params[0]
            matches = [dict(j) for j in self.jira_links if j["case_id"] == cid]
            return matches

        # List cases by Jira
        if "FROM TmCase c INNER JOIN TmCaseJira j ON c.case_id = j.case_id WHERE j.jira_key = %s" in clean_sql:
            jkey = params[0]
            active_links = {j["case_id"]: j for j in self.jira_links if j["jira_key"] == jkey and j["removed_at"] is None}
            res = []
            for cid, link in active_links.items():
                if cid in self.cases:
                    c_dict = dict(self.cases[cid])
                    c_dict["link_kind"] = link["link_kind"]
                    c_dict["linked_at"] = link["linked_at"]
                    c_dict["linked_by"] = link["linked_by"]
                    res.append(c_dict)
            res.sort(key=lambda x: x["case_id"])
            return res

        # Roles
        if "FROM TmRoleAssignment WHERE email = %s" in clean_sql:
            email = params[0]
            if email in self.roles:
                return [dict(self.roles[email])]
            return []

        if "FROM TmRoleAssignment" in clean_sql:
            return [dict(r) for r in self.roles.values()]

        # Case executions query
        if "FROM TestCaseResult tcr" in clean_sql and "WHERE tcr.test_case_id = %s" in clean_sql:
            cid = params[0]
            limit = params[1] if len(params) >= 2 and isinstance(params[1], int) else 50
            run_map = {r["run_id"]: r for r in self.test_runs}
            matched = []
            for tcr in self.test_case_results:
                if tcr.get("test_case_id") == cid:
                    tr = run_map.get(tcr.get("run_id"), {})
                    row = dict(tcr)
                    row["job_name"] = tr.get("job_name", "runner-job")
                    row["environment"] = tr.get("environment", "pre-prod")
                    row["started_at"] = tr.get("started_at", tcr.get("created_at"))
                    row["triggered_by"] = tr.get("triggered_by", "system")
                    row["image_digest"] = tr.get("image_digest", "sha256:abc")
                    matched.append(row)
            matched.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
            return matched[:limit]

        # Unlinked / no id results query
        if "FROM TestCaseResult tcr INNER JOIN RunJiraTickets rjt" in clean_sql:
            jkey = params[0]
            linked_runs = {r["run_id"] for r in self.run_jira_tickets if r.get("jira_key") == jkey}
            run_map = {r["run_id"]: r for r in self.test_runs}
            matched = []
            for tcr in self.test_case_results:
                if tcr.get("run_id") in linked_runs and not tcr.get("test_case_id"):
                    tr = run_map.get(tcr.get("run_id"), {})
                    row = dict(tcr)
                    row["environment"] = tr.get("environment", "pre-prod")
                    row["triggered_by"] = tr.get("triggered_by", "system")
                    row["image_digest"] = tr.get("image_digest", "sha256:abc")
                    matched.append(row)
            return matched

        # EnvironmentLeases query
        if "FROM EnvironmentLeases WHERE environment = %s" in clean_sql:
            env = params[0]
            if env in self.leases:
                return [dict(self.leases[env])]

        # TestRun queries
        if "FROM TestRun" in clean_sql and "tcr" not in clean_sql:
            if "WHERE environment = %s" in clean_sql:
                env = params[0]
                return [dict(r) for r in self.test_runs if r.get("environment") == env]
            if "WHERE run_id = %s" in clean_sql:
                r_id = params[0]
                return [dict(r) for r in self.test_runs if r.get("run_id") == r_id]
            return [dict(r) for r in self.test_runs]

        # Standalone TestCaseResult queries
        if "FROM TestCaseResult" in clean_sql and "tcr" not in clean_sql:
            if "WHERE test_case_id = %s" in clean_sql:
                cid = params[0]
                matched = [dict(r) for r in self.test_case_results if r.get("test_case_id") == cid]
                matched.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
                return matched
            if "WHERE run_id = %s" in clean_sql:
                r_id = params[0]
                return [dict(r) for r in self.test_case_results if r.get("run_id") == r_id]
            return [dict(r) for r in self.test_case_results]

        # TmAuditEvent queries
        if "SELECT event_hash FROM TmAuditEvent ORDER BY id DESC LIMIT 1" in clean_sql:
            if self.audit_events:
                return [{"event_hash": self.audit_events[-1]["event_hash"]}]
            return []

        if "FROM TmAuditEvent" in clean_sql and "WHERE entity_type = %s AND entity_id = %s" in clean_sql:
            etype, eid = params[0], params[1]
            limit = params[2] if len(params) >= 3 and isinstance(params[2], int) else 50
            matched = [dict(ev) for ev in self.audit_events if ev.get("entity_type") == etype and ev.get("entity_id") == eid]
            matched.sort(key=lambda x: x["id"], reverse=True)
            return matched[:limit]

        if "FROM TmAuditEvent" in clean_sql and "ORDER BY id ASC" in clean_sql:
            matched = [dict(ev) for ev in self.audit_events]
            matched.sort(key=lambda x: x["id"])
            if "LIMIT" in clean_sql and len(params) >= 1 and isinstance(params[0], int):
                matched = matched[:params[0]]
            return matched

        return []

    def _filter_cases(self, cases: List[Dict[str, Any]], sql: str, params: list) -> List[Dict[str, Any]]:
        res = list(cases)
        if "c.case_id IN (SELECT case_id FROM TmCaseJira WHERE jira_key = %s" in sql:
            jkey = params[0]
            active_cids = {j["case_id"] for j in self.jira_links if j["jira_key"] == jkey and j["removed_at"] is None}
            res = [c for c in res if c["case_id"] in active_cids]

        if "c.area = %s" in sql:
            for p in params:
                if isinstance(p, str) and not p.startswith("%") and p in {c.get("area") for c in cases}:
                    res = [c for c in res if c.get("area") == p]
                    break

        if "c.status = %s" in sql:
            for p in params:
                if p in ("draft", "active", "deprecated"):
                    res = [c for c in res if c.get("status") == p]
                    break

        if "(c.case_id LIKE %s OR c.title LIKE %s OR c.business_rule LIKE %s)" in sql:
            for p in params:
                if isinstance(p, str) and p.startswith("%") and p.endswith("%"):
                    term = p.strip("%").lower()
                    res = [
                        c for c in res
                        if term in c["case_id"].lower()
                        or term in c.get("title", "").lower()
                        or term in (c.get("business_rule") or "").lower()
                    ]
                    break

        res.sort(key=lambda x: x["case_id"])
        return res

    def execute(self, sql: str, params: Optional[Union[tuple, dict, list]] = None) -> int:
        clean_sql = " ".join(sql.strip().split())
        params = list(params) if params else []

        # Insert SchemaMigrations
        if "INSERT INTO SchemaMigrations" in clean_sql:
            name = params[0]
            if name not in self.migrations:
                self.migrations.append(name)
            return 1

        # Insert TmCaseVersion
        if "INSERT INTO TmCaseVersion" in clean_sql:
            row_id = self._get_id()
            self.versions.append({
                "id": row_id,
                "case_id": params[0],
                "version": params[1],
                "title": params[2],
                "area": params[3],
                "test_type": params[4],
                "source_path": params[5],
                "source_symbol": params[6],
                "is_skipped": params[7],
                "steps": params[8],
                "business_rule": params[9],
                "expected_result": params[10],
                "status": params[11],
                "edited_by": params[12],
                "change_summary": params[13],
                "edited_at": datetime.now(),
            })
            return row_id

        # Insert TmCase
        if "INSERT INTO TmCase (" in clean_sql:
            cid = params[0]
            row_id = self._get_id()
            self.cases[cid] = {
                "id": row_id,
                "case_id": cid,
                "platform": params[1],
                "title": params[2],
                "area": params[3],
                "test_type": params[4],
                "source_path": params[5],
                "source_symbol": params[6],
                "is_skipped": params[7],
                "id_status": params[8],
                "substring_unsafe": params[9],
                "steps": params[10],
                "business_rule": params[11],
                "expected_result": params[12],
                "status": params[13],
                "version": params[14],
                "created_by": params[15],
                "updated_by": params[16],
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            return row_id

        # Update TmCase
        if clean_sql.startswith("UPDATE TmCase SET"):
            cid = params[-1]
            if cid in self.cases:
                c = self.cases[cid]
                if len(params) == 13:
                    c["title"] = params[0]
                    c["area"] = params[1]
                    c["test_type"] = params[2]
                    c["source_path"] = params[3]
                    c["source_symbol"] = params[4]
                    c["is_skipped"] = params[5]
                    c["steps"] = params[6]
                    c["business_rule"] = params[7]
                    c["expected_result"] = params[8]
                    c["status"] = params[9]
                    c["version"] = params[10]
                    c["updated_by"] = params[11]
                    c["updated_at"] = datetime.now()
                elif len(params) == 11:
                    c["platform"] = params[0]
                    c["title"] = params[1]
                    c["area"] = params[2]
                    c["test_type"] = params[3]
                    c["source_path"] = params[4]
                    c["source_symbol"] = params[5]
                    c["is_skipped"] = params[6]
                    c["id_status"] = params[7]
                    c["substring_unsafe"] = params[8]
                    c["updated_by"] = params[9]
                    c["updated_at"] = datetime.now()
                return 1
            return 0

        # Insert TmCaseJira
        if "INSERT INTO TmCaseJira" in clean_sql:
            row_id = self._get_id()
            self.jira_links.append({
                "id": row_id,
                "case_id": params[0],
                "jira_key": params[1],
                "link_kind": params[2],
                "linked_by": params[3],
                "linked_at": datetime.now(),
                "removed_at": None,
            })
            return row_id

        # Update TmCaseJira
        if "UPDATE TmCaseJira SET removed_at = CURRENT_TIMESTAMP" in clean_sql:
            cid, jkey = params[0], params[1]
            count = 0
            for j in self.jira_links:
                if j["case_id"] == cid and j["jira_key"] == jkey and j["removed_at"] is None:
                    j["removed_at"] = datetime.now()
                    count += 1
            return count

        if "UPDATE TmCaseJira SET removed_at = NULL" in clean_sql:
            user_email, link_kind, link_id = params[0], params[1], params[2]
            for j in self.jira_links:
                if j["id"] == link_id:
                    j["removed_at"] = None
                    j["linked_by"] = user_email
                    j["link_kind"] = link_kind
                    j["linked_at"] = datetime.now()
                    return 1
            return 0

        # Roles
        if "INSERT INTO TmRoleAssignment" in clean_sql:
            email = params[0]
            role = params[1]
            assigned_by = params[2]
            row_id = self._get_id()
            self.roles[email] = {
                "id": row_id,
                "email": email,
                "role": role,
                "assigned_by": assigned_by,
                "assigned_at": datetime.now(),
            }
            return row_id

        # TmAuditEvent
        if "INSERT INTO TmAuditEvent" in clean_sql:
            row_id = self._get_id()
            self.audit_events.append({
                "id": row_id,
                "event_uuid": params[0],
                "event_type": params[1],
                "entity_type": params[2],
                "entity_id": params[3],
                "actor_email": params[4],
                "payload_json": params[5],
                "prev_hash": params[6],
                "event_hash": params[7],
                "created_at": datetime.now(),
            })
            return row_id

        # EnvironmentLeases
        if "INSERT INTO EnvironmentLeases" in clean_sql:
            env = params[0]
            holder = params[1]
            self.leases[env] = {
                "environment": env,
                "holder_identity": holder,
                "expires_at": datetime(2099, 1, 1),
            }
            return 1

        if "DELETE FROM EnvironmentLeases WHERE environment = %s" in clean_sql:
            env = params[0]
            if env in self.leases:
                del self.leases[env]
                return 1
            return 0

        # TriggerRunHistory
        if "INSERT INTO TriggerRunHistory" in clean_sql:
            row_id = self._get_id()
            self.trigger_run_history.append({
                "id": row_id,
                "run_id": params[0],
                "job_name": params[1],
                "environment": params[2],
                "triggered_by": params[3],
                "test_type": params[4],
                "status": params[5] if len(params) > 5 else "Triggered",
                "started_at": datetime.now(),
            })
            return row_id

        if clean_sql.startswith("UPDATE TriggerRunHistory SET"):
            status_val = params[0]
            r_id = params[1]
            for trh in self.trigger_run_history:
                if trh.get("run_id") == r_id:
                    trh["status"] = status_val
                    return 1
            return 0

        # TestRun
        if "INSERT INTO TestRun" in clean_sql:
            row_id = self._get_id()
            self.test_runs.append({
                "id": row_id,
                "run_id": params[0],
                "job_name": params[1],
                "environment": params[2],
                "triggered_by": params[3],
                "status": params[4] if len(params) > 4 else "Running",
                "started_at": datetime.now(),
                "completed_at": None,
                "image_digest": "sha256:local-dev",
            })
            return row_id

        if clean_sql.startswith("UPDATE TestRun SET"):
            status_val = params[0]
            r_id = params[1]
            for tr in self.test_runs:
                if tr.get("run_id") == r_id:
                    tr["status"] = status_val
                    tr["completed_at"] = datetime.now()
                    return 1
            return 0

        # TestCaseResult
        if "INSERT INTO TestCaseResult" in clean_sql:
            row_id = self._get_id()
            self.test_case_results.append({
                "id": row_id,
                "run_id": params[0],
                "test_case_id": params[1],
                "node_id": params[2],
                "outcome": params[3],
                "duration_ms": params[4],
                "error_message": params[5],
                "created_at": datetime.now(),
            })
            return row_id

        return 1


def create_seeded_dev_double() -> FakeDatabaseDouble:
    """Creates a pre-populated in-memory database double for local development and UI preview."""
    double = FakeDatabaseDouble()

    # Seed representative test cases
    demo_cases = [
        {
            "case_id": "TC_REW_CHK_001",
            "platform": "rewards",
            "title": "Verifies checkout order discounts for Gold tier members",
            "area": "checkout",
            "test_type": "api",
            "source_path": "tests/test_checkout.py",
            "source_symbol": "test_checkout_order_discount_gold",
            "is_skipped": False,
            "id_status": "unique",
            "substring_unsafe": False,
            "steps": "1. Initialize shopping cart with eligible items.\n2. Apply promo code 'GOLD2026'.\n3. Call /api/rewards/apply-discount.\n4. Verify order total reflects 15% discount.",
            "business_rule": "Gold tier members receive 15% discount on orders exceeding $50 up to a maximum benefit of $100.",
            "expected_result": "HTTP 200 returned with adjusted total and line-item discount details.",
            "status": "active",
            "version": 1,
            "created_by": "qa-lead@vananam.com",
            "updated_by": "qa-lead@vananam.com",
        },
        {
            "case_id": "TC_REW_LOY_005",
            "platform": "rewards",
            "title": "Calculates points accrual on completed payment events",
            "area": "loyalty",
            "test_type": "api",
            "source_path": "tests/test_loyalty.py",
            "source_symbol": "test_accrue_points_on_payment",
            "is_skipped": False,
            "id_status": "unique",
            "substring_unsafe": False,
            "steps": "1. Dispatch payment success webhook.\n2. Fetch user points ledger.\n3. Assert ledger contains 10 points per dollar spent.",
            "business_rule": "Users accrue 10 reward points per $1 spent on qualified items.",
            "expected_result": "Points balance incremented and transaction logged in ledger.",
            "status": "active",
            "version": 2,
            "created_by": "qa-engineer@vananam.com",
            "updated_by": "qa-engineer@vananam.com",
        },
        {
            "case_id": "TC_REW_RED_012",
            "platform": "rewards",
            "title": "Redemption threshold validation for restricted accounts",
            "area": "redemption",
            "test_type": "grpc",
            "source_path": "tests/test_redemption.py",
            "source_symbol": "test_redemption_restricted_account",
            "is_skipped": False,
            "id_status": "unique",
            "substring_unsafe": False,
            "steps": "1. Create restricted user account.\n2. Attempt points redemption above threshold.\n3. Verify refusal response.",
            "business_rule": "Restricted accounts may not redeem points exceeding 5,000 in a single calendar month.",
            "expected_result": "gRPC PermissionDenied code returned with clear error explanation.",
            "status": "draft",
            "version": 1,
            "created_by": "qa-engineer@vananam.com",
            "updated_by": "qa-engineer@vananam.com",
        },
    ]

    for c in demo_cases:
        row_id = double._get_id()
        c_dict = dict(c)
        c_dict["id"] = row_id
        c_dict["created_at"] = datetime(2026, 10, 1, 9, 0, 0)
        c_dict["updated_at"] = datetime(2026, 10, 2, 11, 0, 0)
        double.cases[c["case_id"]] = c_dict

        # Seed initial version snapshot
        v_id = double._get_id()
        double.versions.append({
            "id": v_id,
            "case_id": c["case_id"],
            "version": c["version"],
            "title": c["title"],
            "area": c["area"],
            "test_type": c["test_type"],
            "source_path": c["source_path"],
            "source_symbol": c["source_symbol"],
            "is_skipped": c["is_skipped"],
            "steps": c["steps"],
            "business_rule": c["business_rule"],
            "expected_result": c["expected_result"],
            "status": c["status"],
            "edited_by": c["updated_by"],
            "change_summary": "Initial baseline import",
            "edited_at": datetime(2026, 10, 2, 11, 0, 0),
        })

    # Seed Jira Links
    jira_mappings = [
        ("TC_REW_CHK_001", "REW-5000"),
        ("TC_REW_LOY_005", "REW-5000"),
        ("TC_REW_RED_012", "REW-4021"),
    ]
    for cid, jkey in jira_mappings:
        link_id = double._get_id()
        double.jira_links.append({
            "id": link_id,
            "case_id": cid,
            "jira_key": jkey,
            "link_kind": "covers",
            "linked_by": "qa-lead@vananam.com",
            "linked_at": datetime(2026, 10, 1, 10, 0, 0),
            "removed_at": None,
        })

    # Seed Runs and Execution Results
    double.test_runs.append({
        "run_id": "run-rewards-preprod-101",
        "job_name": "rewards-tests-preprod",
        "environment": "pre-prod",
        "triggered_by": "qa-lead@vananam.com",
        "image_digest": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
        "started_at": datetime(2026, 10, 5, 14, 0, 0),
    })
    double.test_runs.append({
        "run_id": "run-rewards-staging-202",
        "job_name": "rewards-tests-staging",
        "environment": "staging",
        "triggered_by": "ci-automation@vananam.com",
        "image_digest": "sha256:9a3f2b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a",
        "started_at": datetime(2026, 10, 6, 8, 30, 0),
    })

    # Seed TestCaseResults
    double.test_case_results.append({
        "id": 1,
        "run_id": "run-rewards-preprod-101",
        "test_case_id": "TC_REW_CHK_001",
        "node_id": "tests/test_checkout.py::test_checkout_order_discount_gold",
        "outcome": "Passed",
        "duration_ms": 145,
        "error_message": None,
        "created_at": datetime(2026, 10, 5, 14, 5, 0),
    })
    double.test_case_results.append({
        "id": 2,
        "run_id": "run-rewards-staging-202",
        "test_case_id": "TC_REW_CHK_001",
        "node_id": "tests/test_checkout.py::test_checkout_order_discount_gold",
        "outcome": "Passed",
        "duration_ms": 138,
        "error_message": None,
        "created_at": datetime(2026, 10, 6, 8, 35, 0),
    })
    double.test_case_results.append({
        "id": 3,
        "run_id": "run-rewards-preprod-101",
        "test_case_id": "TC_REW_LOY_005",
        "node_id": "tests/test_loyalty.py::test_accrue_points_on_payment",
        "outcome": "Passed",
        "duration_ms": 210,
        "error_message": None,
        "created_at": datetime(2026, 10, 5, 14, 6, 0),
    })

    # Seed RunJiraTickets
    double.run_jira_tickets.append({
        "run_id": "run-rewards-preprod-101",
        "jira_key": "REW-5000",
    })

    # Seed Roles
    double.roles["dev-viewer@vananam.com"] = {
        "id": 1,
        "email": "dev-viewer@vananam.com",
        "role": "editor",
        "assigned_by": "bootstrap",
        "assigned_at": datetime.now(),
    }

    return double
