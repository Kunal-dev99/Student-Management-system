"""Emailed links open the recipient's own institution: https://icr.<base-domain> when the
platform runs on subdomains, otherwise the single APP_BASE_URL (dev, default deployment)."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.tenant_resolver import base_url_for_subdomain


def test_links_use_the_institution_subdomain(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "app_base_url", "https://pgr.fusionpractices.com/")
    monkeypatch.setattr(s, "tenant_base_domain", "pgr.fusionpractices.com")
    assert base_url_for_subdomain("icr") == "https://icr.pgr.fusionpractices.com"
    assert base_url_for_subdomain("default") == "https://pgr.fusionpractices.com"   # the default deployment
    assert base_url_for_subdomain(None) == "https://pgr.fusionpractices.com"


def test_dev_keeps_the_single_base_url(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "app_base_url", "http://localhost:3000")
    monkeypatch.setattr(s, "tenant_base_domain", None)
    assert base_url_for_subdomain("icr") == "http://localhost:3000"


def test_port_is_kept(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "app_base_url", "http://localhost:3000")
    monkeypatch.setattr(s, "tenant_base_domain", "localhost")
    assert base_url_for_subdomain("icr") == "http://icr.localhost:3000"
