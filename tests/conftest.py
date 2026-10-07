import os
import shutil

import pytest


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    prerequisites = {
        "integration": (
            os.getenv("REPORT_DB_INTEGRATION_TEST") == "1",
            "Set REPORT_DB_INTEGRATION_TEST=1 to use a prepared test PostgreSQL.",
        ),
        "worker_integration": (
            os.getenv("REPORT_DB_WORKER_INTEGRATION_TEST") == "1",
            "Set REPORT_DB_WORKER_INTEGRATION_TEST=1 with a prepared worker test account.",
        ),
        "js": (shutil.which("node") is not None, "Node.js is not installed"),
    }
    missing = {
        reason
        for marker, (available, reason) in prerequisites.items()
        if not available and any(item.get_closest_marker(marker) for item in items)
    }
    if os.getenv("CI") == "1" and missing:
        raise pytest.UsageError("CI test prerequisites missing: " + " ".join(sorted(missing)))
    for item in items:
        for marker, (available, reason) in prerequisites.items():
            if not available and item.get_closest_marker(marker):
                item.add_marker(pytest.mark.skip(reason=reason))
