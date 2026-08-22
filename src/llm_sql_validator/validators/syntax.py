"""Tier 1: Syntax Validation - Parse and validate SQL grammar."""

from __future__ import annotations

from typing import Optional

import sqlglot
from sqlglot.errors import ParseError

from llm_sql_validator.result import (
    ValidationError,
    ValidationLevel,
    ValidationResult,
    ValidationStatus,
)
from llm_sql_validator.validators.base import BaseValidator


class SyntaxValidator(BaseValidator):
    """Validates SQL syntax by parsing with sqlglot.

    This is the first tier in the pipeline. If SQL can't be parsed,
    there's no point running further validation.

    Supports dialect-aware parsing (PostgreSQL, Redshift, BigQuery,
    Snowflake, MySQL, SQLite, DuckDB, Trino).
    """

    tier = ValidationLevel.SYNTAX

    def __init__(self, dialect: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dialect = dialect

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Parse the SQL and check for syntax errors.

        Args:
            sql: Raw SQL string from LLM output.
            context: Optional context (dialect override, etc.)

        Returns:
            ValidationResult indicating whether SQL is syntactically valid.
        """
        if not sql or not sql.strip():
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=[
                    ValidationError(
                        tier=self.tier,
                        code="EMPTY_QUERY",
                        message="SQL query is empty or contains only whitespace.",
                    )
                ],
            )

        dialect = (context or {}).get("dialect", self.dialect)

        try:
            parsed = sqlglot.parse(sql, dialect=dialect)

            if not parsed or all(stmt is None for stmt in parsed):
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    tier=self.tier,
                    errors=[
                        ValidationError(
                            tier=self.tier,
                            code="PARSE_EMPTY",
                            message="SQL parsed but produced no statements.",
                        )
                    ],
                )

            return ValidationResult(
                status=ValidationStatus.PASSED,
                tier=self.tier,
                metadata={
                    "statement_count": len([s for s in parsed if s is not None]),
                    "dialect": dialect or "generic",
                },
            )

        except ParseError as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=[
                    ValidationError(
                        tier=self.tier,
                        code="PARSE_ERROR",
                        message=f"SQL syntax error: {str(e)}",
                        suggestion="Verify SQL grammar matches the target dialect.",
                    )
                ],
            )
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=[
                    ValidationError(
                        tier=self.tier,
                        code="UNEXPECTED_ERROR",
                        message=f"Unexpected error during syntax parsing: {str(e)}",
                    )
                ],
            )
