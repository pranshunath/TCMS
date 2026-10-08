# TCMS Operational Runbook

## 1. Overview & Safety Architecture

The Test Case Management System (TCMS) is integrated directly into the `trigger-service` application. It provides centralized test case cataloging, version tracking, Jira traceability, static test-suite scanning, and targeted test run execution for the Rewards platform test suite.

### Critical Safety Guardrails
- **Port Isolation**: Local development **must always** target MySQL port `3307`. Host port `3306` runs a live/production `mysqld` service.
- **Fail-Fast Startup Guard**: If `TRIGGER_DEV_AUTH=true` is enabled while `TRIGGER_DB_PORT=3306`, the application startup crashes immediately with `RuntimeError: FATAL SAFETY GUARD ACTIVATED`.
- **Database Schema Isolation**: All TCMS data resides strictly in new tables prefixed with `Tm` (`TmCase`, `TmCaseVersion`, `TmCaseJira`, `TmRoleAssignment`). Legacy `Tcms*` tables and existing `TestRun`/`TestCaseResult` write pipelines remain untouched.

---

## 2. Configuration & Environment Variables

All configuration is managed through environment variables or a `.env` file loaded by [`app/config.py`](file:///c:/Users/HP/OneDrive/Desktop/TCMS/app/config.py).

| Variable | Dev Default | Description |
| :--- | :--- | :--- |
| `TRIGGER_DB_HOST` | `127.0.0.1` | MySQL database host |
| `TRIGGER_DB_PORT` | `3307` | MySQL port (**Must be 3307 in local development**) |
| `TRIGGER_DB_USER` | `root` | Database user |
| `TRIGGER_DB_PASSWORD` | `secret` | Database password |
| `TRIGGER_DB_NAME` | `trigger_db` | Database schema name |
| `TRIGGER_DEV_AUTH` | `true` | Enables dev auth header (`X-User-Email`) for local testing |
| `TCMS_ADMIN_EMAILS` | `admin@vananam.com,qa-lead@vananam.com` | Comma-delimited list of super-admins |
| `ENVIRONMENT_ALLOWLIST`| `pre-prod,staging,prod` | Permitted environments for test execution |
| `PLATFORM_ALLOWLIST` | `rewards` | Permitted test platforms |

Sample `.env` file:
```dotenv
TRIGGER_DB_HOST=127.0.0.1
TRIGGER_DB_PORT=3307
TRIGGER_DB_USER=root
TRIGGER_DB_PASSWORD=secret
TRIGGER_DB_NAME=trigger_db
TRIGGER_DEV_AUTH=true
TCMS_ADMIN_EMAILS=admin@vananam.com,qa-lead@vananam.com
ENVIRONMENT_ALLOWLIST=pre-prod,staging,prod
PLATFORM_ALLOWLIST=rewards
```

---

## 3. Database Migrations

TCMS migrations use a contiguous sequential numbering model managed by [`app/services/schema.py`](file:///c:/Users/HP/OneDrive/Desktop/TCMS/app/services/schema.py) and stored under [`sql/migrations/`](file:///c:/Users/HP/OneDrive/Desktop/TCMS/sql/migrations/).

### Migration List
1. `001_initial_schema.sql` (Legacy trigger service tables)
2. `002_add_environment_leases.sql`
3. `003_add_run_jira_tickets.sql`
4. `004_add_test_case_results.sql`
5. `005_add_image_digest_to_test_run.sql`
6. `006_add_failure_analysis.sql`
7. `007_add_slack_notifications.sql`
8. `008_tm_case.sql` (`TmCase` core metadata table)
9. `009_tm_case_version.sql` (`TmCaseVersion` immutable audit snapshot table)
10. `010_tm_case_jira.sql` (`TmCaseJira` traceability mapping table)
11. `011_tm_role_assignment.sql` (`TmRoleAssignment` RBAC table)
12. `012_tm_audit_event.sql` (`TmAuditEvent` tamper-evident hash-chained audit log table)

### Applying Migrations
Migrations are applied automatically at service startup in production, or can be run manually:
```bash
python -m app.services.schema
```
*Note: All migrations use `CREATE TABLE IF NOT EXISTS` and strict foreign key isolation.*

---

## 4. Starting the Service

### Local Development Server
Ensure your virtual environment is active, then launch Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Health & Readiness Check
Verify the service is running and connected to the database:
```bash
curl -i http://localhost:8000/health
```
Access the TCMS web UI:
- Open `http://localhost:8000/tcms` in your browser.

---

## 5. Role-Based Access Control (RBAC)

TCMS implements a three-tier RBAC system:
1. **Viewer**: Read-only access to test cases, version history, execution history, and compliance reports.
2. **Editor**: Can edit test case content (steps, business rules, expected results), which increments the version ($N+1$).
3. **Admin**: Can trigger batch scan imports and assign user roles.

### User Identity Resolution
- In development (`TRIGGER_DEV_AUTH=true`), user identity is resolved via the `X-User-Email` HTTP header.
- If no header is provided in dev mode, it defaults to `dev-user@vananam.com` (Viewer).
- Users configured in `TCMS_ADMIN_EMAILS` automatically receive the `admin` role.

---

## 6. Static Scanner & Test Case Import

The static scanner inspects test repositories without importing or executing Python code.

### Running the Scanner
```bash
python scripts/tcms_scan.py --source-dir ../platform_svc_test-suite/tests --output scanned_cases.json
```

The scanner produces a JSON manifest with test case hygiene flags:
- `is_unique`: True if ID appears exactly once across the suite.
- `is_shared`: True if multiple functions declare this ID.
- `is_ambiguous`: True if syntax is malformed or invalid.
- `substring_unsafe`: True if the case ID is a substring of another ID (e.g. `TC_01` vs `TC_010`).

### Importing Scanned Cases
Admins can submit the scanned manifest to the API:
```bash
curl -X POST http://localhost:8000/api/tcms/import \
  -H "Content-Type: application/json" \
  -H "X-User-Email: admin@vananam.com" \
  -d @scanned_cases.json
```

---

## 7. AI Context Export

AI coding agents and LLM tools can consume active test cases, steps, and business rules via JSON:

### CLI Tool
```bash
python scripts/export_tcms_for_ai.py --output tcms_context.json
```

### HTTP Endpoint
```bash
curl -s http://localhost:8000/api/tcms/export.json \
  -H "X-User-Email: viewer@vananam.com" > tcms_context.json
```

---

## 8. Tamper-Evident Audit Log Verification & SOC 2 Audit Packs

TCMS maintains an append-only SHA-256 hash chain in `TmAuditEvent` for SOC 2 Type II audit evidence.

### Verifying Chain Integrity
Auditors or administrators can verify that no past event has been altered, forged, or deleted:
```bash
curl -s http://localhost:8000/api/tcms/audit/verify \
  -H "X-User-Email: viewer@vananam.com"
```
Response when chain is intact:
```json
{
  "valid": true,
  "total_events": 154,
  "head_hash": "a1b2c3d4...",
  "tampered_event_id": null,
  "reason": "Audit chain intact and verified"
}
```

### Generating a Per-Jira SOC 2 Audit Pack
To produce a sealed, self-verifying audit package for a release ticket:
```bash
curl -s http://localhost:8000/api/tcms/jira/REW-5000/audit-pack \
  -H "X-User-Email: viewer@vananam.com" > audit_pack_REW-5000.json
```
The audit pack packages:
1. Complete compliance execution report across environments (`pre-prod`, `staging`, `prod`) and image digests.
2. Full test case specifications and version diffs.
3. Relevant `TmAuditEvent` entries with actor identity and timestamp.
4. Proof of unbroken hash chain verification.
5. Overall cryptographic pack signature (`pack_digest`).

---

## 9. Incident Troubleshooting

### 1. Startup Guard Abort
- **Error**: `FATAL SAFETY GUARD ACTIVATED: TRIGGER_DEV_AUTH=true cannot run against MySQL port 3306.`
- **Remedy**: Update `.env` or set `TRIGGER_DB_PORT=3307`. Verify local MySQL container or proxy is listening on `3307`.

### 2. Environment Lease Conflict (HTTP 409)
- **Error**: `Environment 'pre-prod' is currently locked by 'user@vananam.com'.`
- **Remedy**: Another test run is currently holding the environment lease. Wait for the run to complete or inspect `EnvironmentLeases` table if orphaned.

### 3. Ambiguous Case Execution Refused (HTTP 400)
- **Error**: `Case ID 'TC_DUP_123' has hygiene status 'ambiguous' and cannot be targeted.`
- **Remedy**: Resolve duplicate test case IDs in the automated test repository and re-run the static scanner import.
