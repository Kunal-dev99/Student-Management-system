"""Import every model module so SQLAlchemy can resolve cross-module foreign keys.

Scripts and standalone tools import this before using the ORM; the API gets the
same effect by importing every router. Mirrors the import block in the Alembic env.
"""
from __future__ import annotations

from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.person import models as person_models  # noqa: F401
from app.modules.student_record import models as student_models  # noqa: F401
from app.modules.recruitment import models as recruitment_models  # noqa: F401
from app.modules.recruitment import f3_models as recruitment_f3_models  # noqa: F401
from app.modules.admissions import models as admissions_models  # noqa: F401
from app.modules.supervision import models as supervision_models  # noqa: F401
from app.modules.progression import models as progression_models  # noqa: F401
from app.modules.settings import models as settings_models  # noqa: F401
from app.modules.pattern_lab import models as pattern_lab_models  # noqa: F401
from app.modules.funding import models as funding_models  # noqa: F401
from app.modules.thesis import models as thesis_models  # noqa: F401
from app.modules.completion import models as completion_models  # noqa: F401
from app.modules.workflow import models as workflow_models  # noqa: F401
from app.modules.integration import models as integration_models  # noqa: F401
from app.modules.exports import models as exports_models  # noqa: F401
from app.modules.documents import models as documents_models  # noqa: F401
from app.modules.notifications import models as notifications_models  # noqa: F401
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.research import models as research_models  # noqa: F401
from app.modules.assistant import f6_models as assistant_f6_models  # noqa: F401
from app.modules.assistant import telemetry_models as assistant_telemetry_models  # noqa: F401
