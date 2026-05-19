"""Credential provider abstractions for NCP clients."""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Credentials:
    """NCP credential pair."""

    access_key: str
    secret_key: str


class CredentialProvider(Protocol):
    """Provider interface that can support tenant/service specific lookup."""

    def get_credentials(self, service: str | None = None, tenant_id: str | None = None) -> Credentials:
        """Return credentials for the given context."""


class EnvCredentialProvider:
    """Default provider reading values from process environment variables."""

    def __init__(
        self,
        access_key_env: str = "NCP_ACCESS_KEY",
        secret_key_env: str = "NCP_SECRET_KEY",
    ) -> None:
        self.access_key_env = access_key_env
        self.secret_key_env = secret_key_env

    def get_credentials(self, service: str | None = None, tenant_id: str | None = None) -> Credentials:
        access_key = os.getenv(self.access_key_env, "")
        secret_key = os.getenv(self.secret_key_env, "")
        return Credentials(access_key=access_key, secret_key=secret_key)


class SQLiteCredentialProvider:
    """SQLite-backed provider for future DB integration.

    Table schema example:
        CREATE TABLE ncp_credentials (
            tenant_id TEXT,
            service TEXT,
            access_key TEXT NOT NULL,
            secret_key TEXT NOT NULL,
            updated_at TEXT,
            PRIMARY KEY (tenant_id, service)
        );
    """

    def __init__(self, db_path: str | Path, cache_ttl_seconds: int = 60) -> None:
        self.db_path = str(db_path)
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[str | None, str | None], tuple[float, Credentials]] = {}

    def get_credentials(self, service: str | None = None, tenant_id: str | None = None) -> Credentials:
        cache_key = (tenant_id, service)
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and now - cached[0] < self.cache_ttl_seconds:
            return cached[1]

        credentials = self._query_credentials(service=service, tenant_id=tenant_id)
        self._cache[cache_key] = (now, credentials)
        return credentials

    def _query_credentials(self, service: str | None, tenant_id: str | None) -> Credentials:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT access_key, secret_key
                  FROM ncp_credentials
                 WHERE tenant_id IS ?
                   AND service IS ?
                """,
                (tenant_id, service),
            ).fetchone()

            if row is None and service is not None:
                row = conn.execute(
                    """
                    SELECT access_key, secret_key
                      FROM ncp_credentials
                     WHERE tenant_id IS ?
                       AND service IS NULL
                    """,
                    (tenant_id,),
                ).fetchone()

            if row is None:
                raise LookupError(
                    f"No credentials found for tenant_id={tenant_id!r}, service={service!r}"
                )

            return Credentials(access_key=row["access_key"], secret_key=row["secret_key"])
