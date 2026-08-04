"""Offline tests for the analyzer, run entirely against bundled fixtures.

No test touches the network: every case reads an HTML file from ``fixtures/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seometa.analyzer import analyze_html, analyze_source, parse_page
from seometa.rules import FAIL, PASS, WARN
from seometa.report import render_console, render_json

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _finding(result, check_id):
    return next(f for f in result.findings if f.id == check_id)


@pytest.fixture
def good():
    return analyze_html(_load("good.html"), source="good.html")


@pytest.fixture
def poor():
    return analyze_html(_load("poor.html"), source="poor.html")


@pytest.fixture
def mixed():
    return analyze_html(_load("mixed.html"), source="mixed.html")


# --- Whole-page scoring ---------------------------------------------------


def test_good_page_scores_full_marks(good):
    assert good.score == 100
    assert good.grade == "A"
    assert all(f.status == PASS for f in good.findings)
    assert good.recommendations == []


def test_scores_are_ordered_good_mixed_poor(good, mixed, poor):
    assert good.score > mixed.score > poor.score


def test_poor_page_scores_low(poor):
    assert poor.score == 18
    assert poor.grade == "F"


def test_mixed_page_scores_middle(mixed):
    assert mixed.score == 62
    assert mixed.grade == "C"


# --- Individual checks ----------------------------------------------------


def test_title_length_window(good, poor):
    assert _finding(good, "title").status == PASS
    # "Home" is too short -> warn, not fail.
    assert _finding(poor, "title").status == WARN


def test_missing_meta_description_fails(poor):
    finding = _finding(poor, "meta_description")
    assert finding.status == FAIL
    assert finding.score == 0


def test_noindex_robots_fails(poor):
    finding = _finding(poor, "robots")
    assert finding.status == FAIL
    assert "noindex" in finding.message.lower()


def test_multiple_h1_warns(poor):
    finding = _finding(poor, "headings")
    assert finding.status == WARN
    assert "2" in finding.message


def test_heading_hierarchy_skip_warns(mixed):
    # mixed.html jumps H1 -> H3, which is a hierarchy skip.
    assert _finding(mixed, "headings").status == WARN


def test_image_alt_coverage(poor):
    finding = _finding(poor, "image_alt")
    # 1 of 3 images has alt text.
    assert finding.status == WARN
    assert "1/3" in finding.message


def test_open_graph_partial_warns(mixed):
    finding = _finding(mixed, "open_graph")
    assert finding.status == WARN
    assert "og:image" in (finding.recommendation or "")


def test_missing_viewport_fails(poor):
    assert _finding(poor, "viewport").status == FAIL


def test_good_page_has_no_image_or_hierarchy_issues(good):
    assert _finding(good, "image_alt").status == PASS
    assert _finding(good, "headings").status == PASS


# --- Parsing --------------------------------------------------------------


def test_parse_page_extracts_signals():
    page = parse_page(_load("good.html"))
    assert page.title.strip().startswith("Mountain Trail Coffee")
    assert page.canonical == "https://example.com/coffee"
    assert page.open_graph["og:image"].endswith("og-coffee.jpg")
    assert page.viewport is not None
    assert len(page.images) == 2


def test_recommendations_sorted_high_priority_first(poor):
    priorities = [f.priority for f in poor.recommendations]
    ranks = {"high": 0, "medium": 1, "none": 2}
    assert priorities == sorted(priorities, key=lambda p: ranks[p])


# --- Reporting & source loading ------------------------------------------


def test_render_console_is_plain_text(good):
    text = render_console(good)
    assert "SEO Meta Analyzer report" in text
    assert "100/100" in text


def test_render_json_shape(mixed):
    payload = render_json(mixed)
    assert payload["score"] == 62
    assert {"findings", "recommendations", "grade"} <= payload.keys()
    assert len(payload["findings"]) == 9


def test_analyze_source_reads_local_file():
    result = analyze_source(file=str(FIXTURES / "good.html"))
    assert result.score == 100


def test_analyze_source_requires_exactly_one_input():
    with pytest.raises(ValueError):
        analyze_source()
    with pytest.raises(ValueError):
        analyze_source(url="https://x", file="y.html")
