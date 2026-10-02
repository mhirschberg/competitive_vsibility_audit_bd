"""Notebook-independent styled PDF export for deterministic service reports."""

from datetime import datetime, timezone
import html
from pathlib import Path
import re


def create_styled_pdf_report(
    *, markdown_text, output_path, company_name, company_url="",
    country="", generated_at=None, audit_focus="",
):
    """Render the report and a compact cover using the existing PDF stack."""
    from markdown import markdown
    from weasyprint import HTML

    markdown_text = str(markdown_text or "").strip()
    if not markdown_text:
        raise ValueError("Cannot generate a PDF from an empty report.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    if hasattr(generated_at, "strftime"):
        generated_date = generated_at.strftime("%B %d, %Y")
    else:
        generated_date = str(generated_at)

    report_markdown = re.sub(
        r"^\s*#\s+(?:Competitive Visibility Audit|Competitive Visibility Report)"
        r".*?\n+",
        "", markdown_text, count=1, flags=re.IGNORECASE,
    ).strip()
    report_html = markdown(
        report_markdown,
        extensions=["extra", "sane_lists"], output_format="html5",
    )
    company = html.escape(re.sub(r"\s+", " ", str(company_name or "Audit")).strip())
    focus = html.escape(re.sub(r"\s+", " ", str(audit_focus or "")).strip())
    company_url = html.escape(str(company_url or ""))
    country = html.escape(str(country or "").upper())
    generated_date = html.escape(generated_date)
    subject = company + (f" / {focus}" if focus else "")
    focus_block = (
        f'<p class="focus"><span>Audit focus</span>{focus}</p>' if focus else ""
    )
    metadata = " · ".join(
        value for value in (company_url, country, generated_date) if value
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Competitive Visibility Report for {subject}</title>
<style>
@page {{ size: A4; margin: 20mm 18mm 22mm;
  @bottom-left {{ content: "Qaviso · Competitive Visibility"; color: #60736b; font: 8pt sans-serif; }}
  @bottom-right {{ content: counter(page); color: #60736b; font: 8pt sans-serif; }}
}}
@page:first {{ margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #183a34; font: 10pt/1.55 sans-serif; }}
.cover {{ min-height: 297mm; padding: 42mm 24mm 24mm; background: #f3f0e7; page-break-after: always; }}
.eyebrow {{ color: #ef7147; font: 700 9pt monospace; letter-spacing: .16em; text-transform: uppercase; }}
h1 {{ max-width: 155mm; margin: 22mm 0 8mm; font: 700 34pt/1.08 Georgia, serif; }}
.focus {{ margin: 12mm 0; padding: 6mm; border-left: 3px solid #ef7147; background: #fffdf8; }}
.focus span {{ display: block; margin-bottom: 2mm; color: #60736b; font: 700 8pt monospace; text-transform: uppercase; }}
.metadata {{ margin-top: 22mm; padding-top: 5mm; border-top: 1px solid #c9d0c5; color: #60736b; font-size: 9pt; }}
main {{ padding: 0; }}
h1,h2,h3 {{ color: #183a34; page-break-after: avoid; }}
h2 {{ margin: 9mm 0 3mm; padding-bottom: 2mm; border-bottom: 1px solid #d9ddd4; font: 700 19pt/1.2 Georgia, serif; }}
h3 {{ margin: 6mm 0 2mm; font-size: 12pt; }}
p,li {{ orphans: 3; widows: 3; }}
table {{ width: 100%; margin: 4mm 0; border-collapse: collapse; font-size: 8.5pt; }}
th {{ background: #183a34; color: white; text-align: left; }}
th,td {{ padding: 2.2mm; border: 1px solid #d9ddd4; vertical-align: top; }}
tr {{ page-break-inside: avoid; }}
a {{ color: #176353; text-decoration: none; overflow-wrap: anywhere; }}
blockquote {{ margin: 4mm 0; padding: 2mm 4mm; border-left: 2px solid #ef7147; color: #52645e; }}
code {{ color: #183a34; background: #f1f2ed; }}
</style></head><body>
<section class="cover"><div class="eyebrow">Competitive visibility report</div>
<h1>{html.escape('Competitive Visibility Report for ' + subject)}</h1>
{focus_block}<div class="metadata">{metadata}</div></section>
<main>{report_html}</main></body></html>"""

    def deny_external_fetch(url, *args, **kwargs):
        # Reports are self-contained; provider-supplied Markdown must not make
        # the PDF renderer fetch arbitrary external images or resources.
        return {"string": b"", "mime_type": "text/plain", "redirected_url": url}

    HTML(string=document, url_fetcher=deny_external_fetch).write_pdf(
        target=str(output_path),
    )
    if output_path.stat().st_size < 1000:
        raise ValueError("The generated PDF appears to be empty or incomplete.")
    return output_path
