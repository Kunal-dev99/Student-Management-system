"""Taught (PGT / MSc) student lifecycle — ICR G1.

A second student lifecycle that reuses Person, enrolment, funding, documents, audit, portal and
row-scoping, but replaces the research thesis/viva/examination flow with
modules -> assessments -> dissertation -> award. Activated per programme via
``Programme.programme_type == taught``; research programmes are entirely unaffected (additive).
"""
