"""Custom attribute governance, Phase 7 — permission matrix and error contract.

Every governance endpoint against three roles:
  reader   — student.read only (e.g. a supervisor)
  maker    — PGR Administrator: may request, may not decide
  approver — Institution Administrator: may decide (but never their own request)

Each refusal must use the standard error envelope ({"error": {"code", "message", ...}}).
"""
from __future__ import annotations

import pytest

from tests.integration.custom_attr_helpers import live_attribute
from tests.integration.test_custom_attr_governance_p1 import REQ, gov  # noqa: F401  (fixture)

A = "/api/v1/students/custom-attributes"
CODES = {400: "validation_error", 403: "permission_denied", 404: "not_found", 409: "conflict",
         422: "workflow_error"}


async def test_permission_matrix_and_error_envelope(gov):
    c, hs, _ = gov
    active = await live_attribute(c, hs["maker"], hs["admin2"], label="Matrix active", dataType="code")
    pending = (await c.post(REQ, headers=hs["maker"], json={"label": "Matrix pending", "reason": "x"})).json()
    a, p = active["id"], pending["id"]

    # (method, path, body) -> expected status for reader / maker / approver(admin1).
    # admin1 did not raise `pending` (maker did), so maker-checker allows admin1 to decide it.
    matrix = [
        ("GET", f"{A}", None, (200, 200, 200)),
        ("GET", f"{A}?status=pending", None, (403, 200, 200)),
        ("GET", f"{A}/catalogue", None, (403, 200, 200)),
        ("GET", f"{A}/dashboard", None, (403, 200, 200)),
        ("GET", f"{A}/review-candidates", None, (403, 200, 200)),
        ("GET", f"{A}/{a}", None, (403, 200, 200)),
        ("GET", f"{A}/{a}/dependencies", None, (403, 200, 200)),
        ("GET", f"{A}/{a}/usage", None, (403, 200, 200)),
        ("GET", f"{A}/{a}/health", None, (403, 200, 200)),
        ("GET", REQ, None, (403, 200, 200)),
        ("GET", f"{REQ}/{p}", None, (403, 200, 200)),
        ("GET", f"{REQ}/{p}/assessment", None, (403, 200, 200)),
        ("GET", "/api/v1/students/custom-attribute-events", None, (403, 200, 200)),
        ("POST", f"{REQ}/check", {"label": "Ethnicity"}, (403, 200, 200)),
        ("POST", f"{REQ}/{p}/assess", None, (403, 200, 200)),
        ("POST", f"{REQ}/{p}/activate", None, (403, 403, 409)),       # approver: not approved yet
        ("POST", f"{REQ}/{p}/reject", {"reason": ""}, (403, 403, 400)),  # approver: reason missing
        ("POST", f"{A}/{a}/keep", {}, (403, 403, 409)),                # not under review
        ("POST", f"{A}/{a}/retire", {"reason": "x"}, (403, 403, 409)),
        ("POST", f"{A}/{a}/restore", {"reason": "x"}, (403, 403, 409)),
        ("PUT", f"/api/v1/students/custom-fields/{p}/values", {"values": []}, (403, 422, 422)),  # not live
        ("POST", REQ, {"label": "Matrix new", "reason": "x"}, (403, 201, 201)),
        ("POST", f"{REQ}/{p}/approve", {}, (403, 403, 200)),
    ]
    roles = ("reader", "maker", "admin1")
    for method, path, body, expected in matrix:
        for role, want in zip(roles, expected):
            if method == "POST" and path == REQ and role == "admin1":
                body = {"label": "Matrix new two", "reason": "x"}
            r = await c.request(method, path, headers=hs[role], json=body)
            assert r.status_code == want, (method, path, role, r.status_code, r.text[:200])
            if r.status_code >= 400:
                err = r.json()["error"]
                assert err["code"] == CODES[r.status_code] and err["message"], (method, path, role, err)

    # Unknown ids are a 404 with the envelope, not a 500.
    missing = "00000000-0000-0000-0000-000000000099"
    for method, path in (("GET", f"{A}/{missing}"), ("GET", f"{REQ}/{missing}"),
                         ("POST", f"{REQ}/{missing}/approve"), ("POST", f"{A}/{missing}/review")):
        r = await c.request(method, path, headers=hs["admin1"], json={"reason": "x"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", (path, r.text[:200])


@pytest.mark.parametrize("body", [
    {"label": "", "reason": "x"},
    {"label": "x" * 121, "reason": "x"},
    {"label": "Ok", "reason": "x", "dataType": "blob"},
    {"label": "Ok"},
])
async def test_request_validation_errors_use_the_envelope(gov, body):
    c, hs, _ = gov
    r = await c.post(REQ, headers=hs["maker"], json=body)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "validation_error" and r.json()["error"]["message"]
