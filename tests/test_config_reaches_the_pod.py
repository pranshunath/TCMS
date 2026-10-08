"""Tests ensuring all configuration settings reach the pod or are explicitly allowlisted."""
from app.config import Settings

# Allowlist for settings that are either local dev only, dynamically resolved, or defaults
CONFIG_ALLOWLIST = {
    "TRIGGER_DEV_AUTH": "Local development authorization switch",
    "TCMS_ADMINS": "Bootstrap TCMS admin email list",
    "CANCEL_ADMINS": "Existing bootstrap cancel admin list",
    "REPORTING_HOST": "Database connection host",
    "REPORTING_PORT": "Database connection port (defaults to 3307 for safety)",
    "REPORTING_USER": "Database connection user",
    "REPORTING_PASSWORD": "Database connection password",
    "REPORTING_DB": "Database connection name",
    "K8S_NAMESPACE": "Namespace for executing test runner jobs",
}


def test_all_settings_fields_are_documented_and_allowlisted():
    settings = Settings()
    declared_fields = set(settings.model_fields.keys())

    missing = declared_fields - set(CONFIG_ALLOWLIST.keys())
    assert not missing, f"New Settings fields missing from allowlist: {missing}. Add them to k8s configs or allowlist."
