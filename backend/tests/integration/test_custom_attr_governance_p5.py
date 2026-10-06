"""Custom attribute governance, Phase 5 — a return loads only the custom attributes it maps.

What must hold (plan Phase 5 acceptance criteria):
- unrelated, unmapped and retired custom attributes are not materialised
- the return is identical to the one produced by loading every attribute (the old behaviour)
- dated (effective-dated) custom values still resolve to the value in force for the period
- what was loaded is observable
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

import app.modules.exports.statutory as statutory
from app.modules.exports.statutory import StatutoryEngine
from app.modules.student_record.custom_fields import CustomFieldService
from app.modules.student_record.fact_history import CustomValueHistoryService
from app.modules.student_record.models import Student, StudentCustomField, StudentCustomValue
from tests.integration.test_custom_attr_governance_p1 import gov  # noqa: F401  (fixture)

P = "/api/v1/report-profiles"


async def _setup(sm):
    """Five live attributes with a value for the student, one of them dated with a mid-year
    change, plus one retired attribute that a (carried-forward) mapping still names."""
    async with sm() as s:
        sid = (await s.execute(select(Student.id))).scalar_one()
        fields = {}
        for key, status, dated in (("care_leaver", "active", False), ("research_council", "active", True),
                                   ("locker", "active", False), ("parking", "active", False),
                                   ("canteen", "review", False), ("old_flag", "retired", False)):
            f = StudentCustomField(key=key, label=key.replace("_", " "), data_type="code", reason="t",
                                   status=status, track_history=dated)
            s.add(f)
            await s.flush()
            fields[key] = f
            cv = StudentCustomValue(custom_field_id=f.id, student_id=sid, value=None if dated else f"{key}-v")
            s.add(cv)
            await s.flush()
            if dated:
                hist = CustomValueHistoryService(s)
                await hist.change(cv, "MRC", effective_from=date(2026, 10, 1))
                await hist.change(cv, "CRUK", effective_from=date(2027, 3, 1))
        await s.commit()
        return sid, fields


async def _profile_with(c, h, sources):
    p = (await c.post(P, headers=h, json={"code": "HESA_STUDENT", "name": "HESA", "academicYear": "2026/27"})).json()
    for i, src in enumerate(sources):
        r = await c.post(f"{P}/{p['id']}/fields", headers=h, json={"targetField": f"F{i}", "sourceExpression": src})
        assert r.status_code == 201, r.text
    return p


async def test_only_mapped_live_attributes_are_loaded(gov):
    c, hs, sm = gov
    _, fields = await _setup(sm)
    p = await _profile_with(c, hs["admin1"], ["student.ref", "custom.care_leaver", "custom.research_council"])
    # A carried-forward mapping to the retired attribute (added behind the API's back, the way a
    # clone of an old profile would have it).
    async with sm() as s:
        from app.modules.exports.models import ReportFieldMapping
        s.add(ReportFieldMapping(profile_id=uuid.UUID(p["id"]), target_field="F9", position=9,
                                 source_expression="custom.old_flag"))
        await s.commit()

    async with sm() as s:
        eng = StatutoryEngine(s)
        gen = await eng.generate(uuid.UUID(p["id"]), include_records=True)
    rt = gen["runtime"]
    assert rt["customScope"] == "profile"
    assert rt["customKeysLoaded"] == ["care_leaver", "research_council"]
    assert rt["customKeysSkipped"] == ["old_flag"]               # retired: not read
    assert rt["customValuesLoaded"] == 2                          # locker/parking/canteen untouched
    assert all(set(r["custom"]) == {"care_leaver", "research_council"} for r in gen["records"])
    # The dated attribute reads the value in force (no snapshot date: as at today, Oct 2026 → MRC;
    # the CRUK change from March 2027 hasn't happened yet).
    assert gen["rows"][0][1:3] == ["care_leaver-v", "MRC"]
    # Also on the HTTP response, so it's observable without logs.
    r = await c.post(f"{P}/{p['id']}/generate", headers=hs["admin1"], json={})
    assert r.json()["runtime"]["customKeysLoaded"] == ["care_leaver", "research_council"]


async def test_a_return_without_custom_mappings_loads_none(gov):
    c, hs, sm = gov
    await _setup(sm)
    p = await _profile_with(c, hs["admin1"], ["student.ref", "person.nationality"])
    async with sm() as s:
        gen = await StatutoryEngine(s).generate(uuid.UUID(p["id"]), include_records=True)
    assert gen["runtime"]["customKeysLoaded"] == [] and gen["runtime"]["customValuesLoaded"] == 0
    assert gen["records"][0]["custom"] == {}


async def test_output_is_identical_to_loading_every_attribute(gov, monkeypatch):
    c, hs, sm = gov
    await _setup(sm)
    sources = ["student.ref", "custom.care_leaver", "custom.research_council", "custom.canteen"]
    p = await _profile_with(c, hs["admin1"], sources)
    async with sm() as s:
        scoped = await StatutoryEngine(s).generate(uuid.UUID(p["id"]), as_at=date(2026, 12, 31))
    # The pre-Phase-5 behaviour: load every live attribute for every student.
    monkeypatch.setattr(statutory, "mapped_custom_keys", lambda mappings: None)
    async with sm() as s:
        full = await StatutoryEngine(s).generate(uuid.UUID(p["id"]), as_at=date(2026, 12, 31))
    assert full["runtime"]["customScope"] == "all-live"
    assert full["runtime"]["customValuesLoaded"] > scoped["runtime"]["customValuesLoaded"]
    assert scoped["header"] == full["header"]
    assert scoped["rows"] == full["rows"]
    assert scoped["validation"]["errors"] == full["validation"]["errors"]
    # As at December the dated attribute reads MRC (the March change hasn't happened yet).
    assert scoped["rows"][0][2] == "MRC"


async def test_listing_attributes_does_not_load_their_values(gov):
    c, hs, sm = gov
    await _setup(sm)
    async with sm() as s:
        fields = await CustomFieldService(s).list_fields()
        # The relationship is never loaded through the definition (it used to be selectin).
        assert all(f.values == [] for f in fields)
        assert (await s.execute(select(StudentCustomValue))).scalars().all()   # the values exist
