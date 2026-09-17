"""Row-scoping (``student_scope``) — pins which roles see all students, which see a subset, and
which see none. A silent regression here is a data leak (too broad) or an empty-app bug (too
narrow — this is what the ``dev`` role hit before the fix)."""
from __future__ import annotations

import uuid

from app.core.authorization import UNRESTRICTED_STUDENT_ROLES, student_scope
from app.core.principal import Principal


def _p(roles: list[str], person_id: uuid.UUID | None = None) -> Principal:
    return Principal(user_id=uuid.uuid4(), email="p@t", roles=roles, person_id=person_id)


def test_broad_roles_see_all_students():
    for role in ["Institution Administrator", "PGR Administrator", "Registry"]:
        assert student_scope(_p([role])).kind == "all", f"{role} should be unrestricted"


def test_dev_role_sees_all_students():
    """The ``dev`` role has wildcard permissions plus ``platform.configure``; it needs to see the
    same rows as an admin, otherwise every student-scoped endpoint returns 0 rows for it. Fixed
    once — this test keeps it fixed."""
    assert student_scope(_p(["dev"])).kind == "all"
    assert "dev" in UNRESTRICTED_STUDENT_ROLES


def test_supervisor_is_scoped_to_their_own_supervisees():
    pid = uuid.uuid4()
    scope = student_scope(_p(["Supervisor"], person_id=pid))
    assert scope.kind == "supervisor" and scope.person_id == pid


def test_supervisor_without_a_person_record_sees_nothing():
    # A Supervisor account with no linked person can't be resolved to any supervisees, so the
    # only safe answer is "none" — never "all".
    assert student_scope(_p(["Supervisor"], person_id=None)).kind == "none"


def test_student_sees_only_their_own_record():
    pid = uuid.uuid4()
    scope = student_scope(_p(["Student"], person_id=pid))
    assert scope.kind == "self" and scope.person_id == pid


def test_a_role_with_no_scope_sees_no_students():
    assert student_scope(_p(["Some Unknown Role"])).kind == "none"
