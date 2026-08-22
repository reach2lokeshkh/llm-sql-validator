"""Core validation pipeline that orchestrates all 5 tiers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from llm_sql_validator.config import ValidatorConfig
from llm_sql_validator.result import ValidationResult, ValidationStatus
from llm_sql_validator.validators.base import BaseValidator
from llm_sql_validator.validators.business_rules import BusinessRulesValidator
from llm_sql_validator.validators.output import OutputValidator
from llm_sql_validator.validators.safety import SafetyValidator
from llm_sql_validator.validators.schema import SchemaValidator
from llm_sql_validator.validators.syntax import SyntaxValidator


class ValidationPipeline:
    """Orchestrates the 5-tier progressive validation pipeline.

    Validators are executed in order:
    1. Syntax — Can the SQL be parsed?
    2. Schema — Do all tables/columns exist?
    3. Business Rules — Does the query comply with domain policies?
    4. Safety — Is the query safe to execute?
    5. Output — Does it match known-bad patterns?

    The pipeline fails fast by default (stops at first failure).
    Set `fail_fast=False` to collect all errors across all tiers.
    """

    def __init__(
        self,
        config: Optional[ValidatorConfig] = None,
        fail_fast: bool = True,
    ) -> None:
        """Initialize the pipeline.

        Args:
            config: Validator configuration (schema, rules, safety settings).
            fail_fast: Stop at first tier failure (default True).
        """
        self.config = config or ValidatorConfig()
        self.fail_fast = fail_fast
        self._validators: list[BaseValidator] = self._build_default_validators()

    @classmethod
    def from_yaml(cls, path: str | Path, fail_fast: bool = True) -> ValidationPipeline:
        """Create a pipeline from a YAML config file.

        Args:
            path: Path to YAML configuration.
            fail_fast: Stop at first failure.

        Returns:
            Configured ValidationPipeline.
        """
        config = ValidatorConfig.from_yaml(path)
        return cls(config=config, fail_fast=fail_fast)

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Run the SQL through all validation tiers.

        Args:
            sql: The SQL query string to validate.
            context: Optional runtime context overrides.

        Returns:
            ValidationResult with aggregated pass/fail and all errors.
        """
        ctx = self._build_context(context)
        combined_result = ValidationResult(status=ValidationStatus.PASSED)

        for validator in self._validators:
            result = validator.validate(sql, context=ctx)

            combined_result = combined_result.merge(result)

            if self.fail_fast and result.status == ValidationStatus.FAILED:
                return combined_result

        return combined_result

    def register_validator(self, validator: BaseValidator) -> None:
        """Register a custom validator into the pipeline.

        Custom validators are appended after the default 5 tiers.
        Use this to add domain-specific validation logic.

        Args:
            validator: A BaseValidator subclass instance.
        """
        self._validators.append(validator)

    def record_anti_example(self, sql: str, reason: str) -> None:
        """Record a query that produced wrong results for future detection.

        Args:
            sql: The problematic SQL query.
            reason: Explanation of what went wrong.
        """
        for validator in self._validators:
            if isinstance(validator, OutputValidator):
                validator.record_anti_example(sql, reason)
                return

    @property
    def validators(self) -> list[BaseValidator]:
        """List of active validators in pipeline order."""
        return list(self._validators)

    def _build_default_validators(self) -> list[BaseValidator]:
        """Construct the default 5-tier validator chain from config."""
        safety_config = self.config.safety
        output_config = self.config.output

        return [
            SyntaxValidator(dialect=self.config.dialect),
            SchemaValidator(schema=self.config.schema, dialect=self.config.dialect),
            BusinessRulesValidator(
                rules=self.config.rules,
                schema=self.config.schema,
                dialect=self.config.dialect,
            ),
            SafetyValidator(
                read_only=safety_config.get("read_only", True),
                allow_ddl=safety_config.get("allow_ddl", False),
                max_join_tables=safety_config.get("max_join_tables", 6),
                block_cartesian=safety_config.get("block_cartesian", True),
                dialect=self.config.dialect,
            ),
            OutputValidator(
                anti_examples=output_config.get("anti_examples", []),
                similarity_threshold=output_config.get("similarity_threshold", 0.75),
            ),
        ]

    def _build_context(self, overrides: dict | None = None) -> dict:
        """Build the runtime context passed to each validator."""
        ctx = {
            "dialect": self.config.dialect,
            "schema": self.config.schema,
            "rules": self.config.rules,
        }
        if overrides:
            ctx.update(overrides)
        return ctx
