import os
import uuid


def generate_proposal_pdf(proposal_data: dict, output_dir: str) -> str:
    """Generate a PDF proposal document. Returns the file path."""
    from weasyprint import HTML

    title = proposal_data.get("title", "Technical Proposal")
    company = proposal_data.get("company_name", "ZYNEX Technologies")
    sections = proposal_data.get("sections", {})

    section_order = [
        ("executive_summary", "1. Executive Summary"),
        ("technical_approach", "2. Technical Approach"),
        ("project_plan", "3. Project Plan"),
        ("team_composition", "4. Team Composition"),
        ("company_profile", "5. Company Profile"),
        ("commercial_proposal", "6. Commercial Proposal"),
        ("compliance", "7. Compliance & Certifications"),
    ]

    sections_html = ""
    for key, heading in section_order:
        content = sections.get(key) or proposal_data.get(key, "")
        if not content:
            continue
        paragraphs = "".join(
            f"<p>{p.strip()}</p>"
            for p in content.split("\n")
            if p.strip()
        )
        sections_html += f"<h2>{heading}</h2>{paragraphs}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: Arial, sans-serif; font-size: 12pt; margin: 40px; color: #1a1a2e; }}
        h1 {{ color: #1a2744; text-align: center; font-size: 20pt; margin-bottom: 4px; }}
        .company {{ text-align: center; font-size: 14pt; font-weight: bold; color: #1a5276; margin-bottom: 30px; }}
        h2 {{ color: #1a2744; font-size: 14pt; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 24px; }}
        p {{ line-height: 1.6; margin: 6px 0; }}
        @page {{ margin: 2cm; }}
      </style>
    </head>
    <body>
      <h1>{title}</h1>
      <div class="company">{company}</div>
      {sections_html}
    </body>
    </html>
    """

    os.makedirs(output_dir, exist_ok=True)
    filename = f"proposal_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(output_dir, filename)
    HTML(string=html_content).write_pdf(filepath)
    return filepath
