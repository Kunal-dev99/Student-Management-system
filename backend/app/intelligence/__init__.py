"""app.intelligence — PGR Intelligence layer.

Higher-level orchestration on top of app.ai. Knows PGR context (students, supervision,
funding, thesis, workflows), evidence and freshness, scenarios and intervention drafts.

Dependency rule (enforced by convention):
    app.intelligence  →  app.ai  +  app.modules.* read/query interfaces
    app.modules.*     ↛  app.intelligence

Domain modules must remain able to serve their normal business rules with the whole
intelligence package removed — the model-off proof test guarantees this.
"""
