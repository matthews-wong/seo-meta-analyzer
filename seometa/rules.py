"""SEO checks and their weights.

Each check is a pure function ``(PageData) -> Finding``. A check owns its own
weight (contribution to the 0-100 score) and decides a status plus a partial
score. The public ``CHECKS`` registry is what :mod:`seometa.analyzer` iterates
over, so adding a rule is a one-line change here.

Status vocabulary:
    ``pass`` -- signal is healthy, full weight awarded.
    ``warn`` -- signal is present but suboptimal, partial weight.
    ``fail`` -- signal is missing or harmful, zero weight.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# --- Recommended length windows (characters) for text signals. ---
TITLE_MIN, TITLE_MAX = 30, 60
DESCRIPTION_MIN, DESCRIPTION_MAX = 50, 160

PASS = "pass"
WARN = "warn"
FAIL = "fail"


@dataclass
class PageData:
    """Normalised, framework-agnostic view of a parsed HTML page.

    Populated by :func:`seometa.analyzer.parse_page`. Keeping this separate from
    BeautifulSoup means every rule is a plain function over plain data and is
    trivial to unit-test without touching the parser or the network.
    """

    title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None
    robots: str | None = None
    viewport: str | None = None
    open_graph: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    # Headings in document order as (level, text), e.g. (1, "Home").
    headings: list[tuple[int, str]] = field(default_factory=list)
    # Images as {"src": str, "alt": Optional[str]}; alt is None when absent.
    images: list[dict[str, str | None]] = field(default_factory=list)


@dataclass
class Finding:
    """Result of a single SEO check."""

    id: str
    label: str
    status: str  # PASS | WARN | FAIL
    score: float  # points awarded, 0..weight
    weight: int  # maximum points this check can contribute
    message: str  # what was observed
    recommendation: str | None = None  # how to fix it (None when passing)

    @property
    def priority(self) -> str:
        """Coarse fix priority used to sort recommendations in the report."""
        if self.status == FAIL:
            return "high"
        if self.status == WARN:
            return "medium"
        return "none"


def _finding(
    id: str,
    label: str,
    status: str,
    score: float,
    weight: int,
    message: str,
    recommendation: str | None = None,
) -> Finding:
    return Finding(
        id=id,
        label=label,
        status=status,
        score=round(score, 2),
        weight=weight,
        message=message,
        recommendation=recommendation,
    )


def check_title(page: PageData) -> Finding:
    """<title> must exist and sit within the recommended length window."""
    weight = 15
    title = (page.title or "").strip()
    if not title:
        return _finding(
            "title", "Title tag", FAIL, 0, weight,
            "No <title> tag found.",
            f"Add a descriptive <title> of {TITLE_MIN}-{TITLE_MAX} characters.",
        )
    length = len(title)
    if length < TITLE_MIN or length > TITLE_MAX:
        return _finding(
            "title", "Title tag", WARN, weight * 0.5, weight,
            f"Title is {length} characters (recommended {TITLE_MIN}-{TITLE_MAX}).",
            f"Rewrite the title to {TITLE_MIN}-{TITLE_MAX} characters so it is not "
            "truncated in search results.",
        )
    return _finding(
        "title", "Title tag", PASS, weight, weight,
        f"Title present and well-sized ({length} characters).",
    )


def check_meta_description(page: PageData) -> Finding:
    """Meta description must exist and sit within the recommended length window."""
    weight = 15
    desc = (page.meta_description or "").strip()
    if not desc:
        return _finding(
            "meta_description", "Meta description", FAIL, 0, weight,
            "No meta description found.",
            "Add a <meta name=\"description\"> of "
            f"{DESCRIPTION_MIN}-{DESCRIPTION_MAX} characters summarising the page.",
        )
    length = len(desc)
    if length < DESCRIPTION_MIN or length > DESCRIPTION_MAX:
        return _finding(
            "meta_description", "Meta description", WARN, weight * 0.5, weight,
            f"Meta description is {length} characters "
            f"(recommended {DESCRIPTION_MIN}-{DESCRIPTION_MAX}).",
            f"Adjust the description to {DESCRIPTION_MIN}-{DESCRIPTION_MAX} "
            "characters for a clean SERP snippet.",
        )
    return _finding(
        "meta_description", "Meta description", PASS, weight, weight,
        f"Meta description present and well-sized ({length} characters).",
    )


def check_canonical(page: PageData) -> Finding:
    """A canonical URL should be declared to consolidate duplicate content."""
    weight = 10
    if page.canonical and page.canonical.strip():
        return _finding(
            "canonical", "Canonical link", PASS, weight, weight,
            f"Canonical URL set to {page.canonical.strip()}.",
        )
    return _finding(
        "canonical", "Canonical link", FAIL, 0, weight,
        "No <link rel=\"canonical\"> found.",
        "Add a canonical link to avoid duplicate-content dilution.",
    )


def check_robots(page: PageData) -> Finding:
    """Meta robots must not silently block indexing."""
    weight = 5
    robots = (page.robots or "").strip()
    # Split on commas/whitespace so directives are matched as whole tokens, and
    # honour the `none` shorthand, which the spec defines as `noindex, nofollow`.
    tokens = {token for token in re.split(r"[\s,]+", robots.lower()) if token}
    blocks_index = "noindex" in tokens or "none" in tokens
    blocks_follow = "nofollow" in tokens or "none" in tokens
    if blocks_index:
        return _finding(
            "robots", "Meta robots", FAIL, 0, weight,
            f"Meta robots contains a 'noindex' directive ({page.robots}).",
            "Remove the 'noindex'/'none' directive unless this page is "
            "intentionally hidden from search.",
        )
    if blocks_follow:
        return _finding(
            "robots", "Meta robots", WARN, weight * 0.5, weight,
            f"Meta robots contains 'nofollow' ({page.robots}).",
            "Confirm 'nofollow' is intended; it stops link equity flowing onward.",
        )
    if robots:
        return _finding(
            "robots", "Meta robots", PASS, weight, weight,
            f"Meta robots is indexable ({page.robots}).",
        )
    return _finding(
        "robots", "Meta robots", PASS, weight, weight,
        "No meta robots tag (page defaults to indexable).",
    )


def _presence_score(values: dict[str, str], required: list[str]) -> tuple[int, list[str]]:
    """Return (count_present, missing_keys) for the required keys."""
    missing = [key for key in required if not values.get(key, "").strip()]
    return len(required) - len(missing), missing


def check_open_graph(page: PageData) -> Finding:
    """Open Graph tags power rich link previews on Facebook, LinkedIn, etc."""
    weight = 10
    required = ["og:title", "og:description", "og:image"]
    present, missing = _presence_score(page.open_graph, required)
    score = weight * present / len(required)
    if present == len(required):
        return _finding(
            "open_graph", "Open Graph tags", PASS, score, weight,
            "All core Open Graph tags present (og:title, og:description, og:image).",
        )
    status = FAIL if present == 0 else WARN
    return _finding(
        "open_graph", "Open Graph tags", status, score, weight,
        f"{present}/{len(required)} core Open Graph tags present.",
        "Add the missing Open Graph tags: " + ", ".join(missing) + ".",
    )


def check_twitter_card(page: PageData) -> Finding:
    """Twitter Card tags control how the page renders when shared on X/Twitter."""
    weight = 10
    required = ["twitter:card", "twitter:title", "twitter:image"]
    present, missing = _presence_score(page.twitter, required)
    score = weight * present / len(required)
    if present == len(required):
        return _finding(
            "twitter_card", "Twitter Card tags", PASS, score, weight,
            "All core Twitter Card tags present (twitter:card, twitter:title, twitter:image).",
        )
    status = FAIL if present == 0 else WARN
    return _finding(
        "twitter_card", "Twitter Card tags", status, score, weight,
        f"{present}/{len(required)} core Twitter Card tags present.",
        "Add the missing Twitter Card tags: " + ", ".join(missing) + ".",
    )


def _has_hierarchy_skip(headings: list[tuple[int, str]]) -> bool:
    """True if heading levels jump by more than one on the way down (e.g. H1->H3)."""
    previous = 0
    for level, _text in headings:
        if previous and level > previous + 1:
            return True
        previous = level
    return False


def check_headings(page: PageData) -> Finding:
    """Exactly one H1 plus a well-nested heading outline."""
    weight = 15
    h1_count = sum(1 for level, _ in page.headings if level == 1)
    if h1_count == 0:
        return _finding(
            "headings", "Heading structure", FAIL, 0, weight,
            "No H1 heading found.",
            "Add exactly one H1 that states the page's main topic.",
        )
    if h1_count > 1:
        return _finding(
            "headings", "Heading structure", WARN, weight * 0.5, weight,
            f"Found {h1_count} H1 headings (expected exactly one).",
            "Keep a single H1 and demote the others to H2/H3.",
        )
    if _has_hierarchy_skip(page.headings):
        return _finding(
            "headings", "Heading structure", WARN, weight * 0.7, weight,
            "Single H1 present, but the heading hierarchy skips a level.",
            "Avoid skipping heading levels (e.g. H1 -> H3); nest them in order.",
        )
    return _finding(
        "headings", "Heading structure", PASS, weight, weight,
        "Exactly one H1 and a well-nested heading hierarchy.",
    )


def check_image_alt(page: PageData) -> Finding:
    """Images should carry descriptive alt text for accessibility and image SEO."""
    weight = 10
    total = len(page.images)
    if total == 0:
        return _finding(
            "image_alt", "Image alt text", PASS, weight, weight,
            "No <img> elements to evaluate.",
        )
    with_alt = sum(1 for img in page.images if (img.get("alt") or "").strip())
    coverage = with_alt / total
    score = weight * coverage
    if with_alt == total:
        return _finding(
            "image_alt", "Image alt text", PASS, score, weight,
            f"All {total} images have alt text.",
        )
    status = FAIL if with_alt == 0 else WARN
    return _finding(
        "image_alt", "Image alt text", status, score, weight,
        f"{with_alt}/{total} images have alt text ({coverage:.0%} coverage).",
        f"Add alt text to the {total - with_alt} image(s) missing it.",
    )


def check_viewport(page: PageData) -> Finding:
    """A viewport meta tag is required for mobile-friendly rendering."""
    weight = 10
    if page.viewport and page.viewport.strip():
        return _finding(
            "viewport", "Viewport meta", PASS, weight, weight,
            f"Viewport configured ({page.viewport.strip()}).",
        )
    return _finding(
        "viewport", "Viewport meta", FAIL, 0, weight,
        "No viewport meta tag found.",
        "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.",
    )


# Registry of every check. Order here is the order findings appear in reports.
CHECKS: list[Callable[[PageData], Finding]] = [
    check_title,
    check_meta_description,
    check_canonical,
    check_robots,
    check_open_graph,
    check_twitter_card,
    check_headings,
    check_image_alt,
    check_viewport,
]

# Sum of all check weights; the score is normalised so this equals 100.
TOTAL_WEIGHT: int = sum(check(PageData()).weight for check in CHECKS)
