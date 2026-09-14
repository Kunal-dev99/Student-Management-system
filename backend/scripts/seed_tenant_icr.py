"""Seed the Institute of Cancer Research as a real tenant row.

The `tenant` table already carries a "Default Institution" row from the MT-1
migration. This adds ICR alongside it so the login screen's institution
selector has a second real option with its own branding, matching the
Redwood-maroon scheme already used elsewhere in the frontend.

Additive and idempotent — running this twice does not duplicate the row.

    python -m scripts.seed_tenant_icr
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionFactory
from app.modules.tenant.models import Tenant

ICR_SUBDOMAIN = "icr"
ICR_NAME = "Institute of Cancer Research"

# Matches the maroon ICR branding already used in the sidebar/login-page work
# earlier in this project (vs the Redwood-red default institution branding).
ICR_BRANDING = {
    "primaryColor": "#7A1F3D",
    "accentColor": "#C74634",
    "shortName": "ICR",
    "logoInitials": "ICR",
}


async def main() -> None:
    async with SessionFactory() as s:
        existing = (
            await s.execute(select(Tenant).where(Tenant.subdomain == ICR_SUBDOMAIN))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  = tenant '{ICR_NAME}' already present ({existing.id}) - skipped")
            return

        tenant = Tenant(
            name=ICR_NAME,
            subdomain=ICR_SUBDOMAIN,
            activated_at=datetime.now(timezone.utc),
            branding=ICR_BRANDING,
        )
        s.add(tenant)
        await s.commit()
        print(f"  + tenant '{ICR_NAME}' created ({tenant.id})")


if __name__ == "__main__":
    asyncio.run(main())
