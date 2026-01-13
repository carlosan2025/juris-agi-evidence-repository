"""LLM prompts for multi-level extraction."""

import json
from typing import Any


def build_system_prompt(vocab_context: dict[str, Any], level: int) -> str:
    """Build system prompt for extraction.

    Args:
        vocab_context: Vocabulary context from BaseVocabulary.get_extraction_prompt_context()
        level: Extraction level (1-4)

    Returns:
        System prompt string
    """
    profile_name = vocab_context["profile_name"]

    # Build metrics section
    metrics_list = "\n".join(
        f"  - {m['name']}: {m['description']} (unit: {m['unit_type']})"
        for m in vocab_context["metrics"]
    )

    # Build predicates section
    predicates_list = "\n".join(
        f"  - {p['name']}: {p['description']}"
        for p in vocab_context["claim_predicates"]
    )

    # Build risks section (only for L2+)
    risks_section = ""
    if vocab_context["risk_categories"]:
        risks_list = "\n".join(
            f"  - {r['name']}: {r['description']}"
            for r in vocab_context["risk_categories"]
        )
        risks_section = f"""

## Risk Categories to Identify
{risks_list}"""

    # Level-specific instructions
    level_instructions = {
        1: """
## Level 1 (Basic) Extraction Instructions
- Extract only key metrics and essential compliance claims
- Focus on explicitly stated facts
- Do NOT infer or speculate
- Limit to 5-10 most important metrics
- Limit to 3-5 most critical claims""",
        2: """
## Level 2 (Standard) Extraction Instructions
- Extract comprehensive metrics with time scope
- Extract all compliance and certification claims
- Identify constraints and definitions
- Flag any obvious conflicts or inconsistencies
- Note missing information as open questions""",
        3: """
## Level 3 (Deep) Extraction Instructions
- Extract all identifiable metrics across all categories
- Resolve entity references (who/what the metric applies to)
- Extract time-series data where available
- Identify risks based on extracted facts
- Cross-reference related facts for consistency
- Note quality flags (estimated, restated, pro forma)""",
        4: """
## Level 4 (Forensic) Extraction Instructions
- Maximum extraction depth
- Flag all potential inconsistencies as conflicts
- Identify related party transactions
- Note calculation methodologies and their implications
- Cross-document reconciliation where applicable
- Comprehensive risk assessment
- Document all assumptions and limitations""",
    }

    return f"""You are a specialized extraction agent for {profile_name} due diligence analysis.

Your task is to extract structured facts from documents with full provenance tracking.
All facts must reference specific spans in the source document.

## Output Format
Respond with a JSON object containing:
- claims: Array of claim objects
- metrics: Array of metric objects
- constraints: Array of constraint objects (L2+)
- risks: Array of risk objects (L2+)
- conflicts: Array of conflict objects (L2+)
- open_questions: Array of question objects (L2+)

## Metrics to Extract
{metrics_list}

## Claim Predicates (Assertions)
{predicates_list}
{risks_section}
{level_instructions.get(level, level_instructions[2])}

## Quality Standards
- certainty levels: "definite" (explicitly stated), "probable" (strongly implied), "possible" (mentioned but uncertain), "speculative" (inferred)
- source_reliability: "audited" (independently verified), "official" (company document), "internal" (unverified internal), "third_party" (external source), "unknown"
- Always include span_refs (even if empty array) for traceability
- Include evidence_quote for critical facts
- Parse numeric values where possible (value_numeric)
- Include period information for time-bound metrics

## Response Schema
```json
{{
  "claims": [
    {{
      "subject": {{"type": "company", "name": "..."}},
      "predicate": "has_soc2",
      "object": {{"type": "certification", "name": "SOC2 Type II"}},
      "claim_type": "compliance",
      "time_scope": {{"period": "2024", "as_of": "2024-12-31"}},
      "certainty": "definite",
      "source_reliability": "official",
      "span_refs": ["span_id_1"],
      "evidence_quote": "...",
      "extraction_confidence": 0.95
    }}
  ],
  "metrics": [
    {{
      "entity_id": "acme_corp",
      "entity_type": "company",
      "metric_name": "arr",
      "metric_category": "revenue",
      "value_numeric": 10000000,
      "value_raw": "$10M",
      "unit": "USD",
      "currency": "USD",
      "period_start": "2024-01-01",
      "period_end": "2024-12-31",
      "period_type": "annual",
      "method": "standard",
      "certainty": "definite",
      "source_reliability": "official",
      "quality_flags": [],
      "span_refs": ["span_id_2"],
      "evidence_quote": "...",
      "extraction_confidence": 0.98
    }}
  ],
  "constraints": [
    {{
      "constraint_type": "definition",
      "applies_to": {{"metric_ids": ["arr"]}},
      "statement": "ARR is calculated as MRR × 12",
      "certainty": "definite",
      "span_refs": ["span_id_3"],
      "extraction_confidence": 0.9
    }}
  ],
  "risks": [
    {{
      "risk_type": "customer_concentration",
      "risk_category": "financial",
      "severity": "medium",
      "statement": "Top customer represents 40% of revenue",
      "rationale": "Concentration above 20% threshold",
      "related_claims": [],
      "related_metrics": ["revenue"],
      "span_refs": ["span_id_4"],
      "extraction_confidence": 0.85
    }}
  ],
  "conflicts": [
    {{
      "topic": "Revenue figures",
      "severity": "high",
      "claim_ids": [],
      "metric_ids": ["revenue_q4", "revenue_annual"],
      "reason": "Q4 revenue × 4 doesn't match stated annual revenue"
    }}
  ],
  "open_questions": [
    {{
      "question": "What is the customer churn rate?",
      "category": "missing_data",
      "context": "Mentioned NRR but no explicit churn figure",
      "related_claim_ids": [],
      "related_metric_ids": ["nrr"]
    }}
  ]
}}
```
"""


def build_user_prompt(
    document_text: str,
    spans: list[dict[str, Any]] | None = None,
    previous_extraction: dict[str, Any] | None = None,
) -> str:
    """Build user prompt for extraction.

    Args:
        document_text: Full document text or relevant sections
        spans: Optional list of pre-identified spans with IDs
        previous_extraction: Optional results from lower level extraction

    Returns:
        User prompt string
    """
    prompt_parts = []

    # Add document content
    prompt_parts.append("## Document Content\n")
    prompt_parts.append(document_text)

    # Add span references if available
    if spans:
        prompt_parts.append("\n\n## Available Span References\n")
        for span in spans:
            prompt_parts.append(
                f"- {span['id']}: Page {span.get('page', 'N/A')}, "
                f"Type: {span.get('type', 'text')}\n"
            )

    # Add previous extraction context for incremental extraction
    if previous_extraction:
        prompt_parts.append("\n\n## Previous Extraction Results (Lower Level)\n")
        prompt_parts.append(
            "Build upon these previously extracted facts. "
            "Do not duplicate, but add depth and identify additional facts.\n"
        )
        prompt_parts.append("```json\n")
        prompt_parts.append(json.dumps(previous_extraction, indent=2, default=str))
        prompt_parts.append("\n```")

    prompt_parts.append(
        "\n\nExtract facts from the document above according to the system instructions. "
        "Return only valid JSON."
    )

    return "".join(prompt_parts)
