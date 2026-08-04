"""Render an :class:`~seometa.analyzer.AuditResult` for humans and machines.

``render_console`` returns a plain-text report (no colour codes, so it is easy
to snapshot in tests and paste into docs). ``render_json`` returns a stable dict
ready for ``json.dumps``.
"""

from __future__ import annotations

from seometa.analyzer import AuditResult
from seometa.rules import FAIL, PASS, WARN

# ASCII status markers keep output copy-paste friendly across terminals.
_STATUS_MARKER = {PASS: "[PASS]", WARN: "[WARN]", FAIL: "[FAIL]"}


def render_console(result: AuditResult) -> str:
    """Return a human-readable, plain-text audit report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("SEO Meta Analyzer report")
    lines.append(f"Source : {result.source}")
    lines.append(f"Score  : {result.score}/100  (grade {result.grade})")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Checks:")
    for finding in result.findings:
        marker = _STATUS_MARKER[finding.status]
        lines.append(
            f"  {marker} {finding.label} "
            f"({finding.score:g}/{finding.weight}) - {finding.message}"
        )

    recommendations = result.recommendations
    lines.append("")
    if recommendations:
        lines.append("Prioritized recommendations:")
        for index, finding in enumerate(recommendations, start=1):
            lines.append(
                f"  {index}. [{finding.priority.upper()}] "
                f"{finding.label}: {finding.recommendation}"
            )
    else:
        lines.append("No recommendations - all checks passed.")

    return "\n".join(lines)


def render_json(result: AuditResult) -> dict:
    """Return a JSON-serialisable dict describing the full audit."""
    return {
        "source": result.source,
        "score": result.score,
        "grade": result.grade,
        "findings": [
            {
                "id": f.id,
                "label": f.label,
                "status": f.status,
                "score": f.score,
                "weight": f.weight,
                "message": f.message,
                "recommendation": f.recommendation,
                "priority": f.priority,
            }
            for f in result.findings
        ],
        "recommendations": [
            {
                "id": f.id,
                "label": f.label,
                "priority": f.priority,
                "recommendation": f.recommendation,
            }
            for f in result.recommendations
        ],
    }
