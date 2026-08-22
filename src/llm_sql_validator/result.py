"""Validation result types and status enums."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    """Status of a validation check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class ValidationLevel(str, Enum):
    """Tiers in the progressive validation pipeline."""

    SYNTAX = "SYNTAX"
    SCHEMA = "SCHEMA"
    BUSINESS_RULES = "BUSINESS_RULES"
    SAFETY = "SAFETY"
    OUTPUT = "OUTPUT"


class ValidationError(BaseModel):
    """A single validation error with context."""

    tier: ValidationLevel
    code: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    suggestion: Optional[str] = None
    severity: str = "error"  # error, warning, info


class ValidationResult(BaseModel):
    """Result from a single validator or the full pipeline."""

    status: ValidationStatus
    tier: Optional[ValidationLevel] = None
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[ValidationError] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Query passed all validation checks."""
        return self.status in (ValidationStatus.PASSED, ValidationStatus.WARNING)

    @property
    def failed_tier(self) -> Optional[ValidationLevel]:
        """The tier where validation failed, if any."""
        if self.status == ValidationStatus.FAILED and self.errors:
            return self.errors[0].tier
        return None

    @property
    def error_messages(self) -> list[str]:
        """Flat list of error message strings."""
        return [e.message for e in self.errors]

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another result into this one (for pipeline aggregation)."""
        combined_errors = self.errors + other.errors
        combined_warnings = self.warnings + other.warnings
        combined_metadata = {**self.metadata, **other.metadata}

        if other.status == ValidationStatus.FAILED:
            status = ValidationStatus.FAILED
        elif self.status == ValidationStatus.FAILED:
            status = ValidationStatus.FAILED
        elif combined_warnings:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        return ValidationResult(
            status=status,
            tier=other.tier if other.status == ValidationStatus.FAILED else self.tier,
            errors=combined_errors,
            warnings=combined_warnings,
            metadata=combined_metadata,
        )
