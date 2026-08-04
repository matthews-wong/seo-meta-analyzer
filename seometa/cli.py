"""Command-line interface for seo-meta-analyzer.

Usage examples::

    seo-meta-analyzer --file fixtures/good.html
    seo-meta-analyzer --url https://example.com --format json
"""

from __future__ import annotations

import json
import sys

import click

from seometa.analyzer import analyze_source
from seometa.report import render_console, render_json


@click.command()
@click.option("--url", "url", default=None, help="URL of the page to audit.")
@click.option(
    "--file",
    "file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a local HTML file to audit (offline).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["console", "json"]),
    default="console",
    show_default=True,
    help="Output format.",
)
def main(url: str | None, file: str | None, output_format: str) -> None:
    """Audit a web page's on-page SEO signals and print a scored report."""
    if bool(url) == bool(file):
        raise click.UsageError("Provide exactly one of --url or --file.")

    try:
        result = analyze_source(url=url, file=file)
    except Exception as exc:  # surface a clean message instead of a traceback
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(json.dumps(render_json(result), indent=2))
    else:
        click.echo(render_console(result))

    # Non-zero exit on a failing grade makes the tool CI-friendly.
    sys.exit(0 if result.score >= 60 else 1)


if __name__ == "__main__":
    main()
