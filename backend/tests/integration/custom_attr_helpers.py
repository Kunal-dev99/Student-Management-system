"""Test helper: get a custom attribute live the governed way — one user requests it, another
approves and activates it (maker-checker). There is no one-step create any more."""
from __future__ import annotations


async def live_attribute(c, maker_h: dict, checker_h: dict, **body) -> dict:
    body.setdefault("dataType", "string")
    body.setdefault("reason", "HESA")
    r = await c.post("/api/v1/students/custom-attribute-requests", headers=maker_h, json=body)
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/students/custom-attribute-requests/{r.json()['id']}/approve",
                     # A reason, so an assessment that flags a possible duplicate can be overridden.
                     headers=checker_h, json={"activate": True, "reason": "Reviewed for the test"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"
    return r.json()
