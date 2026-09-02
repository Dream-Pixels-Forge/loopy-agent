# `loopy.audit` — Readiness scoring + audit reports

Quantify how "production-ready" an agent configuration is. Each
component gets a score (0-100) and contributes to a final readiness
level (L1/L2/L3/L4/L5).

## Quickstart

```python
from loopy import AuditReport, CheckItem

report = AuditReport(
    items=[
        CheckItem(category="observability", name="tracing", score=80),
        CheckItem(category="safety",       name="redactor",  score=90),
        CheckItem(category="eval",         name="evals",     score=70),
    ],
)
print(report.overall_score, report.readiness_level)
```

## API

| Symbol | Purpose |
|---|---|
| `AuditReport` | Aggregate report |
| `CheckItem` | One component's score |
| `ReadinessLevel` | L1 / L2 / L3 / L4 / L5 (derived from overall score) |