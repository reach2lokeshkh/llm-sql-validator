"""Base validator interface that all tier validators implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from llm_sql_validator.result import ValidationLevel, ValidationResult


class BaseValidator(ABC):
    """Abstract base class for all validators in the pipeline.

    Each validator represents one tier in the progressive validation pipeline.
    Validators are executed in order, and the pipeline stops at the first failure
    (fail-fast behavior) unless configured otherwise.
    """

    tier: ValidationLevel

    def __init__(self, config: Any = None) -> None:
        self.config = config

    @abstractmethod
    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Validate the SQL query.

        Args:
            sql: The SQL query string to validate.
            context: Optional context dict with schema info, rules, etc.

        Returns:
            ValidationResult with pass/fail status and any errors.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name for this validator."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"<{self.name} tier={self.tier.value}>"
