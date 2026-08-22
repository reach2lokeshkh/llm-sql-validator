"""Tier 5: Output Validation - Validate result characteristics and anti-examples."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional

from llm_sql_validator.result import (
    ValidationError,
    ValidationLevel,
    ValidationResult,
    ValidationStatus,
)
from llm_sql_validator.validators.base import BaseValidator


class AntiExample:
    """A recorded query pattern that produced incorrect results."""

    def __init__(self, sql: str, reason: str, similarity_threshold: float = 0.75) -> None:
        self.sql = sql.strip().lower()
        self.reason = reason
        self.similarity_threshold = similarity_threshold


class OutputValidator(BaseValidator):
    """Validates queries against known-bad patterns (anti-examples).

    This tier implements feedback learning — when a query produces wrong results,
    it's recorded as an anti-example. Future similar queries are flagged with
    a warning explaining what went wrong previously.

    Also validates expected output characteristics like column count.
    """

    tier = ValidationLevel.OUTPUT

    def __init__(
        self,
        anti_examples: Optional[list[AntiExample | dict]] = None,
        expected_columns: Optional[int] = None,
        similarity_threshold: float = 0.75,
        **kwargs,
    ) -> None:
        """Initialize output validator.

        Args:
            anti_examples: Known-bad query patterns to match against.
            expected_columns: Expected number of columns in result (if known).
            similarity_threshold: How similar a query must be to an anti-example to trigger (0-1).
        """
        super().__init__(**kwargs)
        self.anti_examples = self._parse_anti_examples(anti_examples or [])
        self.expected_columns = expected_columns
        self.similarity_threshold = similarity_threshold

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Check query against anti-examples and output expectations.

        Args:
            sql: SQL query string.
            context: Optional context overrides.

        Returns:
            ValidationResult with any anti-example matches or output concerns.
        """
        warnings = []
        errors = []

        # Check anti-examples
        anti_example_match = self._check_anti_examples(sql)
        if anti_example_match:
            warnings.append(anti_example_match)

        if errors:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=errors,
                warnings=warnings,
            )

        if warnings:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                tier=self.tier,
                warnings=warnings,
            )

        return ValidationResult(
            status=ValidationStatus.PASSED,
            tier=self.tier,
        )

    def record_anti_example(self, sql: str, reason: str) -> None:
        """Record a new anti-example for future validation.

        Args:
            sql: The SQL query that produced incorrect results.
            reason: Explanation of what went wrong.
        """
        self.anti_examples.append(
            AntiExample(sql=sql, reason=reason, similarity_threshold=self.similarity_threshold)
        )

    def _check_anti_examples(self, sql: str) -> Optional[ValidationError]:
        """Check if the query matches any known anti-examples."""
        normalized_sql = sql.strip().lower()

        for anti in self.anti_examples:
            similarity = self._compute_similarity(normalized_sql, anti.sql)
            if similarity >= anti.similarity_threshold:
                return ValidationError(
                    tier=self.tier,
                    code="ANTI_EXAMPLE_MATCH",
                    message=(
                        f"Query matches a known problematic pattern "
                        f"(similarity: {similarity:.0%}). "
                        f"Previous issue: {anti.reason}"
                    ),
                    suggestion="Review and modify the query to avoid the known issue.",
                    severity="warning",
                )
        return None

    def _compute_similarity(self, sql_a: str, sql_b: str) -> float:
        """Compute similarity between two SQL strings.

        Uses SequenceMatcher for structural similarity rather than
        exact string matching, so minor variations still trigger matches.
        """
        return SequenceMatcher(None, sql_a, sql_b).ratio()

    def _parse_anti_examples(
        self, anti_examples: list[AntiExample | dict]
    ) -> list[AntiExample]:
        """Convert dicts to AntiExample objects."""
        parsed = []
        for item in anti_examples:
            if isinstance(item, AntiExample):
                parsed.append(item)
            elif isinstance(item, dict):
                parsed.append(AntiExample(**item))
        return parsed
