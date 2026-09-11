"""Identity business rules: authentication, token issue/refresh, principal resolution.

Arch §12.1. Refresh is stateless (signed JWT) for the MVP; hashed-store revocation is a
follow-up hardening task (see plan). Authorization fails closed.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError

from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import AuthError
from app.core.principal import Principal
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_opaque_token,
    hash_opaque,
    hash_password,
    verify_password,
)
from app.modules.identity.models import User
from app.modules.identity.repository import IdentityRepository

logger = logging.getLogger("pgr.auth")


def _utc_from_ts(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime (SQLite drops tz) to UTC-aware for safe comparison."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _permissions_for(user: User) -> list[str]:
    codes: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            codes.add(perm.code)
    return sorted(codes)


def _principal_from_user(user: User) -> Principal:
    return Principal(
        user_id=user.id,
        email=user.email,
        person_id=user.person_id,
        roles=sorted(r.name for r in user.roles),
        permissions=_permissions_for(user),
        # MT-1 — carry tenant into the principal so downstream middleware / RLS
        # can scope queries. `tenant_id` is nullable during Phase 1.
        tenant_id=getattr(user, "tenant_id", None),
    )


def _claims_for(principal: Principal) -> dict:
    return {
        "email": principal.email,
        "personId": str(principal.person_id) if principal.person_id else None,
        "roles": principal.roles,
        "permissions": principal.permissions,
        # MT-1 — new claim. Older tokens without it decode fine (see the decoder).
        "tenantId": str(principal.tenant_id) if principal.tenant_id else None,
    }


class IdentityService:
    def __init__(self, repo: IdentityRepository) -> None:
        self.repo = repo

    async def _issue_refresh(self, user_id: uuid.UUID) -> str:
        """Mint a refresh JWT and record its jti so it can later be revoked (arch §12.1)."""
        token = create_refresh_token(str(user_id))
        claims = decode_token(token, "refresh")
        self.repo.add_refresh_token(user_id, claims["jti"], _utc_from_ts(claims["exp"]))
        return token

    async def authenticate(self, email: str, password: str) -> tuple[str, str, Principal]:
        settings = get_settings()
        user = await self.repo.get_user_by_email(email)
        if user is None or not user.is_active or not user.password_hash:
            raise AuthError("Invalid email or password")
        # Lockout gate (arch §12.1): reject while locked, without revealing account state further.
        now = datetime.now(timezone.utc)
        locked_until = _aware(user.locked_until)
        if locked_until is not None and locked_until > now:
            raise AuthError("Account temporarily locked. Try again later.")
        if not verify_password(password, user.password_hash):
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_count = 0
                logger.warning("account locked after repeated failures: %s", user.email)
            await self.repo.session.commit()
            raise AuthError("Invalid email or password")
        # Success: reset counters, stamp login, issue tokens.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        principal = _principal_from_user(user)
        subject = str(user.id)
        refresh = await self._issue_refresh(user.id)
        await self.repo.session.commit()
        return create_access_token(subject, _claims_for(principal)), refresh, principal

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        try:
            claims = decode_token(refresh_token, "refresh")
        except JWTError as exc:
            raise AuthError("Invalid or expired refresh token") from exc
        subject = claims["sub"]
        # Revocation check: the jti must exist, be unrevoked, and unexpired (arch §12.1).
        stored = await self.repo.get_refresh_token(claims.get("jti", ""))
        now = datetime.now(timezone.utc)
        if stored is None or stored.revoked_at is not None or _aware(stored.expires_at) <= now:
            raise AuthError("Refresh token is no longer valid")
        user = await self.repo.get_user_by_id(uuid.UUID(subject))
        if user is None or not user.is_active:
            raise AuthError("User no longer active")
        # Rotate: revoke the presented token, issue a fresh pair.
        await self.repo.revoke_refresh_token(stored.jti)
        new_refresh = await self._issue_refresh(user.id)
        await self.repo.session.commit()
        return create_access_token(subject, _claims_for(_principal_from_user(user))), new_refresh

    async def logout(self, refresh_token: str) -> None:
        try:
            claims = decode_token(refresh_token, "refresh")
        except JWTError:
            return  # already useless; nothing to revoke
        await self.repo.revoke_refresh_token(claims.get("jti", ""))
        await self.repo.session.commit()

    async def logout_all(self, user_id: uuid.UUID) -> int:
        count = await self.repo.revoke_all_refresh_tokens(user_id)
        await self.repo.session.commit()
        return count

    async def request_password_reset(self, email: str) -> None:
        """Always succeeds silently (no account enumeration). Emails a reset link if the user exists."""
        settings = get_settings()
        user = await self.repo.get_user_by_email(email)
        if user is None or not user.is_active:
            return
        raw = generate_opaque_token()
        expires = datetime.now(timezone.utc) + timedelta(seconds=settings.password_reset_ttl_seconds)
        self.repo.add_reset_token(user.id, hash_opaque(raw), expires)
        await self.repo.session.commit()
        link = f"{settings.app_base_url}/reset-password?token={raw}"
        minutes = settings.password_reset_ttl_seconds // 60
        text_body = (
            f"You have been invited to the PGR Platform.\n\n"
            f"Set your password using this link (valid for {minutes} minutes):\n\n"
            f"{link}\n\n"
            f"If you did not expect this email, you can ignore it."
        )
        html_body = f"""\
<!doctype html>
<html><body style="margin:0;padding:24px;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#111;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e5e5;border-radius:8px;">
    <tr><td style="padding:32px 32px 8px 32px;">
      <h1 style="margin:0 0 16px 0;font-size:20px;font-weight:600;">Welcome to the PGR Platform</h1>
      <p style="margin:0 0 16px 0;font-size:14px;line-height:1.5;color:#333;">
        An administrator has invited you. Use the button below to set your password and sign in.
      </p>
    </td></tr>
    <tr><td style="padding:8px 32px 24px 32px;">
      <a href="{link}" style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;padding:12px 20px;border-radius:6px;font-size:14px;font-weight:500;">
        Set your password
      </a>
      <p style="margin:20px 0 0 0;font-size:12px;color:#666;line-height:1.5;">
        This link is valid for {minutes} minutes. If the button does not work, copy this URL into your browser:
      </p>
      <p style="margin:8px 0 0 0;font-size:12px;color:#0f172a;word-break:break-all;">
        {link}
      </p>
    </td></tr>
    <tr><td style="padding:16px 32px 24px 32px;border-top:1px solid #eee;">
      <p style="margin:0;font-size:11px;color:#999;">
        If you did not expect this email, you can safely ignore it.
      </p>
    </td></tr>
  </table>
</body></html>"""
        await send_email(
            to=user.email,
            subject="Set your PGR Platform password",
            body=text_body,
            html=html_body,
        )

    async def confirm_password_reset(self, token: str, new_password: str) -> None:
        row = await self.repo.get_reset_token(hash_opaque(token))
        now = datetime.now(timezone.utc)
        if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
            raise AuthError("Reset link is invalid or expired")
        if len(new_password) < 8:
            raise AuthError("Password must be at least 8 characters")
        user = await self.repo.get_user_by_id(row.user_id)
        if user is None:
            raise AuthError("Reset link is invalid or expired")
        user.password_hash = hash_password(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        row.used_at = now
        # Invalidate every existing session on password change.
        await self.repo.revoke_all_refresh_tokens(user.id)
        await self.repo.session.commit()

    async def principal_from_access_token(self, token: str) -> Principal:
        try:
            claims = decode_token(token, "access")
        except JWTError as exc:
            raise AuthError("Invalid or expired token") from exc
        # Fast path: build the principal from token claims — no DB round-trip (arch §16).
        if "roles" in claims:
            pid = claims.get("personId")
            tid = claims.get("tenantId")
            return Principal(
                user_id=uuid.UUID(claims["sub"]),
                email=claims.get("email") or "",
                person_id=uuid.UUID(pid) if pid else None,
                roles=claims.get("roles", []),
                permissions=claims.get("permissions", []),
                tenant_id=uuid.UUID(tid) if tid else None,
            )
        # Fallback for tokens without embedded claims.
        user = await self.repo.get_user_by_id(uuid.UUID(claims["sub"]))
        if user is None or not user.is_active:
            raise AuthError("User no longer active")
        return _principal_from_user(user)
