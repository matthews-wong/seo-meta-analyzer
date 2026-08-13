"""HTML parsing and audit orchestration.

The parser turns raw HTML into a :class:`~seometa.rules.PageData` value object,
then every rule in :data:`seometa.rules.CHECKS` scores it. Nothing here reaches
the network unless :func:`analyze_source` is given a URL, which keeps the whole
analysis pipeline unit-testable against local fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from seometa.rules import CHECKS, TOTAL_WEIGHT, Finding, PageData

# Re-exported so callers can `from seometa.analyzer import Finding`.
__all__ = ["AuditResult", "Finding", "analyze_html", "analyze_source", "parse_page"]

_HEADING_TAGS = {f"h{level}": level for level in range(1, 7)}


@dataclass
class AuditResult:
    """Aggregate outcome of auditing one page."""

    source: str
    score: int  # 0-100, weighted sum of findings normalised to TOTAL_WEIGHT
    findings: list[Finding]

    @property
    def grade(self) -> str:
        """Letter grade derived from the numeric score."""
        if self.score >= 90:
            return "A"
        if self.score >= 75:
            return "B"
        if self.score >= 60:
            return "C"
        if self.score >= 40:
            return "D"
        return "F"

    @property
    def recommendations(self) -> list[Finding]:
        """Findings that need action, highest priority first, then by weight."""
        priority_rank = {"high": 0, "medium": 1, "none": 2}
        actionable = [f for f in self.findings if f.recommendation]
        return sorted(
            actionable,
            key=lambda f: (priority_rank[f.priority], -f.weight),
        )


def _meta_content(soup: BeautifulSoup, *, name: str) -> str | None:
    """Return the content of ``<meta name=...>`` (case-insensitive), if present."""
    tag = soup.find("meta", attrs={"name": lambda v: v and v.lower() == name})
    if tag and tag.get("content") is not None:
        return tag["content"]
    return None


def parse_page(html: str) -> PageData:
    """Parse an HTML string into a normalised :class:`PageData`.

    Pure and offline: it only reads the supplied markup. Missing signals become
    ``None`` / empty collections rather than raising, so downstream rules decide
    severity.
    """
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text() if title_tag else None

    canonical_tag = soup.find("link", attrs={"rel": lambda v: v and "canonical" in [
        r.lower() for r in (v if isinstance(v, list) else [v])
    ]})
    canonical = canonical_tag.get("href") if canonical_tag else None

    open_graph: dict[str, str] = {}
    for tag in soup.find_all("meta", property=True):
        prop = tag["property"].lower()
        if prop.startswith("og:") and tag.get("content"):
            open_graph.setdefault(prop, tag["content"])

    twitter: dict[str, str] = {}
    for tag in soup.find_all("meta", attrs={"name": True}):
        name = tag["name"].lower()
        if name.startswith("twitter:") and tag.get("content"):
            twitter.setdefault(name, tag["content"])

    headings: list[tuple[int, str]] = []
    for tag in soup.find_all(list(_HEADING_TAGS)):
        level = _HEADING_TAGS[tag.name]
        headings.append((level, tag.get_text(strip=True)))

    images: list[dict[str, str | None]] = []
    for tag in soup.find_all("img"):
        images.append({"src": tag.get("src"), "alt": tag.get("alt")})

    return PageData(
        title=title,
        meta_description=_meta_content(soup, name="description"),
        canonical=canonical,
        robots=_meta_content(soup, name="robots"),
        viewport=_meta_content(soup, name="viewport"),
        open_graph=open_graph,
        twitter=twitter,
        headings=headings,
        images=images,
    )


def analyze_html(html: str, source: str = "<string>") -> AuditResult:
    """Run every check over ``html`` and return a scored :class:`AuditResult`.

    ``source`` is a human-readable label (URL or file path) echoed in reports.
    """
    page = parse_page(html)
    findings = [check(page) for check in CHECKS]
    raw_score = sum(f.score for f in findings)
    score = round(raw_score / TOTAL_WEIGHT * 100)
    return AuditResult(source=source, score=score, findings=findings)


def analyze_source(
    url: str | None = None,
    file: str | None = None,
    *,
    timeout: float = 10.0,
) -> AuditResult:
    """Audit a page from a local file or a URL.

    Exactly one of ``url`` or ``file`` must be given. Local files are read
    offline; URLs are fetched with ``requests`` (imported lazily so the package
    works without network access for the file/string paths).
    """
    if bool(url) == bool(file):
        raise ValueError("Provide exactly one of 'url' or 'file'.")

    if file:
        path = Path(file)
        html = path.read_text(encoding="utf-8")
        return analyze_html(html, source=str(path))

    import requests  # local import keeps offline usage dependency-light

    response = requests.get(url, timeout=timeout, headers={"User-Agent": "seo-meta-analyzer/0.1"})
    response.raise_for_status()
    return analyze_html(response.text, source=url)
