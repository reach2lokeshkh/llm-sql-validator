"""Tier 2: Schema Validation - Verify tables and columns exist."""

from __future__ import annotations

from difflib import get_close_matches
from typing import Optional

import sqlglot
from sqlglot import exp

from llm_sql_validator.result import (
    ValidationError,
    ValidationLevel,
    ValidationResult,
    ValidationStatus,
)
from llm_sql_validator.validators.base import BaseValidator


class SchemaValidator(BaseValidator):
    """Validates that all referenced tables and columns exist in the schema.

    Provides fuzzy matching suggestions when column/table names are close
    but not exact matches (common LLM hallucination pattern).
    """

    tier = ValidationLevel.SCHEMA

    def __init__(
        self,
        schema: Optional[dict] = None,
        dialect: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Initialize with schema definition.

        Args:
            schema: Dict mapping schema_name -> table_name -> {columns: {col: {type, ...}}}
            dialect: SQL dialect for parsing.
        """
        super().__init__(**kwargs)
        self.schema = schema or {}
        self.dialect = dialect

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Validate all table/column references against the known schema.

        Args:
            sql: Parsed-valid SQL string.
            context: Optional context with schema override.

        Returns:
            ValidationResult with any missing table/column errors.
        """
        schema = (context or {}).get("schema", self.schema)
        dialect = (context or {}).get("dialect", self.dialect)

        if not schema:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                tier=self.tier,
                metadata={"reason": "No schema provided for validation"},
            )

        try:
            parsed = sqlglot.parse(sql, dialect=dialect)
        except Exception:
            # Syntax validator should have caught this
            return ValidationResult(status=ValidationStatus.SKIPPED, tier=self.tier)

        errors = []
        all_tables = self._get_all_tables(schema)
        all_columns_by_table = self._get_all_columns(schema)

        for stmt in parsed:
            if stmt is None:
                continue

            # Validate table references
            for table_node in stmt.find_all(exp.Table):
                table_name = table_node.name.lower()
                schema_name = (table_node.db or "").lower()

                if table_name and table_name not in all_tables:
                    suggestion = self._suggest_table(table_name, all_tables)
                    errors.append(
                        ValidationError(
                            tier=self.tier,
                            code="TABLE_NOT_FOUND",
                            message=f"Table '{table_name}' does not exist in the schema.",
                            suggestion=suggestion,
                        )
                    )

            # Validate column references
            for col_node in stmt.find_all(exp.Column):
                col_name = col_node.name.lower()
                table_ref = (col_node.table or "").lower()

                if col_name in ("*",):
                    continue

                if table_ref and table_ref in all_columns_by_table:
                    table_columns = all_columns_by_table[table_ref]
                    if col_name not in table_columns:
                        suggestion = self._suggest_column(col_name, table_columns)
                        errors.append(
                            ValidationError(
                                tier=self.tier,
                                code="COLUMN_NOT_FOUND",
                                message=(
                                    f"Column '{col_name}' does not exist in table '{table_ref}'."
                                ),
                                suggestion=suggestion,
                            )
                        )
                elif not table_ref:
                    # Column without table qualifier — check across all tables
                    found = any(
                        col_name in cols for cols in all_columns_by_table.values()
                    )
                    if not found and all_columns_by_table:
                        all_cols = set()
                        for cols in all_columns_by_table.values():
                            all_cols.update(cols)
                        suggestion = self._suggest_column(col_name, all_cols)
                        errors.append(
                            ValidationError(
                                tier=self.tier,
                                code="COLUMN_NOT_FOUND",
                                message=(
                                    f"Column '{col_name}' not found in any known table."
                                ),
                                suggestion=suggestion,
                            )
                        )

        if errors:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=errors,
            )

        return ValidationResult(
            status=ValidationStatus.PASSED,
            tier=self.tier,
            metadata={"tables_validated": len(all_tables)},
        )

    def _get_all_tables(self, schema: dict) -> set[str]:
        """Extract all table names from the schema definition."""
        tables = set()
        for schema_name, schema_tables in schema.items():
            if isinstance(schema_tables, dict):
                for table_name in schema_tables:
                    tables.add(table_name.lower())
        return tables

    def _get_all_columns(self, schema: dict) -> dict[str, set[str]]:
        """Extract all columns grouped by table."""
        columns_by_table: dict[str, set[str]] = {}
        for schema_name, schema_tables in schema.items():
            if isinstance(schema_tables, dict):
                for table_name, table_def in schema_tables.items():
                    if isinstance(table_def, dict) and "columns" in table_def:
                        cols = {c.lower() for c in table_def["columns"]}
                        columns_by_table[table_name.lower()] = cols
        return columns_by_table

    def _suggest_table(self, name: str, known_tables: set[str]) -> Optional[str]:
        """Fuzzy match a table name and suggest corrections."""
        matches = get_close_matches(name, list(known_tables), n=2, cutoff=0.6)
        if matches:
            return f"Did you mean: {', '.join(repr(m) for m in matches)}?"
        return None

    def _suggest_column(self, name: str, known_columns: set[str]) -> Optional[str]:
        """Fuzzy match a column name and suggest corrections."""
        matches = get_close_matches(name, list(known_columns), n=3, cutoff=0.5)
        if matches:
            return f"Did you mean: {', '.join(repr(m) for m in matches)}?"
        return None
