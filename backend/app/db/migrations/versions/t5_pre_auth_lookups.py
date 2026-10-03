"""Single-address SaaS: narrow "which institution?" lookups for requests that arrive before any
institution is known (sign-in, token refresh, password reset, referee links, email bounces).

On one shared address the institution can't come from the host, and row-level security is
fail-closed, so the restricted app login (pgr_app) couldn't even find the user who is signing in.
Instead of giving it a bypass, each of these functions answers exactly one question and returns
only institution ids (and a user id) - never a row of data:

  pgr_tenant_of_email(email)          -> the institution of the user with this sign-in email
  pgr_tenant_of_user(user_id)         -> the institution of this user
  pgr_tenant_of_reference(token_hash) -> the institution of this referee request
  pgr_tenants_with_email(email)       -> every institution with a user or person at this address

They run as the table owner (SECURITY DEFINER) with the owner's explicit bypass switched on only
for their one query and then put back, so the caller's transaction is left exactly as it was.
EXECUTE is revoked from PUBLIC and granted to pgr_app only, so reporting logins can't call them.

Revision ID: t5_pre_auth_lookups
Revises: t4_tenant_uniques
"""
from typing import Sequence, Union

from alembic import op

revision: str = "t5_pre_auth_lookups"
down_revision: Union[str, Sequence[str], None] = "t4_tenant_uniques"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTIONS = {
    "pgr_tenant_of_email(text)": ("uuid", "SELECT tenant_id INTO result FROM users WHERE email = lower(arg)"),
    "pgr_tenant_of_user(uuid)": ("uuid", "SELECT tenant_id INTO result FROM users WHERE id = arg"),
    "pgr_tenant_of_reference(text)": ("uuid", "SELECT tenant_id INTO result FROM reference_request WHERE token_hash = arg"),
}


def _scalar_fn(signature: str, returns: str, body: str) -> str:
    name, argtype = signature[:-1].split("(")
    return f"""
CREATE OR REPLACE FUNCTION {name}(arg {argtype}) RETURNS {returns}
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    prev text := current_setting('app.bypass_tenant', true);
    result {returns};
BEGIN
    PERFORM set_config('app.bypass_tenant', 'on', true);
    {body};
    PERFORM set_config('app.bypass_tenant', coalesce(prev, ''), true);
    RETURN result;
END
$fn$;"""


SET_FN = """
CREATE OR REPLACE FUNCTION pgr_tenants_with_email(arg text) RETURNS SETOF uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    prev text := current_setting('app.bypass_tenant', true);
BEGIN
    PERFORM set_config('app.bypass_tenant', 'on', true);
    RETURN QUERY
        SELECT tenant_id FROM users WHERE email = lower(arg)
        UNION
        SELECT tenant_id FROM person WHERE lower(email) = lower(arg);
    PERFORM set_config('app.bypass_tenant', coalesce(prev, ''), true);
END
$fn$;"""

ALL = list(FUNCTIONS) + ["pgr_tenants_with_email(text)"]


def upgrade() -> None:
    for signature, (returns, body) in FUNCTIONS.items():
        op.execute(_scalar_fn(signature, returns, body))
    op.execute(SET_FN)
    for signature in ALL:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    # pgr_app is created by deploy/provision_app_role.sql, which also grants these; grant here too
    # in case it already exists.
    grants = "".join(f"EXECUTE 'GRANT EXECUTE ON FUNCTION {s} TO pgr_app'; " for s in ALL)
    op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgr_app') THEN {grants}END IF; END $$")


def downgrade() -> None:
    for signature in ALL:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
