"""Custom attribute governance, Phase 6 — usage tracking and lifecycle review.

What must hold (plan Phase 6 acceptance criteria):
- a return that is generated, downloaded or signed off records that it read the attribute; a
  validation preview does not
- review candidates follow fixed rules and come out the same every time
- an attribute mapped in a live return is protected — never a candidate
- nothing is retired or deleted automatically
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.modules.student_record.models import (
    StudentCustomField, StudentCustomFieldAssessment, StudentCustomFieldUsage, StudentCustomValue,
)
from tests.integration.custom_attr_helpers import live_attribute
from tests.integration.test_custom_attr_governance_p1 import gov  # noqa: F401  (fixture)

P = "/api/v1/report-profiles"
A = "/api/v1/students/custom-attributes"


async def _live(c, hs, label, value=None):
    f = await live_attribute(c, hs["maker"], hs["admin1"], label=label, dataType="code")
    if value is not None:
        grid = (await c.get(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"])).json()
        r = await c.put(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"],
                        json={"values": [{"studentId": grid["rows"][0]["studentId"], "value": value}]})
        assert r.status_code == 200
    return f


async def _profile(c, h, year="2026/27", maps=()):
    p = (await c.post(P, headers=h, json={"code": "HESA_STUDENT", "name": "HESA", "academicYear": year})).json()
    for i, src in enumerate(("student.ref", *maps)):
        assert (await c.post(f"{P}/{p['id']}/fields", headers=h,
                             json={"targetField": f"F{i}", "sourceExpression": src})).status_code == 201
    return p


async def test_real_outputs_record_usage_and_previews_do_not(gov):
    c, hs, sm = gov
    f = await _live(c, hs, "Care leaver", "01")
    p = await _profile(c, hs["admin1"], maps=["custom.care_leaver"])

    assert (await c.get(f"{P}/{p['id']}/validate", headers=hs["admin1"])).status_code == 200
    async with sm() as s:
        assert (await s.execute(select(func.count()).select_from(StudentCustomFieldUsage))).scalar_one() == 0

    assert (await c.post(f"{P}/{p['id']}/generate", headers=hs["admin1"], json={})).status_code == 201
    assert (await c.get(f"{P}/{p['id']}/xml", headers=hs["admin1"])).status_code == 200
    usage = (await c.get(f"{A}/{f['id']}/usage", headers=hs["admin1"])).json()
    assert {(u["purpose"], u["count"]) for u in usage["byReturn"]} == {("generate", 1), ("download", 1)}
    assert usage["recent"][0]["profileCode"] == "HESA_STUDENT" and usage["recent"][0]["rowCount"] == 1

    h = (await c.get(f"{A}/{f['id']}/health", headers=hs["admin1"])).json()["health"]
    assert h["useCount"] == 2 and h["lastUsed"] and h["fillRate"] == 1.0
    assert h["protected"] is True and h["reviewCandidate"] is False


async def test_review_rules_protection_and_no_automatic_change(gov):
    c, hs, sm = gov
    unused = await _live(c, hs, "Unused flag")                     # unmapped, nobody has a value
    mapped = await _live(c, hs, "Mapped flag")                     # empty too, but a live return reads it
    healthy = await _live(c, hs, "Healthy flag", "Y")              # unmapped but filled and recent
    stale = await _live(c, hs, "Stale flag", "Y")                  # filled, but untouched for 2 years
    dropped = await _live(c, hs, "Dropped flag", "Y")              # its HESA field left the spec
    await _profile(c, hs["admin1"], maps=["custom.mapped_flag"])

    two_years_ago = datetime.now(timezone.utc) - timedelta(days=730)
    async with sm() as s:
        sid = uuid.UUID(stale["id"])
        await s.execute(update(StudentCustomField).where(StudentCustomField.id == sid)
                        .values(created_at=two_years_ago, decided_at=two_years_ago))
        await s.execute(update(StudentCustomValue).where(StudentCustomValue.custom_field_id == sid)
                        .values(updated_at=two_years_ago))
        s.add(StudentCustomFieldAssessment(
            custom_field_id=uuid.UUID(dropped["id"]), verdict="supported", specification="HESA_STUDENT 2025/26 v1",
            created_at=datetime.now(timezone.utc) + timedelta(seconds=5),
            result={"hesa": {"match": {"pack": "HESA_STUDENT", "field": "OLDCODE"}}},
        ))
        await s.commit()
        before = {f.key: f.status for f in (await s.execute(select(StudentCustomField))).scalars().all()}

    first = (await c.get(f"{A}/review-candidates", headers=hs["maker"])).json()
    second = (await c.get(f"{A}/review-candidates", headers=hs["maker"])).json()
    assert [x["key"] for x in first] == [x["key"] for x in second] == ["dropped_flag", "stale_flag", "unused_flag"]
    by = {x["key"]: x["health"] for x in first}
    assert any("Not mapped in any return" in r for r in by["unused_flag"]["reasons"])
    assert any("reporting cycle" in r for r in by["stale_flag"]["reasons"])
    assert any("HESA OLDCODE is no longer in" in r for r in by["dropped_flag"]["reasons"])

    dash = {x["key"]: x["health"] for x in (await c.get(f"{A}/dashboard", headers=hs["maker"])).json()}
    assert dash["mapped_flag"]["protected"] and not dash["mapped_flag"]["reviewCandidate"]
    assert dash["mapped_flag"]["recommendation"] == "keep — mapped in a live return"
    assert dash["healthy_flag"]["recommendation"] == "keep" and dash["healthy_flag"]["reasons"] == []

    # Nothing changed on its own: same attributes, same statuses.
    async with sm() as s:
        after = {f.key: f.status for f in (await s.execute(select(StudentCustomField))).scalars().all()}
    assert after == before and set(after.values()) == {"active"}

    # Putting a candidate under review is a person's decision; it then shows as under review.
    await c.post(f"{A}/{unused['id']}/review", headers=hs["maker"], json={"reason": "; ".join(by["unused_flag"]["reasons"])})
    dash = {x["key"]: x["health"] for x in (await c.get(f"{A}/dashboard", headers=hs["maker"])).json()}
    assert dash["unused_flag"]["recommendation"] == "under review"
    assert "unused_flag" not in [x["key"] for x in (await c.get(f"{A}/review-candidates", headers=hs["maker"])).json()]
    assert healthy["key"] == "healthy_flag" and mapped["key"] == "mapped_flag"


async def test_reader_cannot_see_usage(gov):
    c, hs, _ = gov
    f = await _live(c, hs, "Care leaver", "01")
    for path in ("dashboard", "review-candidates", f"{f['id']}/usage", f"{f['id']}/health"):
        assert (await c.get(f"{A}/{path}", headers=hs["reader"])).status_code == 403, path
