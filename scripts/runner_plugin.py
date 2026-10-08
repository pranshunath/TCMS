"""Pytest collection hook plugin for exact test case ID filtering.

Intended for inclusion in platform_svc_test-suite conftest.py or installed as a pytest plugin.
Filters pytest collected items based on the TEST_CASE_IDS environment variable.
"""
import os
import re
from typing import Any, List, Optional, Tuple

CASE_ID_REGEX = re.compile(r"(TC_|GRPC_)[A-Za-z0-9_.-]+")


def extract_test_case_id_from_item(item) -> Optional[str]:
    """Extracts test_case_id from a pytest item according to repository conventions."""
    # 1. Check callspec params (from @pytest.mark.parametrize)
    if hasattr(item, "callspec") and hasattr(item.callspec, "params"):
        params = item.callspec.params
        if "test_case_id" in params and params["test_case_id"]:
            return str(params["test_case_id"])
        if "description" in params and params["description"]:
            m = CASE_ID_REGEX.search(str(params["description"]))
            if m:
                return m.group(0)

    # 2. Check docstring
    if hasattr(item, "obj") and item.obj and hasattr(item.obj, "__doc__") and item.obj.__doc__:
        m = CASE_ID_REGEX.search(item.obj.__doc__)
        if m:
            return m.group(0)

    # 3. Check nodeid / name
    name = getattr(item, "name", "")
    m = CASE_ID_REGEX.search(name)
    if m:
        return m.group(0)

    return None


def filter_items_by_test_case_ids(items: List[Any], raw_env_ids: Optional[str]) -> Tuple[List[Any], List[Any]]:
    """Filters pytest items, keeping only items whose extracted ID matches TEST_CASE_IDS."""
    if not raw_env_ids or not raw_env_ids.strip():
        return list(items), []

    allowed_ids = {cid.strip() for cid in raw_env_ids.split(",") if cid.strip()}
    if not allowed_ids:
        return list(items), []

    selected = []
    deselected = []

    for item in items:
        cid = extract_test_case_id_from_item(item)
        if cid and cid in allowed_ids:
            selected.append(item)
        else:
            deselected.append(item)

    return selected, deselected


def pytest_collection_modifyitems(config, items) -> None:
    """Pytest hook keeping only tests matching TEST_CASE_IDS."""
    raw_ids = os.getenv("TEST_CASE_IDS")
    selected, deselected = filter_items_by_test_case_ids(items, raw_ids)

    if deselected:
        if hasattr(config, "hook") and hasattr(config.hook, "pytest_deselected"):
            config.hook.pytest_deselected(items=deselected)
        items[:] = selected
