"""Student status history — kept as an import path; the engine lives in ``fact_history``.

``student.status`` is one of several effective-dated facts (status, programme, study intensity)
that share one history engine. See ``app/modules/student_record/fact_history.py``.
"""
from app.modules.student_record.fact_history import StatusHistoryService, today  # noqa: F401
