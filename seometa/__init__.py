"""seo-meta-analyzer: audit on-page SEO signals and produce a scored report.

Public surface:
    analyze_html   -- parse an HTML string and return an AuditResult
    analyze_source -- convenience wrapper for a URL or local file
    AuditResult    -- aggregated findings + 0-100 score
    Finding        -- a single check result
"""

from seometa.analyzer import AuditResult, Finding, analyze_html, analyze_source

__all__ = ["AuditResult", "Finding", "analyze_html", "analyze_source"]
__version__ = "0.1.0"
