"""Truthfulness assessment for documents.

This module assesses document credibility and flags potential issues.

Assessment categories:
- Source credibility
- Claim verifiability
- Bias indicators
- Logical consistency
- Citation quality
"""

import json
import logging
from typing import Any

from evidence_repository.config import get_settings

logger = logging.getLogger(__name__)


async def assess_truthfulness(
    text: str,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Assess document truthfulness and credibility.

    Args:
        text: Document text.
        metadata: Optional metadata for context.

    Returns:
        Assessment dictionary with scores and flags.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured, returning basic assessment")
        return _basic_assessment(text)

    try:
        return await _llm_assessment(text, metadata)
    except Exception as e:
        logger.warning(f"LLM truthfulness assessment failed: {e}")
        return _basic_assessment(text)


def _basic_assessment(text: str) -> dict[str, Any]:
    """Perform basic truthfulness assessment without LLM.

    Args:
        text: Document text.

    Returns:
        Basic assessment dict.
    """
    import re

    assessment = {
        "method": "basic",
        "overall_score": None,
        "flags": [],
        "metrics": {},
    }

    text_lower = text.lower()

    # Check for citation presence
    citation_count = len(re.findall(r'\[\d+\]|\(\d{4}\)', text))
    assessment["metrics"]["citation_count"] = citation_count

    if citation_count == 0 and len(text) > 2000:
        assessment["flags"].append({
            "type": "no_citations",
            "severity": "medium",
            "message": "Document lacks citations/references",
        })

    # Check for hedging language (may indicate uncertainty)
    hedging_words = ["allegedly", "reportedly", "claims", "sources say", "may be", "could be"]
    hedging_count = sum(1 for word in hedging_words if word in text_lower)
    assessment["metrics"]["hedging_count"] = hedging_count

    # Check for absolute claims (may indicate bias)
    absolute_words = ["always", "never", "definitely", "certainly", "100%", "guaranteed"]
    absolute_count = sum(1 for word in absolute_words if word in text_lower)
    assessment["metrics"]["absolute_claim_count"] = absolute_count

    if absolute_count > 5:
        assessment["flags"].append({
            "type": "excessive_absolute_claims",
            "severity": "low",
            "message": "Document contains many absolute claims",
        })

    # Check for emotional language
    emotional_words = [
        "amazing", "terrible", "shocking", "incredible", "outrageous",
        "disgusting", "wonderful", "horrible", "fantastic", "devastating"
    ]
    emotional_count = sum(1 for word in emotional_words if word in text_lower)
    assessment["metrics"]["emotional_language_count"] = emotional_count

    if emotional_count > 10:
        assessment["flags"].append({
            "type": "emotional_language",
            "severity": "medium",
            "message": "Document contains significant emotional language",
        })

    return assessment


async def _llm_assessment(
    text: str,
    metadata: dict | None,
) -> dict[str, Any]:
    """Perform LLM-based truthfulness assessment.

    Args:
        text: Document text.
        metadata: Optional metadata.

    Returns:
        Detailed assessment dict.
    """
    import openai

    settings = get_settings()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = f"""Analyze this document for truthfulness and credibility. Return a JSON assessment.

Document (first 15000 chars):
{text[:15000]}

Evaluate the following dimensions on a scale of 0-100:
1. source_credibility: How credible is the apparent source?
2. claim_verifiability: Can the main claims be verified?
3. bias_level: Level of apparent bias (0=neutral, 100=heavily biased)
4. logical_consistency: Are arguments logically consistent?
5. citation_quality: Quality and presence of citations/references
6. factual_accuracy_indicators: Signs of factual accuracy

Also identify:
- key_claims: Array of main claims made (max 5)
- potential_issues: Array of specific credibility concerns
- verification_suggestions: What would need to be verified

Return ONLY valid JSON with these fields:
{{
  "overall_score": 0-100,
  "dimensions": {{
    "source_credibility": 0-100,
    "claim_verifiability": 0-100,
    "bias_level": 0-100,
    "logical_consistency": 0-100,
    "citation_quality": 0-100
  }},
  "key_claims": ["claim1", "claim2"],
  "potential_issues": [
    {{"type": "issue_type", "severity": "low|medium|high", "description": "..."}}
  ],
  "verification_suggestions": ["suggestion1"],
  "summary": "Brief assessment summary"
}}"""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a fact-checking and credibility assessment expert. Analyze documents objectively."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    content = response.choices[0].message.content.strip()

    # Clean up response
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    assessment = json.loads(content)
    assessment["method"] = "llm"
    assessment["llm_model"] = "gpt-4o-mini"

    return assessment
