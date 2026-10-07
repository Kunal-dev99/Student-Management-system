"""Custom attribute governance, Phase 2 — is a requested attribute needed?

What must hold (plan Phase 2 acceptance criteria):
- a core-record equivalent is identified (and approving it anyway needs a reason)
- a duplicate custom attribute is identified
- the HESA requirement is identified when the spec has it — including from an accepted spec version
- the assessment is stored, shown with the request, and can be re-run
- the check failing never blocks the request
"""
from __future__ import annotations

from sqlalchemy import select

from app.modules.exports.models import SpecVersionStatus, StatutorySpecVersion
from app.modules.student_record.models import StudentCustomFieldAssessment
from tests.integration.test_custom_attr_governance_p1 import REQ, gov  # noqa: F401  (fixture)


async def _request(c, h, label, reason="For the HESA return.", data_type="string"):
    r = await c.post(REQ, headers=h, json={"label": label, "reason": reason, "dataType": data_type})
    assert r.status_code == 201, r.text
    return r.json()


async def test_core_equivalent_is_flagged_and_needs_an_override_reason(gov):
    c, hs, _ = gov
    f = await _request(c, hs["maker"], "Nationality")
    a = f["assessment"]
    assert a["verdict"] == "duplicate"
    assert a["coreMatches"][0]["path"] == "person.nationality" and a["coreMatches"][0]["match"] == "exact"
    assert any("person.nationality" in fl for fl in a["flags"])
    # The approver can't wave it through without saying why.
    r = await c.post(f"{REQ}/{f['id']}/approve", headers=hs["admin1"], json={})
    assert r.status_code == 400 and "duplicate" in r.json()["error"]["message"]
    r = await c.post(f"{REQ}/{f['id']}/approve", headers=hs["admin1"],
                     json={"reason": "Need the second nationality, which the core field doesn't hold"})
    assert r.status_code == 200 and r.json()["status"] == "approved"


async def test_hesa_requirement_and_suggested_type(gov):
    c, hs, _ = gov
    f = await _request(c, hs["maker"], "Ethnicity", data_type="string")
    a = f["assessment"]
    assert a["verdict"] == "supported"
    assert a["hesa"]["match"]["field"] == "ETHNIC"
    assert a["hesa"]["requirement"] == "required"
    assert a["hesa"]["specification"] == "HESA_STUDENT 2026/27 v1"
    # A coded HESA field suggests the code type and its coding frame.
    assert a["suggested"]["dataType"] == "code" and "10" in a["suggested"]["allowedValues"]
    assert any("suggests 'code'" in fl for fl in a["flags"])


async def test_a_hesa_code_named_in_the_reason_is_a_direct_match(gov):
    c, hs, _ = gov
    f = await _request(c, hs["maker"], "Gender identity marker", reason="Feeds SEXID on the student return.")
    assert f["assessment"]["hesa"]["match"]["field"] == "SEXID"
    assert f["assessment"]["hesa"]["match"]["how"] == "named"


async def test_custom_duplicate_and_no_hesa_basis(gov):
    c, hs, _ = gov
    first = await _request(c, hs["maker"], "Locker number", reason="Facilities report")
    assert first["assessment"]["verdict"] == "no_hesa_basis"
    assert first["assessment"]["suggested"]["dataType"] == "number"
    # Same meaning, different key: caught as a duplicate of the pending request.
    second = await _request(c, hs["maker"], "Locker numbers", reason="Facilities report")
    m = second["assessment"]["customMatches"][0]
    assert m["key"] == "locker_number" and m["match"] == "exact" and m["status"] == "pending"
    assert second["assessment"]["verdict"] == "duplicate"


async def test_assessment_is_stored_and_rerunnable(gov):
    c, hs, sm = gov
    f = await _request(c, hs["maker"], "Ethnicity")
    got = await c.get(f"{REQ}/{f['id']}/assessment", headers=hs["admin1"])
    assert got.status_code == 200 and got.json()["verdict"] == "supported"
    again = await c.post(f"{REQ}/{f['id']}/assess", headers=hs["admin1"])
    assert again.status_code == 200 and again.json()["id"] != got.json()["id"]
    async with sm() as s:
        n = len((await s.execute(select(StudentCustomFieldAssessment))).scalars().all())
    assert n == 2
    detail = (await c.get(f"{REQ}/{f['id']}", headers=hs["admin1"])).json()
    assert [e["action"] for e in reversed(detail["events"])] == ["requested", "assessed", "assessed"]
    # A reader without governance rights can't see or run it.
    assert (await c.get(f"{REQ}/{f['id']}/assessment", headers=hs["reader"])).status_code == 403


async def test_preview_check_saves_nothing(gov):
    c, hs, sm = gov
    r = await c.post(f"{REQ}/check", headers=hs["maker"], json={"label": "Date of birth"})
    assert r.status_code == 200
    assert r.json()["verdict"] == "duplicate"
    assert r.json()["hesa"]["match"]["field"] == "BIRTHDTE"
    assert (await c.get(REQ, headers=hs["maker"])).json() == []
    async with sm() as s:
        assert (await s.execute(select(StudentCustomFieldAssessment))).first() is None


async def test_a_failing_check_does_not_block_the_request(gov, monkeypatch):
    c, hs, _ = gov
    import app.modules.student_record.custom_attr_assessment as mod

    async def boom(*a, **kw):
        raise RuntimeError("spec store unavailable")

    monkeypatch.setattr(mod, "assess", boom)
    r = await c.post(REQ, headers=hs["maker"], json={"label": "Ethnicity", "reason": "HESA"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending" and r.json()["assessment"] is None


async def test_an_accepted_spec_version_is_used(gov):
    c, hs, sm = gov
    async with sm() as s:
        s.add(StatutorySpecVersion(
            pack_code="HESA_STUDENT", academic_year="2027/28", version=2, name="HESA Student",
            status=SpecVersionStatus.active, rules=[], disabled_rule_keys=[],
            fields=[{"field": "CARELEAVER", "description": "Care leaver indicator",
                     "allowed": ["01", "02", "03", "98"], "source": ""}],
        ))
        await s.commit()
    f = await _request(c, hs["maker"], "Care leaver")
    hesa = f["assessment"]["hesa"]
    assert hesa["match"]["field"] == "CARELEAVER"
    assert hesa["specification"] == "HESA_STUDENT 2027/28 v2"
    # The spec endpoints show the same effective pack.
    specs = (await c.get("/api/v1/hesa/specifications", headers=hs["maker"])).json()
    assert {"HESA_STUDENT:2026-27", "HESA_STUDENT:2027-28"} <= {s["id"] for s in specs}
    fields = (await c.get("/api/v1/hesa/specifications/HESA_STUDENT:2027-28/fields", headers=hs["maker"])).json()
    assert fields["version"] == 2 and fields["fields"][0]["field"] == "CARELEAVER"
    one = await c.get("/api/v1/hesa/specifications/HESA_STUDENT:2026-27/fields/ethnic", headers=hs["maker"])
    assert one.status_code == 200 and one.json()["field"] == "ETHNIC"
    assert (await c.get("/api/v1/hesa/specifications/NOPE:2026-27/fields",
                        headers=hs["maker"])).status_code == 404
