"""Vocabulary registry for profile-based extraction."""

from evidence_repository.extraction.vocabularies.base import BaseVocabulary
from evidence_repository.extraction.vocabularies.general import GeneralVocabulary
from evidence_repository.extraction.vocabularies.insurance import InsuranceVocabulary
from evidence_repository.extraction.vocabularies.pharma import PharmaVocabulary
from evidence_repository.extraction.vocabularies.vc import VCVocabulary


class VocabularyRegistry:
    """Registry for looking up vocabularies by profile code."""

    _instance: "VocabularyRegistry | None" = None
    _vocabularies: dict[str, BaseVocabulary]

    def __new__(cls) -> "VocabularyRegistry":
        """Singleton pattern for vocabulary registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._vocabularies = {}
            cls._instance._register_defaults()
        return cls._instance

    def _register_defaults(self) -> None:
        """Register default vocabularies."""
        self.register(GeneralVocabulary())
        self.register(VCVocabulary())
        self.register(PharmaVocabulary())
        self.register(InsuranceVocabulary())

    def register(self, vocabulary: BaseVocabulary) -> None:
        """Register a vocabulary.

        Args:
            vocabulary: Vocabulary instance to register
        """
        self._vocabularies[vocabulary.profile_code] = vocabulary

    def get(self, profile_code: str) -> BaseVocabulary | None:
        """Get vocabulary by profile code.

        Args:
            profile_code: Profile code (e.g., 'vc', 'pharma')

        Returns:
            Vocabulary instance or None if not found
        """
        return self._vocabularies.get(profile_code)

    def get_or_default(self, profile_code: str) -> BaseVocabulary:
        """Get vocabulary by profile code, falling back to general.

        Args:
            profile_code: Profile code (e.g., 'vc', 'pharma')

        Returns:
            Vocabulary instance (general if not found)
        """
        return self._vocabularies.get(profile_code, self._vocabularies["general"])

    def list_profiles(self) -> list[str]:
        """List all registered profile codes."""
        return list(self._vocabularies.keys())

    def list_vocabularies(self) -> list[BaseVocabulary]:
        """List all registered vocabularies."""
        return list(self._vocabularies.values())


# Convenience function for getting the registry
def get_vocabulary_registry() -> VocabularyRegistry:
    """Get the vocabulary registry singleton."""
    return VocabularyRegistry()


# Convenience function for getting a vocabulary
def get_vocabulary(profile_code: str) -> BaseVocabulary:
    """Get vocabulary by profile code.

    Args:
        profile_code: Profile code (e.g., 'vc', 'pharma', 'insurance', 'general')

    Returns:
        Vocabulary instance (falls back to general if not found)
    """
    return get_vocabulary_registry().get_or_default(profile_code)
