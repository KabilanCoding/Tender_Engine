"""
All LLM prompt templates for ZYNEX.
Each function returns a fully formatted prompt string.
"""


def document_classification_prompt(text: str) -> str:
    excerpt = text[:3000]
    return f"""You are a document classifier. Analyze the following document excerpt and return ONLY a JSON object.

Document excerpt:
---
{excerpt}
---

Return this exact JSON structure:
{{
  "doc_type": "<SRS|TENDER|RFP|PROPOSAL|UNKNOWN>",
  "confidence": <0.0-1.0>,
  "detected_sections": ["<section name>", ...],
  "summary": "<one sentence description>"
}}

Return only valid JSON, no explanation."""


def _kb_context_block(kb_context) -> str:
    """Format KBContext into a compact text block for injection into prompts."""
    if kb_context is None:
        return ""
    lines = ["\n--- Company Knowledge Base Context ---"]
    if kb_context.certifications:
        cert_names = ", ".join(c["name"] for c in kb_context.certifications)
        lines.append(f"Certifications: {cert_names}")
    if kb_context.financials:
        fin = kb_context.financials[0]
        lines.append(f"Latest annual turnover: {fin['annual_turnover']} {fin['currency']} (FY{fin['fiscal_year']})")
    if kb_context.past_projects:
        proj_names = ", ".join(p.get("name", "") for p in kb_context.past_projects[:3])
        lines.append(f"Past projects (sample): {proj_names}")
    if kb_context.relevant_chunks:
        lines.append("Relevant evidence from past project documents:")
        for ch in kb_context.relevant_chunks[:3]:
            heading = ch.get("section_heading") or ""
            snippet = ch.get("chunk_text", "")[:300]
            lines.append(f"  [{heading}] {snippet}")
    lines.append("--- End of KB Context ---\n")
    return "\n".join(lines)


def estimation_prompt(document_text: str, kb_context=None) -> str:
    kb_block = _kb_context_block(kb_context)
    return f"""You are a software project estimation expert. Analyze this requirements document and return a structured project estimation.

Document:
---
{document_text[:3000]}
---
{kb_block}
Return ONLY a valid JSON object with this exact structure:
{{
  "modules": [
    {{
      "name": "<module name>",
      "description": "<brief description>",
      "user_stories": ["<story>", ...],
      "estimated_hours": <number>,
      "complexity": "<low|medium|high>"
    }}
  ],
  "sprints": [
    {{
      "sprint_number": <number>,
      "name": "<sprint name>",
      "duration_weeks": <number>,
      "tasks": [
        {{
          "name": "<task name>",
          "module": "<module name>",
          "hours": <number>,
          "role": "<developer|qa|devops|designer>"
        }}
      ]
    }}
  ],
  "total_hours": <number>,
  "total_weeks": <number>,
  "team_composition": {{
    "developers": <number>,
    "qa_engineers": <number>,
    "devops_engineers": <number>
  }}
}}

Return only valid JSON."""



def proposal_section_prompt(section_name: str, context: dict) -> str:
    return f"""You are writing a professional tender proposal. Generate the '{section_name}' section.

Context:
- Company: {context.get('company_name', 'Our Company')}
- Project: {context.get('project_name', 'The Project')}
- Requirements: {context.get('requirements_summary', '')}
- Technologies: {context.get('technologies', [])}

Write a professional, concise '{section_name}' section suitable for a formal tender submission.
Use clear headings and bullet points where appropriate.
Return only the section content, no JSON wrapper."""
