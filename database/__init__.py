"""PostgreSQL persistence for generated NCP reports."""

from database.config import DatabaseSettings
from database.report_repository import PostgresReportRepository


def build_report_repository_from_env():
    """Return an enabled repository, or ``None`` when DB storage is disabled."""
    settings = DatabaseSettings.from_env()
    if not settings.enabled:
        return None
    return PostgresReportRepository(settings)


__all__ = [
    "DatabaseSettings",
    "PostgresReportRepository",
    "build_report_repository_from_env",
]
