"""The server-wide partner URL (INTEGRATION_<SYSTEM>_URL) stands in only for the default
deployment; another institution with no target of its own sends nothing, rather than its
messages going to someone else's partner endpoint."""
from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.core.tenant_context import DEFAULT_TENANT_ID, tenant_scope
from app.modules.integration.adapters import _env_url


def test_env_partner_url_is_for_the_default_deployment_only(monkeypatch):
    monkeypatch.setattr(get_settings(), "integration_finance_url", "https://finance.example/hook")
    with tenant_scope(DEFAULT_TENANT_ID):
        assert _env_url("finance") == "https://finance.example/hook"
    assert _env_url("finance") == "https://finance.example/hook"        # single-institution install
    with tenant_scope(uuid.UUID("00000000-0000-0000-0000-0000000000bb")):
        assert _env_url("finance") is None
