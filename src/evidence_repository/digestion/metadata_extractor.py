"""LLM-based metadata extraction.

This module uses LLM to extract structured metadata from document content.

Extracted fields:
- title
- short_description
- long_summary
- source_type (enum)
- main_topics
- sectors
- geographies
- company_names
- authors
- publishing_organization
- publication_date
"""

import json
import logging
from datetime import datetime
from typing import Any

from evidence_repository.config import get_settings

logger = logging.getLogger(__name__)

# Document type classifications
DOCUMENT_TYPES = [
    "academic_paper",
    "news_article",
    "blog_post",
    "company_report",
    "financial_statement",
    "legal_document",
    "technical_documentation",
    "press_release",
    "marketing_material",
    "government_document",
    "patent",
    "presentation",
    "whitepaper",
    "case_study",
    "policy_document",
    "regulatory_filing",
    "internal_memo",
    "contract",
    "invoice",
    "spreadsheet_data",
    "unknown",
]

# Industry sectors
SECTORS = [
    "technology",
    "healthcare",
    "finance",
    "energy",
    "consumer",
    "industrial",
    "materials",
    "real_estate",
    "utilities",
    "communications",
    "government",
    "education",
    "legal",
    "media",
    "retail",
    "transportation",
    "agriculture",
    "other",
]


async def extract_metadata(
    text: str,
    filename: str,
    use_llm: bool = True,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    """Extract metadata from document text.

    Args:
        text: Document text (first N characters).
        filename: Original filename for hints.
        use_llm: Whether to use LLM for extraction.
        openai_api_key: Optional OpenAI API key (if not provided, uses settings).

    Returns:
        Extracted metadata dictionary.
    """
    # Start with filename-based extraction
    metadata = _extract_from_filename(filename)

    if not use_llm:
        return metadata

    # Use provided key or fall back to settings
    api_key = openai_api_key
    if not api_key:
        settings = get_settings()
        api_key = settings.openai_api_key

    if not api_key:
        logger.warning("OpenAI API key not configured (OPENAI_API_KEY env var), skipping LLM extraction")
        return metadata

    logger.info(f"OpenAI API key found, attempting LLM metadata extraction for: {filename}")

    try:
        llm_metadata = await _extract_with_llm(text, filename, api_key)
        metadata.update(llm_metadata)
        logger.info(f"LLM metadata extraction succeeded for: {filename}")
    except Exception as e:
        logger.error(f"LLM metadata extraction failed for {filename}: {e}", exc_info=True)

    return metadata


def _extract_from_filename(filename: str) -> dict[str, Any]:
    """Extract basic metadata from filename.

    Args:
        filename: Original filename.

    Returns:
        Basic metadata dict.
    """
    import re
    from pathlib import Path

    metadata = {
        "filename": filename,
        "extracted_at": datetime.utcnow().isoformat(),
    }

    # Try to extract date from filename
    date_patterns = [
        r'(\d{4})[-_](\d{2})[-_](\d{2})',  # 2024-01-15
        r'(\d{2})[-_](\d{2})[-_](\d{4})',  # 15-01-2024
        r'(\d{4})(\d{2})(\d{2})',           # 20240115
    ]
    for pattern in date_patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()
            if len(groups[0]) == 4:
                metadata["filename_date"] = f"{groups[0]}-{groups[1]}-{groups[2]}"
            else:
                metadata["filename_date"] = f"{groups[2]}-{groups[1]}-{groups[0]}"
            break

    # Try to identify document type from filename
    name_lower = filename.lower()
    if "invoice" in name_lower:
        metadata["guessed_type"] = "invoice"
    elif "contract" in name_lower:
        metadata["guessed_type"] = "contract"
    elif "report" in name_lower:
        metadata["guessed_type"] = "company_report"
    elif "whitepaper" in name_lower or "white paper" in name_lower:
        metadata["guessed_type"] = "whitepaper"
    elif "presentation" in name_lower or "slides" in name_lower:
        metadata["guessed_type"] = "presentation"

    return metadata


async def _extract_with_llm(text: str, filename: str, api_key: str) -> dict[str, Any]:
    """Extract metadata using LLM.

    Args:
        text: Document text.
        filename: Original filename.
        api_key: OpenAI API key.

    Returns:
        Extracted metadata.
    """
    import openai

    client = openai.AsyncOpenAI(api_key=api_key)

    # Prepare prompt
    prompt = f"""Analyze this document and extract comprehensive metadata. Return a JSON object.

Filename: {filename}

Document content (first 10000 chars):
{text[:10000]}

Extract the following fields (use null if not determinable):
- title: The document title (infer from content if not explicit)
- short_description: A concise 2-3 sentence description of what this document is about and its purpose (max 300 chars)
- long_summary: A comprehensive 2-3 paragraph summary covering the main points, conclusions, and key information
- source_type: One of: {', '.join(DOCUMENT_TYPES)}
- main_topics: Array of 3-5 main topics discussed
- sectors: Array of relevant sectors from: {', '.join(SECTORS)}
- geographies: Array of countries/regions mentioned
- company_names: Array of company names mentioned
- authors: Array of author names if identifiable (look for signatures, "prepared by", "written by", etc.)
- publishing_organization: The organization that published or created this document
- document_created_date: When the document was originally created/dated (YYYY-MM-DD format, look for dates in headers, footers, or content)
- publication_date: When the document was published (YYYY-MM-DD format)
- language: Primary language (ISO code, e.g., "en", "es", "fr")
- key_metrics: Array of {{name, value}} for important metrics, numbers, or statistics mentioned
- document_purpose: Brief description of why this document was created (e.g., "investment proposal", "quarterly update", "legal agreement")
- confidentiality: Classification if mentioned (e.g., "confidential", "internal", "public")
- version: Document version if mentioned (e.g., "v1.0", "Draft", "Final")

Return ONLY valid JSON, no markdown formatting."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a document analysis expert. Extract metadata accurately and return valid JSON."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000,
        )

        content = response.choices[0].message.content.strip()

        # Clean up response
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        metadata = json.loads(content)

        # Validate and clean
        if isinstance(metadata.get("main_topics"), list):
            metadata["main_topics"] = metadata["main_topics"][:10]
        if isinstance(metadata.get("sectors"), list):
            metadata["sectors"] = [s for s in metadata["sectors"] if s in SECTORS]

        metadata["llm_extracted"] = True
        metadata["llm_model"] = "gpt-4o-mini"

        return metadata

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        return {"llm_error": "json_parse_error"}
    except Exception as e:
        logger.warning(f"LLM extraction failed: {e}")
        return {"llm_error": str(e)}
