"""Controlled vocabularies for domain-specific extraction profiles."""

from evidence_repository.extraction.vocabularies.base import (
    BaseVocabulary,
    ClaimPredicate,
    MetricDefinition,
    RiskCategory,
)
from evidence_repository.extraction.vocabularies.general import GeneralVocabulary
from evidence_repository.extraction.vocabularies.insurance import InsuranceVocabulary
from evidence_repository.extraction.vocabularies.pharma import PharmaVocabulary
from evidence_repository.extraction.vocabularies.registry import (
    VocabularyRegistry,
    get_vocabulary,
    get_vocabulary_registry,
)
from evidence_repository.extraction.vocabularies.vc import VCVocabulary

__all__ = [
    # Base
    "BaseVocabulary",
    "ClaimPredicate",
    "MetricDefinition",
    "RiskCategory",
    # Vocabularies
    "GeneralVocabulary",
    "VCVocabulary",
    "PharmaVocabulary",
    "InsuranceVocabulary",
    # Registry
    "VocabularyRegistry",
    "get_vocabulary",
    "get_vocabulary_registry",
]
