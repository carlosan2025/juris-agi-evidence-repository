"""Base vocabulary definitions for extraction profiles."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricDefinition:
    """Definition of an extractable metric."""

    name: str  # Canonical name (e.g., "arr", "revenue")
    display_name: str  # Human-readable name
    description: str  # What this metric represents
    unit_type: str  # "currency", "percentage", "count", "ratio", "duration"
    aliases: list[str] = field(default_factory=list)  # Alternative names
    required_level: int = 1  # Minimum extraction level (1-4)
    calculation_notes: str | None = None  # How to calculate/interpret


@dataclass
class ClaimPredicate:
    """Definition of a claim predicate (assertion type)."""

    name: str  # Canonical predicate name
    display_name: str  # Human-readable name
    description: str  # What this predicate asserts
    subject_types: list[str]  # Valid subject types
    object_types: list[str]  # Valid object types
    required_level: int = 1  # Minimum extraction level


@dataclass
class RiskCategory:
    """Definition of a risk category."""

    name: str  # Canonical name
    display_name: str  # Human-readable name
    description: str  # What risks fall into this category
    indicators: list[str] = field(default_factory=list)  # What to look for
    required_level: int = 2  # Risks typically require L2+


class BaseVocabulary(ABC):
    """Abstract base class for domain-specific vocabularies.

    Each profile (General, VC, Pharma, Insurance) implements this
    to define domain-specific metrics, claims, and risks.
    """

    @property
    @abstractmethod
    def profile_code(self) -> str:
        """Return the profile code (e.g., 'vc', 'pharma')."""
        ...

    @property
    @abstractmethod
    def profile_name(self) -> str:
        """Return the human-readable profile name."""
        ...

    @abstractmethod
    def get_metrics(self, level: int = 1) -> list[MetricDefinition]:
        """Get metrics available at the specified extraction level.

        Args:
            level: Extraction level (1-4)

        Returns:
            List of metric definitions available at that level
        """
        ...

    @abstractmethod
    def get_claim_predicates(self, level: int = 1) -> list[ClaimPredicate]:
        """Get claim predicates available at the specified extraction level.

        Args:
            level: Extraction level (1-4)

        Returns:
            List of claim predicates available at that level
        """
        ...

    @abstractmethod
    def get_risk_categories(self, level: int = 2) -> list[RiskCategory]:
        """Get risk categories available at the specified extraction level.

        Args:
            level: Extraction level (2-4, risks typically not at L1)

        Returns:
            List of risk categories available at that level
        """
        ...

    def get_metric_by_name(self, name: str) -> MetricDefinition | None:
        """Look up a metric by name or alias."""
        name_lower = name.lower()
        for metric in self.get_metrics(level=4):  # Get all metrics
            if metric.name == name_lower or name_lower in [a.lower() for a in metric.aliases]:
                return metric
        return None

    def get_predicate_by_name(self, name: str) -> ClaimPredicate | None:
        """Look up a predicate by name."""
        name_lower = name.lower()
        for predicate in self.get_claim_predicates(level=4):
            if predicate.name == name_lower:
                return predicate
        return None

    def get_extraction_prompt_context(self, level: int) -> dict[str, Any]:
        """Get context for LLM extraction prompts at specified level.

        Returns a dict with metrics, predicates, and risks to extract.
        """
        return {
            "profile": self.profile_code,
            "profile_name": self.profile_name,
            "level": level,
            "metrics": [
                {
                    "name": m.name,
                    "display_name": m.display_name,
                    "description": m.description,
                    "unit_type": m.unit_type,
                    "aliases": m.aliases,
                }
                for m in self.get_metrics(level)
            ],
            "claim_predicates": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "subject_types": p.subject_types,
                    "object_types": p.object_types,
                }
                for p in self.get_claim_predicates(level)
            ],
            "risk_categories": [
                {
                    "name": r.name,
                    "display_name": r.display_name,
                    "description": r.description,
                    "indicators": r.indicators,
                }
                for r in self.get_risk_categories(level)
            ] if level >= 2 else [],
        }
