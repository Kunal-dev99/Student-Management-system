"""CB-A — Classifier coverage: for each intent, in-vocab phrasings win, cross-intent phrasings
either lose or route to the right competitor."""
from __future__ import annotations

import pytest

from app.modules.fuzzy.classifier import CONFIDENT_THRESHOLD, classify, decide
from app.modules.fuzzy.intents import registry
from app.modules.fuzzy.normaliser import normalise


def _classify(query: str):
    tokens = normalise(query).tokens
    return classify(tokens, entities=[])


@pytest.mark.parametrize("query,expected_intent", [
    # overdue vs held — distinguished by core tokens
    ("who's late paying", "overdue_payments"),
    ("outstanding stipends", "overdue_payments"),
    ("chase up unpaid payments", "overdue_payments"),
    ("held payments", "held_payments"),
    ("finance rejections", "held_payments"),
    ("blocked stipends", "held_payments"),
    # at-risk
    ("who is at risk", "at_risk_students"),
    ("risky cohort", "at_risk_students"),
    ("students flagged red", "at_risk_students"),
    # student summary requires the "summary" family of words
    ("overview of tom fisher", "student_summary"),
    ("state of alice", "student_summary"),
    # workforce
    ("supervisor workload", "supervisor_workforce"),
    ("who is over capacity", "supervisor_workforce"),
    # cashflow (umbrella)
    ("cashflow this quarter", "funding_cashflow"),
    ("financial summary", "funding_cashflow"),
    ("budget position", "funding_cashflow"),
    # my tasks
    ("my tasks", "my_tasks"),
    ("what's in my inbox", "my_tasks"),
    # analytics
    ("show analytics", "analytics_overview"),
    ("completion rate", "analytics_overview"),
    # signoffs
    ("pending sign-offs", "pending_signoffs"),
    ("statutory signoffs open", "pending_signoffs"),
    # meetings
    ("supervision meetings overdue", "supervision_meetings_overdue"),
    ("students with no meeting in 90 days", "supervision_meetings_overdue"),
    # reconciliation drift
    ("unreconciled payments", "paid_without_reference"),
    ("paid without a finance reference", "paid_without_reference"),
    # navigate
    ("go to funding", "navigate"),
    ("open the workforce page", "navigate"),
    # help
    ("help", "help"),
    ("what can i ask", "help"),
    # milestones due / overdue
    ("milestones due", "milestones_due"),
    ("upcoming annual reviews", "milestones_due"),
    ("overdue milestones", "milestones_overdue"),
    ("missed progression reviews", "milestones_overdue"),
    # viva
    ("vivas pending", "viva_pending"),
    ("upcoming vivas", "viva_pending"),
    # corrections
    ("corrections open", "corrections_open"),
    ("outstanding thesis corrections", "corrections_open"),
    # applications / opportunities / offers
    ("new applications", "applications_new"),
    ("fresh applicants", "applications_new"),
    ("open opportunities", "opportunities_open"),
    ("current vacancies", "opportunities_open"),
    ("conditional offers", "offers_conditional"),
    ("offers with unmet conditions", "offers_conditional"),
    # assignment requests
    ("pending assignment requests", "assignment_requests"),
    ("supervisor assignment queue", "assignment_requests"),
    # funding gap
    ("funding gaps", "funding_gap"),
    ("students with expiring funding", "funding_gap"),
    # sabbatical conflicts
    ("sabbatical conflicts", "sabbatical_conflicts"),
    ("supervisors on leave with vivas coming up", "sabbatical_conflicts"),
    # admin
    ("dead letters", "integration_failures"),
    ("failed webhook messages", "integration_failures"),
    ("recent audit log", "audit_recent"),
    ("audit trail", "audit_recent"),
    # CB-B — write intents
    ("approve this payment", "approve_payment"),
    ("approve the stipend", "approve_payment"),
    ("put this payment on hold", "hold_payment"),
    ("halt alice's payment", "hold_payment"),
    ("freeze this payment", "hold_payment"),
    ("sign off alice's statutory record", "submit_signoff"),
    ("submit sign-off for alice", "submit_signoff"),
])
def test_classifier_picks_the_right_intent(query, expected_intent):
    matches = _classify(query)
    assert matches, f"no matches at all for {query!r}"
    top = matches[0]
    assert top.intent.name == expected_intent, (
        f"query={query!r} → got {top.intent.name} (score={top.score:.2f}) instead of {expected_intent}. "
        f"Top 3: {[(m.intent.name, round(m.score,2)) for m in matches[:3]]}"
    )


def test_confident_queries_pass_the_threshold():
    matches = _classify("held payments this quarter")
    assert matches and matches[0].score >= CONFIDENT_THRESHOLD


def test_off_topic_returns_not_understood():
    matches = _classify("what's the weather like")
    kind, _ = decide(matches)
    assert kind == "not_understood"


def test_ambiguous_returns_clarify_or_answer():
    """A vague query like 'payments' shouldn't confidently pick one — either clarify or nothing."""
    matches = _classify("payments")
    kind, _ = decide(matches)
    assert kind in {"clarify", "not_understood"}


def test_registry_has_seed_intents():
    names = {i.name for i in registry().all()}
    seeds = {
        "overdue_payments", "held_payments", "at_risk_students", "student_summary",
        "supervisor_workforce", "funding_cashflow", "my_tasks", "analytics_overview",
        "pending_signoffs", "supervision_meetings_overdue", "paid_without_reference",
        "navigate", "help",
        # CB-A expansion
        "milestones_due", "milestones_overdue", "viva_pending", "corrections_open",
        "applications_new", "opportunities_open", "offers_conditional",
        "assignment_requests", "funding_gap", "sabbatical_conflicts",
        "integration_failures", "audit_recent",
        # CB-B write intents
        "approve_payment", "hold_payment", "submit_signoff",
    }
    missing = seeds - names
    assert not missing, f"missing seed intents: {missing}"
