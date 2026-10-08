"""Local export script for AI agents to dump TCMS test cases and business rules to JSON.

Usage:
  python scripts/export_tcms_for_ai.py --out tcms_ai_cases.json
  python scripts/export_tcms_for_ai.py --url http://127.0.0.1:8000/api/tcms/export.json --email dev@vananam.com
"""
import argparse
import datetime
import json
import urllib.request
from pathlib import Path


def export_via_api(api_url: str, user_email: str, out_path: Path) -> None:
    req = urllib.request.Request(
        api_url,
        headers={
            "X-User-Email": user_email,
            "Accept": "application/json",
            "User-Agent": "TCMS-AI-Agent-Exporter/1.0",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Exported {data['metadata']['total_cases']} cases to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Export TCMS cases and business rules for AI agents")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/api/tcms/export.json",
        help="TCMS export endpoint URL",
    )
    parser.add_argument(
        "--email",
        default="ai-agent@vananam.com",
        help="Authenticated user email header",
    )
    parser.add_argument(
        "--out",
        default="tcms_ai_cases.json",
        help="Path to write exported JSON",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    export_via_api(args.url, args.email, out_path)


if __name__ == "__main__":
    main()
