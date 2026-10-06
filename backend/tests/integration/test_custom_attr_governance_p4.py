"""Custom attribute governance, Phase 4 — custom attributes as governed mapping sources.

What must hold (plan Phase 4 acceptance criteria):
- only active attributes can be selected (the profile's picker offers nothing else)
- mapping a retired / never-live attribute is rejected, and can be checked before saving
- the profile's picker is HESA-aware: it says which attribute was requested for a field of
  this return
- an obsolete mapping (carried forward to an attribute that has since been retired) is detected,
  reported on clone, and blocks sign-off until re-mapped
- core-field mappings work exactly as before
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.modules.exports.models import ReportProfile
from tests.integration.custom_attr_helpers import live_attribute
from tests.integration.test_custom_attr_governance_p1 import REQ, gov  # noqa: F401  (fixture)

P = "/api/v1/report-profiles"
A = "/api/v1/students/custom-attributes"


async def _profile(c, h, year="2026/27"):
    return (await c.post(P, headers=h, json={"code": "HESA_STUDENT", "name": "HESA Student",
                                             "academicYear": year})).json()


async def _map(c, h, pid, target, src, **kw):
    return await c.post(f"{P}/{pid}/fields", headers=h, json={"targetField": target, "sourceExpression": src, **kw})


async def test_profile_picker_is_hesa_aware_and_live_only(gov):
    c, hs, _ = gov
    eth = await live_attribute(c, hs["maker"], hs["admin1"], label="Ethnic origin", dataType="code",
                               reason="Feeds ETHNIC on the student return.")
    await live_attribute(c, hs["maker"], hs["admin1"], label="Locker number", dataType="number",
                         reason="Facilities report")
    await c.post(REQ, headers=hs["maker"], json={"label": "Pending thing", "reason": "x"})
    p = await _profile(c, hs["admin1"])

    schema = (await c.get(f"{P}/{p['id']}/record-schema", headers=hs["admin1"])).json()
    custom = next(g for g in schema["groups"] if g["root"] == "custom")["fields"]
    assert [f["path"] for f in custom] == ["custom.ethnic_origin", "custom.locker_number"]   # relevant first
    first = custom[0]
    assert first["hesaField"] == "ETHNIC" and first["hesaRelevant"] is True and first["type"] == "code"
    assert custom[1]["hesaRelevant"] is False
    assert "custom.pending_thing" not in schema["paths"]
    assert "student.ref" in schema["paths"]            # the core catalogue is all still there

    assert (await _map(c, hs["admin1"], p["id"], "ETHNIC", "custom.ethnic_origin")).status_code == 201
    schema = (await c.get(f"{P}/{p['id']}/record-schema", headers=hs["admin1"])).json()
    mapped = next(f for f in next(g for g in schema["groups"] if g["root"] == "custom")["fields"]
                  if f["path"] == "custom.ethnic_origin")
    assert mapped["mappedAs"] == ["ETHNIC"]
    used = (await c.get(f"{P}/{p['id']}/custom-attributes", headers=hs["admin1"])).json()
    assert [u["customKey"] for u in used["used"]] == ["ethnic_origin"] and used["obsoleteCount"] == 0
    assert used["unusedLive"] == ["locker_number"]
    assert eth["key"] == "ethnic_origin"


async def test_validate_before_saving(gov):
    c, hs, _ = gov
    await live_attribute(c, hs["maker"], hs["admin1"], label="Ethnic origin", dataType="string",
                         reason="Feeds ETHNIC on the student return.")
    await c.post(REQ, headers=hs["maker"], json={"label": "Pending thing", "reason": "x"})
    p = await _profile(c, hs["admin1"])
    existing = (await _map(c, hs["admin1"], p["id"], "OWNSTU", "student.ref")).json()

    async def check(**body):
        r = await c.post(f"{P}/{p['id']}/fields/validate", headers=hs["admin1"], json=body)
        assert r.status_code == 200, r.text
        return r.json()

    ok = await check(targetField="HUSID", sourceExpression="student.husid")
    assert ok["valid"] and ok["errors"] == [] and ok["spec"]["field"] == "HUSID"
    # Unknown core paths stay allowed (compatibility) but are flagged.
    odd = await check(targetField="HUSID", sourceExpression="student.nope")
    assert odd["valid"] and any("record catalogue" in w for w in odd["warnings"])
    # A request that never went live can't be mapped.
    pend = await check(targetField="X1", sourceExpression="custom.pending_thing")
    assert not pend["valid"] and "pending" in pend["errors"][0]
    missing = await check(targetField="X1", sourceExpression="custom.no_such")
    assert not missing["valid"] and "no custom attribute" in missing["errors"][0]
    # HESA compatibility: a coded field fed by a text attribute, and a field it wasn't requested for.
    sex = await check(targetField="SEXID", sourceExpression="custom.ethnic_origin")
    assert sex["valid"]
    assert any("coded field" in w for w in sex["warnings"])
    assert any("requested for HESA ETHNIC, not SEXID" in w for w in sex["warnings"])
    # Duplicate target, unless it is the mapping being edited; a bad transform.
    dup = await check(targetField="OWNSTU", sourceExpression="student.ref")
    assert not dup["valid"] and "already mapped" in dup["errors"][0]
    same = await check(targetField="OWNSTU", sourceExpression="student.ref", mappingId=existing["id"])
    assert same["valid"]
    bad = await check(targetField="Y", sourceExpression="student.ref", transform="nonsense")
    assert not bad["valid"]
    # Not in this year's spec → a warning, not an error.
    assert any("isn't a field" in w for w in (await check(targetField="LOCAL1", sourceExpression="student.ref"))["warnings"])


async def test_obsolete_mapping_is_detected_on_clone_and_blocks_sign_off(gov):
    c, hs, sm = gov
    f = await live_attribute(c, hs["maker"], hs["admin1"], label="Care leaver", dataType="code")
    p = await _profile(c, hs["admin1"])
    assert (await _map(c, hs["admin1"], p["id"], "OWNSTU", "student.ref")).status_code == 201
    assert (await _map(c, hs["admin1"], p["id"], "CARELEAVER", "custom.care_leaver")).status_code == 201
    # Last year's return is signed off, so retiring the attribute is allowed (Phase 3)…
    async with sm() as s:
        prof = await s.get(ReportProfile, uuid.UUID(p["id"]))
        prof.signed_off_at = datetime.now(timezone.utc)
        await s.commit()
    await c.post(f"{A}/{f['id']}/review", headers=hs["maker"], json={"reason": "Dropped"})
    assert (await c.post(f"{A}/{f['id']}/retire", headers=hs["admin1"], json={"reason": "Dropped"})).status_code == 200

    # …but carrying that return forward must not silently keep a dead mapping.
    clone = await c.post(f"{P}/{p['id']}/clone", headers=hs["admin1"], json={"academicYear": "2027/28"})
    assert clone.status_code == 201, clone.text
    nxt = clone.json()
    assert [o["targetField"] for o in nxt["obsoleteMappings"]] == ["CARELEAVER"]
    assert "retired" in nxt["obsoleteMappings"][0]["reason"]

    deps = {d["targetField"]: d for d in (await c.get(f"{P}/{nxt['id']}/dependencies", headers=hs["admin1"])).json()}
    assert deps["OWNSTU"]["kind"] == "core" and not deps["OWNSTU"]["obsolete"]
    assert deps["CARELEAVER"]["kind"] == "custom" and deps["CARELEAVER"]["obsolete"]
    comp = (await c.get(f"{P}/{nxt['id']}/compile", headers=hs["admin1"])).json()
    assert comp["signOffReady"] is False and comp["obsoleteMappings"][0]["targetField"] == "CARELEAVER"
    so = await c.post(f"{P}/{nxt['id']}/sign-off", headers=hs["admin1"], json={})
    assert so.status_code == 422 and "CARELEAVER reads custom.care_leaver" in so.json()["error"]["message"]
    used = (await c.get(f"{P}/{nxt['id']}/custom-attributes", headers=hs["admin1"])).json()
    assert used["obsoleteCount"] == 1

    # Re-mapping the field clears it.
    r = await c.patch(f"{P}/{nxt['id']}/fields/{deps['CARELEAVER']['mappingId']}", headers=hs["admin1"],
                      json={"sourceExpression": "student.status"})
    assert r.status_code == 200, r.text
    comp = (await c.get(f"{P}/{nxt['id']}/compile", headers=hs["admin1"])).json()
    assert comp["obsoleteMappings"] == []
    # Re-pointing a mapping AT a retired attribute is refused.
    r = await c.patch(f"{P}/{nxt['id']}/fields/{deps['CARELEAVER']['mappingId']}", headers=hs["admin1"],
                      json={"sourceExpression": "custom.care_leaver"})
    assert r.status_code == 400 and "retired" in r.json()["error"]["message"]
