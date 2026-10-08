# Developer Guide: How to Add a Test Case

## 1. Overview

TCMS bridges the automated pytest test suite in `platform_svc_test-suite` with central test case management, Jira tracking, and targeted test execution.

To enable TCMS tracking and targeted execution, every test in the suite must follow the conventions outlined below.

---

## 2. Test Case ID Conventions

### Allowed Syntax
Test case IDs must match the regex:
```regex
^[A-Za-z0-9][A-Za-z0-9_.-]{2,99}$
```
- Length: 3 to 100 characters.
- Must begin with an alphanumeric character.
- May contain alphanumeric characters, underscores (`_`), dots (`.`), and hyphens (`-`).

### Recommended Naming Pattern
Follow a structured prefix format:
```
TC_REW_<AREA>_<NUMBER>
```
Examples:
- `TC_REW_CHK_001` (Rewards Checkout Test 001)
- `TC_REW_LOY_015` (Loyalty Points Test 015)
- `TC_REW_RED_042` (Redemption Flow Test 042)

### Avoiding Substring Collisions
When running tests with pytest expressions (`-k`), a short ID can accidentally match longer IDs:
- **Problem**: Targeting `TC_01` will also match and run `TC_010`, `TC_011`, and `TC_0100`.
- **Solution**: Always use fixed 3-digit zero-padding (`001`, `002`, `010`) or distinct semantic identifiers.
- The TCMS scanner automatically flags substring-unsafe test IDs during static analysis.

---

## 3. How to Author Tests in Pytest

The TCMS static AST scanner extracts test case IDs without importing test modules or running code.

### Pattern 1: Standard Test Function (Docstring)
Include the test case ID at the start of the docstring or on a dedicated line:

```python
def test_apply_rewards_discount():
    """TC_REW_CHK_001: Verifies valid promo code reduces total order amount."""
    cart = create_cart(items=[{"id": "sku-1", "price": 100}])
    cart.apply_code("REW10")
    assert cart.total == 90
```

Alternatively, use an explicit `@tcms_id:` annotation in the docstring:
```python
def test_points_expiry_calculation():
    """Calculates points expiration date for tiered users.
    
    @tcms_id: TC_REW_LOY_008
    """
    expiry = calculate_expiry(points=500, tier="gold")
    assert expiry.year == 2027
```

---

### Pattern 2: Parametrized Tests (`@pytest.mark.parametrize`)
For parametrized test cases, every individual parameter variation must be associated with its own unique test case ID.

#### Approach A: Using Parameter `ids` (Recommended)
Set the pytest `ids` parameter to match the test case IDs:

```python
import pytest

@pytest.mark.parametrize(
    "tier, expected_multiplier",
    [
        ("bronze", 1.0),
        ("silver", 1.2),
        ("gold", 1.5),
    ],
    ids=[
        "TC_REW_TIER_001",
        "TC_REW_TIER_002",
        "TC_REW_TIER_003",
    ]
)
def test_tier_multiplier(tier, expected_multiplier):
    """Verifies tier multiplier calculation."""
    multiplier = get_tier_multiplier(tier)
    assert multiplier == expected_multiplier
```

#### Approach B: Passing `test_case_id` in Parameters
Include a parameter named `test_case_id` or `tc_id`:

```python
import pytest

@pytest.mark.parametrize(
    "tier, bonus, test_case_id",
    [
        ("standard", 0, "TC_REW_BONUS_001"),
        ("vip", 100, "TC_REW_BONUS_002"),
    ]
)
def test_bonus_points(tier, bonus, test_case_id):
    """Calculates bonus points based on user status."""
    assert calculate_bonus(tier) == bonus
```

---

## 4. Test Hygiene Verification

Before committing changes, run the TCMS static scanner locally:

```bash
python scripts/tcms_scan.py --source-dir tests/ --output scan_results.json
```

### Reviewing Scanner Diagnostics
The scanner outputs a summary table:
```
==================================================
TCMS Scanner Summary
==================================================
Total Test Functions Scanned: 48
Total Test Case IDs Found:   52
Unique IDs:                  52
Shared/Duplicate IDs:         0
Ambiguous IDs:                0
Substring-Unsafe IDs:         0
==================================================
```

### Addressing Scanner Warnings
- **Duplicate / Shared IDs**: If the same ID is declared in multiple functions, rename one of them to guarantee uniqueness.
- **Ambiguous IDs**: If an ID contains invalid characters or does not adhere to regex rules, correct the string.
- **Substring-Unsafe IDs**: If an ID is a substring prefix of another ID, update the identifier to use consistent padding.

---

## 5. Integrating with CI and TCMS

1. **Commit and Push**: Ensure all test IDs are unique and the scanner reports 0 ambiguous items.
2. **Automated Scanner Import**: The CI pipeline runs `scripts/tcms_scan.py` and posts new/updated test cases to `POST /api/tcms/import`.
3. **Verify in Portal**: Open `http://localhost:8000/tcms` to verify that your newly added test cases appear with status `active` or `draft`.
4. **Link Jira Tickets**: Add the corresponding Jira ticket (e.g. `REW-1234`) on the test case detail page or via Jira bulk link.
