import os
import shutil
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def gated_suite(pytester: pytest.Pytester) -> pytest.Pytester:
    tests_dir = Path(__file__).parent
    pytester.makeconftest((tests_dir / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyprojecttoml((tests_dir.parent / "pyproject.toml").read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_gates="""
        import unittest
        import pytest

        @pytest.mark.integration
        class TestDatabase(unittest.TestCase):
            def test_database(self):
                pass

        @pytest.mark.worker_integration
        class TestWorker(unittest.TestCase):
            def test_worker(self):
                pass

        class TestOrdinary(unittest.TestCase):
            @pytest.mark.js
            def test_js(self):
                pass

            def test_plain(self):
                pass
        """
    )
    return pytester


@pytest.mark.parametrize(
    ("ci", "database", "worker", "node", "selection", "passed", "skipped", "exit_code"),
    [
        ("0", "0", "0", False, "", 1, 3, 0),
        ("0", "1", "0", False, "", 2, 2, 0),
        ("0", "0", "1", False, "", 2, 2, 0),
        ("1", "0", "0", False, "", 0, 0, 4),
        ("1", "1", "1", True, "", 4, 0, 0),
        ("1", "0", "0", True, "not integration and not worker_integration", 2, 0, 0),
    ],
)
def test_execution_gates(
    gated_suite, monkeypatch, ci, database, worker, node, selection, passed, skipped, exit_code
):
    settings = {
        "CI": ci,
        "REPORT_DB_INTEGRATION_TEST": database,
        "REPORT_DB_WORKER_INTEGRATION_TEST": worker,
    }
    getenv = os.getenv
    which = shutil.which
    monkeypatch.setattr(
        os, "getenv", lambda name, default=None: settings.get(name, getenv(name, default))
    )
    monkeypatch.setattr(
        shutil, "which", lambda name: ("node" if node else None) if name == "node" else which(name)
    )
    result = gated_suite.runpytest_inprocess("-q", "test_gates.py", "-m", selection)
    assert result.ret == exit_code
    if exit_code:
        result.stderr.fnmatch_lines(["*CI test prerequisites missing:*"])
    else:
        result.assert_outcomes(passed=passed, skipped=skipped, deselected=2 if selection else 0)
