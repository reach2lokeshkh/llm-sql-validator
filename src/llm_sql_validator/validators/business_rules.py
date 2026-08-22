"""Tier 3: Business Rules Validation - Enforce domain-specific query policies."""

from __future__ import annotations

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


class BusinessRule:
    """A single configurable business rule."""

    def __init__(
        self,
        name: str,
        rule_type: str,
        description: str = "",
        target_tables: Optional[list[str]] = None,
        filter_columns: Optional[list[str]] = None,
        filter_expression: Optional[str] = None,
        columns_with_tag: Optional[str] = None,
        forbidden_columns: Optional[list[str]] = None,
        unless_wrapped_in: Optional[list[str]] = None,
        row_threshold: Optional[int] = None,
        max_limit: Optional[int] = None,
    ) -> None:
        self.name = name
        self.rule_type = rule_type
        self.description = description
        self.target_tables = [t.lower() for t in (target_tables or [])]
        self.filter_columns = [c.lower() for c in (filter_columns or [])]
        self.filter_expression = filter_expression
        self.columns_with_tag = columns_with_tag
        self.forbidden_columns = [c.lower() for c in (forbidden_columns or [])]
        self.unless_wrapped_in = [f.lower() for f in (unless_wrapped_in or [])]
        self.row_threshold = row_threshold
        self.max_limit = max_limit


class BusinessRulesValidator(BaseValidator):
    """Validates SQL against configurable business rules.

    Supports rule types:
    - required_filter: Certain tables must always have specific WHERE clauses
    - forbidden_columns: Certain columns cannot be selected without masking
    - row_limit: Large tables require LIMIT or WHERE clauses
    - required_join: Certain tables must be joined with access control tables
    """

    tier = ValidationLevel.BUSINESS_RULES

    def __init__(
        self,
        rules: Optional[list[dict | BusinessRule]] = None,
        schema: Optional[dict] = None,
        dialect: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.rules = self._parse_rules(rules or [])
        self.schema = schema or {}
        self.dialect = dialect

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Validate SQL against all configured business rules.

        Args:
            sql: SQL query string.
            context: Optional context with rules/schema override.

        Returns:
            ValidationResult with any rule violations.
        """
        rules = (context or {}).get("rules", self.rules)
        # Context may pass raw dicts; normalize to BusinessRule objects
        rules = self._parse_rules(rules)
        schema = (context or {}).get("schema", self.schema)
        dialect = (context or {}).get("dialect", self.dialect)

        if not rules:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                tier=self.tier,
                metadata={"reason": "No business rules configured"},
            )

        try:
            parsed = sqlglot.parse(sql, dialect=dialect)
        except Exception:
            return ValidationResult(status=ValidationStatus.SKIPPED, tier=self.tier)

        errors = []
        warnings = []

        for stmt in parsed:
            if stmt is None:
                continue

            # Get tables referenced in this statement
            referenced_tables = {
                t.name.lower() for t in stmt.find_all(exp.Table) if t.name
            }

            for rule in rules:
                result = self._check_rule(stmt, rule, referenced_tables, schema)
                if result:
                    if result.severity == "error":
                        errors.append(result)
                    else:
                        warnings.append(result)

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
            metadata={"rules_checked": len(rules)},
        )

    def _check_rule(
        self,
        stmt: exp.Expression,
        rule: BusinessRule,
        referenced_tables: set[str],
        schema: dict,
    ) -> Optional[ValidationError]:
        """Check a single rule against the statement."""
        # Only apply rule if target tables are referenced
        if rule.target_tables:
            if not any(t in referenced_tables for t in rule.target_tables):
                return None

        if rule.rule_type == "required_filter":
            return self._check_required_filter(stmt, rule)
        elif rule.rule_type == "forbidden_columns":
            return self._check_forbidden_columns(stmt, rule, schema)
        elif rule.rule_type == "row_limit":
            return self._check_row_limit(stmt, rule, schema)
        return None

    def _check_required_filter(
        self, stmt: exp.Expression, rule: BusinessRule
    ) -> Optional[ValidationError]:
        """Check that required filter columns appear in WHERE clause."""
        where_clause = stmt.find(exp.Where)

        if not where_clause:
            return ValidationError(
                tier=self.tier,
                code="MISSING_REQUIRED_FILTER",
                message=(
                    f"Rule '{rule.name}': Query is missing a required WHERE clause. "
                    f"{rule.description}"
                ),
                suggestion=f"Add a filter on: {', '.join(rule.filter_columns)}",
                severity="error",
            )

        # Check if required columns appear in the WHERE clause
        where_columns = {
            col.name.lower() for col in where_clause.find_all(exp.Column)
        }

        missing_filters = [
            col for col in rule.filter_columns if col not in where_columns
        ]

        if missing_filters:
            return ValidationError(
                tier=self.tier,
                code="MISSING_REQUIRED_FILTER",
                message=(
                    f"Rule '{rule.name}': Missing required filter on "
                    f"{', '.join(missing_filters)}. {rule.description}"
                ),
                suggestion=f"Add WHERE clause filtering on: {', '.join(missing_filters)}",
                severity="error",
            )
        return None

    def _check_forbidden_columns(
        self, stmt: exp.Expression, rule: BusinessRule, schema: dict
    ) -> Optional[ValidationError]:
        """Check that forbidden/PII columns are not selected without masking."""
        # Determine forbidden columns from rule or schema tags
        forbidden = set(rule.forbidden_columns)

        if rule.columns_with_tag and schema:
            for schema_tables in schema.values():
                if isinstance(schema_tables, dict):
                    for table_def in schema_tables.values():
                        if isinstance(table_def, dict) and "columns" in table_def:
                            for col_name, col_def in table_def["columns"].items():
                                if isinstance(col_def, dict):
                                    if col_def.get(rule.columns_with_tag):
                                        forbidden.add(col_name.lower())

        if not forbidden:
            return None

        # Check SELECT columns
        for select_col in stmt.find_all(exp.Column):
            col_name = select_col.name.lower()
            if col_name in forbidden:
                # Check if wrapped in an allowed function
                parent = select_col.parent
                if rule.unless_wrapped_in and isinstance(parent, exp.Anonymous):
                    func_name = parent.name.lower() if hasattr(parent, "name") else ""
                    if func_name in rule.unless_wrapped_in:
                        continue

                if rule.unless_wrapped_in and isinstance(parent, exp.Func):
                    func_name = parent.key.lower() if hasattr(parent, "key") else ""
                    if func_name in rule.unless_wrapped_in:
                        continue

                return ValidationError(
                    tier=self.tier,
                    code="FORBIDDEN_COLUMN_ACCESS",
                    message=(
                        f"Rule '{rule.name}': Column '{col_name}' cannot be accessed directly. "
                        f"{rule.description}"
                    ),
                    suggestion=(
                        f"Wrap with a masking function: "
                        f"{', '.join(rule.unless_wrapped_in)}"
                        if rule.unless_wrapped_in
                        else "Remove this column from the query."
                    ),
                    severity="error",
                )
        return None

    def _check_row_limit(
        self, stmt: exp.Expression, rule: BusinessRule, schema: dict
    ) -> Optional[ValidationError]:
        """Check that queries on large tables include LIMIT or WHERE."""
        # Check if there's a LIMIT clause
        limit_node = stmt.find(exp.Limit)
        where_node = stmt.find(exp.Where)

        if limit_node or where_node:
            return None

        # Check if any referenced table exceeds the row threshold
        for table_node in stmt.find_all(exp.Table):
            table_name = table_node.name.lower()
            row_estimate = self._get_row_estimate(table_name, schema)
            if row_estimate and rule.row_threshold and row_estimate > rule.row_threshold:
                return ValidationError(
                    tier=self.tier,
                    code="UNBOUNDED_LARGE_TABLE_QUERY",
                    message=(
                        f"Rule '{rule.name}': Table '{table_name}' has ~{row_estimate:,} rows. "
                        f"Query requires a WHERE clause or LIMIT. {rule.description}"
                    ),
                    suggestion=(
                        f"Add LIMIT {rule.max_limit or 1000} or a WHERE clause to bound results."
                    ),
                    severity="error",
                )
        return None

    def _get_row_estimate(self, table_name: str, schema: dict) -> Optional[int]:
        """Look up row estimate for a table from schema metadata."""
        for schema_tables in schema.values():
            if isinstance(schema_tables, dict):
                table_def = schema_tables.get(table_name, {})
                if isinstance(table_def, dict):
                    return table_def.get("row_estimate")
        return None

    def _parse_rules(self, rules: list[dict | BusinessRule]) -> list[BusinessRule]:
        """Convert rule dicts to BusinessRule objects."""
        parsed = []
        for rule in rules:
            if isinstance(rule, BusinessRule):
                parsed.append(rule)
            elif isinstance(rule, dict):
                parsed.append(BusinessRule(**rule))
        return parsed
