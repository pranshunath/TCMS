# TCMS QA User Guide

## 1. Introduction

The Test Case Management System (TCMS) provides QA engineers and testers with an interactive web portal to manage manual and automated test specifications, track Jira test coverage, view real-time test execution history, and trigger targeted test runs directly against target test environments.

---

## 2. Navigating the TCMS Portal

Open `http://localhost:8000/tcms` in your web browser.

### User Role Banner
At the top right of the navigation header, your active role is indicated:
- **Viewer**: Read-only access to test specifications, versions, executions, and reports.
- **Editor**: Can update test steps, business rules, expected results, and link Jira tickets.
- **Admin**: Can perform batch test-suite imports and manage system configurations.

*(In local development, you can simulate different roles by setting the `X-User-Email` header or using test user accounts).*

---

## 3. Searching and Filtering Test Cases

The main test catalog (`/tcms`) allows multi-attribute filtering:

1. **Free-Text Search**: Enter keywords to search across Case IDs, titles, or business rules.
2. **Area**: Filter by application module (e.g., `checkout`, `redemption`, `points-calc`, `rewards-core`).
3. **Status**: Filter by lifecycle status:
   - `draft`: New or under-development tests.
   - `active`: Production-ready test cases.
   - `deprecated`: Obsolete or superseded tests.
4. **Jira Key**: Enter a ticket key (e.g., `REW-4021`) to isolate only test cases linked to that Jira issue.

Click **Filter** to apply or **Reset** to clear all criteria.

---

## 4. Test Case Details & Audit History

Clicking any **Case ID** (e.g., `TC_REW_1001`) opens the detail view:

### Specifications Section
- **Test Steps**: Step-by-step procedures to execute the test.
- **Business Rules**: Core domain logic, validation constraints, and edge-case requirements.
- **Expected Results**: Verifiable success criteria.
- **Source Code Anchor**: Displays the associated test file path and symbol (e.g., `tests/test_points.py::test_calculate_tier`).

### Jira Traceability Section
- Lists all active Jira tickets linked to this test case.
- **Link Ticket**: Editors can add ticket keys (e.g., `REW-1050`).
- **Unlink**: Soft-deletes the association without losing audit history.

### Version History Section
- Displays all historical versions ($v1, v2, v3, \dots$).
- Shows who made the change, the exact timestamp, and the change summary note.
- TCMS versioning is strictly immutable: edits create a new $N+1$ snapshot.

### Execution History Section
- Displays the most recent test run executions for this specific test case.
- Shows the test outcome (`Passed`, `Failed`, `Skipped`), execution duration, environment, run timestamp, and the runner Docker container image digest.

---

## 5. Editing Test Cases (Editors & Admins)

To update test documentation without modifying repository source code:
1. Navigate to the test case detail page.
2. Click the **Edit Case** button (top right).
3. Modify the desired fields:
   - **Title**
   - **Functional Area**
   - **Status** (`draft`, `active`, `deprecated`)
   - **Test Steps**
   - **Business Rules**
   - **Expected Results**
   - **Change Summary** *(Mandatory brief description of what changed)*
4. Click **Save Changes**.
5. The system saves the updates, increments the version to $N+1$, records the snapshot in `TmCaseVersion`, and redirects you back to the detail page.

---

## 6. Triggering Targeted Runs from the UI

You can execute a single test case against a live test environment directly from the UI:

1. On the test case detail page, locate the **Run This Case** card in the right sidebar.
2. Select your **Target Environment** (e.g., `pre-prod` or `staging`).
3. Click **Execute Test Run**.
4. The system validates:
   - The test case belongs to the `rewards` platform.
   - The test case ID is not marked as `ambiguous`.
   - The target environment is not locked by another running test suite.
5. On success, a modal displays the generated `run_id` and the triggered Argo workflow URL.

> [!NOTE]
> If another engineer holds an active lease on the selected environment, the system responds with an environment conflict alert (`HTTP 409`), showing who is holding the lease and when it expires.

---

## 7. Jira Compliance Reporting & CSV Export

For sprint sign-offs and release readiness, TCMS provides automated compliance reports by Jira ticket:

### Web Report
Navigate to `/tcms/jira/{jira_key}` (e.g., `http://localhost:8000/tcms/jira/REW-5000`).

The report renders:
1. **Linked Test Cases**: Every case mapped to the ticket with its latest status across all test environments (`pre-prod`, `staging`, `prod`) and the exact Docker image digest used during the run.
2. **Unlinked / Legacy Results**: Any test executed under this Jira run that lacked a test case ID, ensuring complete visibility into untagged tests.

### Compliance Exports for Sign-Off & SOC 2 Audits
From the Jira report page:
1. **Download CSV**: Click the green **Download CSV** button, or request `/api/tcms/jira/{jira_key}/report.csv` to attach evidence directly to Jira release tickets.
2. **SOC 2 Audit Pack (JSON)**: Click the purple **SOC 2 Audit Pack (JSON)** button, or request `/api/tcms/jira/{jira_key}/audit-pack` to get a cryptographically sealed, tamper-evident package complete with historical version snapshots and hash chain verification proof.
