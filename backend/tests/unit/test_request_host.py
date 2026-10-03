"""Behind the Next.js proxy the backend sees its own address as Host; the user's address
(which names the institution) arrives in X-Forwarded-Host. It is trusted only when the
deployment says so, because a directly reachable API must not let callers pick their host."""
from __future__ import annotations

from types import SimpleNamespace

from app.core.config import get_settings
from app.core.tenant_resolver import request_host, subdomain_of


def _req(**headers):
    return SimpleNamespace(headers={k.replace("_", "-"): v for k, v in headers.items()})


def test_forwarded_host_is_ignored_unless_trusted(monkeypatch):
    monkeypatch.setattr(get_settings(), "trust_forwarded_host", False)
    r = _req(host="localhost:8000", x_forwarded_host="icr.pgr.fusionpractices.com")
    assert request_host(r) == "localhost:8000"


def test_forwarded_host_names_the_institution_when_trusted(monkeypatch):
    monkeypatch.setattr(get_settings(), "trust_forwarded_host", True)
    r = _req(host="localhost:8000", x_forwarded_host="icr.pgr.fusionpractices.com, proxy.internal")
    assert request_host(r) == "icr.pgr.fusionpractices.com"
    assert subdomain_of(request_host(r), "pgr.fusionpractices.com") == "icr"
    assert request_host(_req(host="pgr.fusionpractices.com")) == "pgr.fusionpractices.com"
