"""Optional FastAPI wrapper exposing the audit over HTTP.

Run with::

    uvicorn seometa.api:app --reload

Then::

    POST /audit   {"html": "<html>..."}   # audit inline markup (offline)
    POST /audit   {"url": "https://..."}  # fetch and audit a live URL

FastAPI/uvicorn are optional extras; the CLI and library work without them.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator

from seometa.analyzer import analyze_html, analyze_source
from seometa.report import render_json

app = FastAPI(
    title="seo-meta-analyzer",
    description="Audit a web page's on-page SEO signals and return a scored report.",
    version="0.1.0",
)


class AuditRequest(BaseModel):
    """Request body for ``POST /audit``. Provide exactly one of url or html."""

    url: Optional[str] = None
    html: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "AuditRequest":
        if bool(self.url) == bool(self.html):
            raise ValueError("Provide exactly one of 'url' or 'html'.")
        return self


@app.post("/audit")
def audit(request: AuditRequest) -> dict:
    """Audit a page supplied inline (``html``) or by ``url`` and return JSON."""
    try:
        if request.html is not None:
            result = analyze_html(request.html, source="<request>")
        else:
            result = analyze_source(url=request.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return render_json(result)
