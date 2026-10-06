"""Custom attribute governance, Phase 3 — review, retire, restore; nothing is deleted.

What must hold (plan Phase 3 acceptance criteria):
- retiring keeps every value and every dated-history row
- a retired attribute can't be mapped, takes no values and isn't read by a return
- its values stay readable; restoring brings them back and is recorded
- an attribute still mapped in a live (not signed-off) profile can't be retired
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.modules.exports.models import ReportProfile
from app.modules.student_record.models import StudentCustomValue, StudentCustomValueHistory
from tests.integration.custom_attr_helpers import live_attribute
from tests.integration.test_custom_attr_governance_p1 import gov  # noqa: F401  (fixture)

A = "/api/v1/students/custom-attributes"


async def _live_with_value(c, hs, label="Care leaver", **kw):
    f = await live_attribute(c, hs["maker"], hs["admin1"], label=label, dataType="code", **kw)
    grid = (await c.get(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"])).json()
    sid = grid["rows"][0]["studentId"]
    r = await c.put(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"],
                    json={"values": [{"studentId": sid, "value": "01"}]})
    assert r.status_code == 200, r.text
    return f, sid


async def _profile(c, h):
    return (await c.post("/api/v1/report-profiles", headers=h, json={
        "code": "HESA_STUDENT", "name": "HESA Student Return", "academicYear": "2026/27"})).json()


async def test_retire_keeps_data_and_takes_it_out_of_every_live_path(gov):
    c, hs, sm = gov
    f, sid = await _live_with_value(c, hs, trackHistory=True)
    async with sm() as s:
        hist_before = (await s.execute(select(func.count()).select_from(StudentCustomValueHistory))).scalar_one()
    assert hist_before >= 1

    # Under review it is still live: enterable and mappable.
    r = await c.post(f"{A}/{f['id']}/review", headers=hs["maker"], json={"reason": "No longer in the 27/28 spec"})
    assert r.status_code == 200 and r.json()["status"] == "review"
    assert "custom.care_leaver" in (await c.get("/api/v1/report-profiles/record-schema", headers=hs["admin1"])).json()["paths"]

    # The maker can't retire (no approve right); an approver can.
    assert (await c.post(f"{A}/{f['id']}/retire", headers=hs["maker"], json={"reason": "x"})).status_code == 403
    assert (await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={})).status_code == 400
    r = await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={"reason": "Dropped from the spec"})
    assert r.status_code == 200 and r.json()["status"] == "retired"
    assert r.json()["usage"]["valueCount"] == 1

    # Out of every live path…
    schema = (await c.get("/api/v1/report-profiles/record-schema", headers=hs["admin1"])).json()
    assert "custom.care_leaver" not in schema["paths"]
    p = await _profile(c, hs["admin1"])
    m = await c.post(f"/api/v1/report-profiles/{p['id']}/fields", headers=hs["admin1"],
                     json={"targetField": "CARELEAVER", "sourceExpression": "custom.care_leaver"})
    assert m.status_code == 400 and "retired" in m.json()["error"]["message"]
    put = await c.put(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"],
                      json={"values": [{"studentId": sid, "value": "02"}]})
    assert put.status_code == 422
    assert all(x["key"] != "care_leaver" for x in (await c.get("/api/v1/students/custom-fields", headers=hs["admin1"])).json())

    # …but nothing is deleted, and the values are still readable.
    async with sm() as s:
        assert (await s.execute(select(func.count()).select_from(StudentCustomValue))).scalar_one() == 1
        hist_after = (await s.execute(select(func.count()).select_from(StudentCustomValueHistory))).scalar_one()
    assert hist_after == hist_before
    grid = (await c.get(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"])).json()
    assert grid["rows"][0]["value"] == "01"

    # Restore needs a reason and brings it all back.
    assert (await c.post(f"{A}/{f['id']}/restore", headers=hs["admin2"], json={})).status_code == 400
    assert (await c.post(f"{A}/{f['id']}/restore", headers=hs["maker"], json={"reason": "x"})).status_code == 403
    r = await c.post(f"{A}/{f['id']}/restore", headers=hs["admin2"], json={"reason": "Back in the 28/29 spec"})
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["usage"]["valueCount"] == 1
    assert "custom.care_leaver" in (await c.get("/api/v1/report-profiles/record-schema", headers=hs["admin1"])).json()["paths"]

    detail = (await c.get(f"{A}/{f['id']}", headers=hs["admin1"])).json()
    actions = [e["action"] for e in reversed(detail["events"])]
    assert actions[-3:] == ["review_started", "retired", "restored"]
    retired = next(e for e in detail["events"] if e["action"] == "retired")
    assert retired["detail"]["valuesRetained"] == 1 and retired["notes"] == "Dropped from the spec"


async def test_a_live_mapping_blocks_retirement_but_a_signed_off_one_does_not(gov):
    c, hs, sm = gov
    f, _ = await _live_with_value(c, hs)
    p = await _profile(c, hs["admin1"])
    m = (await c.post(f"/api/v1/report-profiles/{p['id']}/fields", headers=hs["admin1"],
                      json={"targetField": "CARELEAVER", "sourceExpression": "custom.care_leaver"})).json()
    await c.post(f"{A}/{f['id']}/review", headers=hs["maker"], json={"reason": "Check"})

    deps = (await c.get(f"{A}/{f['id']}/dependencies", headers=hs["admin1"])).json()
    assert deps == [{**deps[0], "targetField": "CARELEAVER", "signedOff": False, "blocksRetirement": True}]
    r = await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={"reason": "Gone"})
    assert r.status_code == 409 and "HESA_STUDENT 2026/27 (CARELEAVER)" in r.json()["error"]["message"]

    # Once that return is signed off it is a frozen snapshot: retiring no longer affects it.
    async with sm() as s:
        prof = await s.get(ReportProfile, __import__("uuid").UUID(p["id"]))
        prof.signed_off_at = datetime.now(timezone.utc)
        await s.commit()
    deps = (await c.get(f"{A}/{f['id']}/dependencies", headers=hs["admin1"])).json()
    assert deps[0]["signedOff"] is True and deps[0]["blocksRetirement"] is False
    assert (await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={"reason": "Gone"})).status_code == 200
    assert m["id"] == deps[0]["mappingId"]


async def test_review_rules(gov):
    c, hs, _ = gov
    f, _ = await _live_with_value(c, hs)
    # Only an active attribute can go under review; retire/restore need the right state.
    assert (await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={"reason": "x"})).status_code == 409
    assert (await c.post(f"{A}/{f['id']}/restore", headers=hs["admin1"], json={"reason": "x"})).status_code == 409
    assert (await c.post(f"{A}/{f['id']}/review", headers=hs["admin1"], json={})).status_code == 400
    assert (await c.post(f"{A}/{f['id']}/review", headers=hs["reader"], json={"reason": "x"})).status_code == 403
    assert (await c.post(f"{A}/{f['id']}/review", headers=hs["admin1"], json={"reason": "Low use"})).status_code == 200
    # Whoever started the review can't also retire it.
    own = await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={"reason": "x"})
    assert own.status_code == 403
    # Keep ends the review.
    r = await c.post(f"{A}/{f['id']}/keep", headers=hs["admin2"], json={"reason": "Still on the return"})
    assert r.status_code == 200 and r.json()["status"] == "active"


async def test_catalogue_shows_usage(gov):
    c, hs, _ = gov
    f, _ = await _live_with_value(c, hs)
    other = await live_attribute(c, hs["maker"], hs["admin1"], label="Refugee status", dataType="code")
    p = await _profile(c, hs["admin1"])
    await c.post(f"/api/v1/report-profiles/{p['id']}/fields", headers=hs["admin1"],
                 json={"targetField": "CARELEAVER", "sourceExpression": "custom.care_leaver"})
    await c.post(f"{A}/{other['id']}/review", headers=hs["admin1"], json={"reason": "Unused"})
    await c.post(f"{A}/{other['id']}/retire", headers=hs["admin2"], json={"reason": "Unused"})
    cat = {x["key"]: x for x in (await c.get(f"{A}/catalogue", headers=hs["maker"])).json()}
    assert cat["care_leaver"]["usage"] == {**cat["care_leaver"]["usage"], "valueCount": 1, "mappingCount": 1}
    assert cat["care_leaver"]["usage"]["lastValueUpdate"]
    assert cat["refugee_status"]["status"] == "retired" and cat["refugee_status"]["usage"]["valueCount"] == 0
    only_retired = (await c.get(f"{A}/catalogue?status=retired", headers=hs["maker"])).json()
    assert [x["key"] for x in only_retired] == ["refugee_status"]
    assert (await c.get(f"{A}/catalogue", headers=hs["reader"])).status_code == 403
