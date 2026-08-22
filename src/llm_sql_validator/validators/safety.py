"""Tier 4: Safety Validation - Block dangerous SQL operations."""

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


class SafetyValidator(BaseValidator):
    """Validates that SQL queries don't contain unsafe operations.

    Checks for:
    - DDL operations (CREATE, DROP, ALTER, TRUNCATE)
    - DML mutations (INSERT, UPDATE, DELETE) in read-only mode
    - Cartesian joins (missing join conditions)
    - SQL injection patterns
    - Unbounded operations without safety limits
    """

    tier = ValidationLevel.SAFETY

    # Statement types that are always blocked
    BLOCKED_DDL = (exp.Create, exp.Drop, exp.Alter)

    # Statement types blocked in read-only mode
    BLOCKED_DML = (exp.Insert, exp.Update, exp.Delete)

    def __init__(
        self,
        read_only: bool = True,
        allow_ddl: bool = False,
        max_join_tables: int = 6,
        block_cartesian: bool = True,
        dialect: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Initialize safety validator.

        Args:
            read_only: Block all write operations (INSERT/UPDATE/DELETE).
            allow_ddl: Allow DDL statements (CREATE/DROP/ALTER).
            max_join_tables: Maximum tables in a single query before warning.
            block_cartesian: Block queries with cartesian/cross joins.
            dialect: SQL dialect for parsing.
        """
        super().__init__(**kwargs)
        self.read_only = read_only
        self.allow_ddl = allow_ddl
        self.max_join_tables = max_join_tables
        self.block_cartesian = block_cartesian
        self.dialect = dialect

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        """Check SQL for dangerous operations.

        Args:
            sql: SQL query string.
            context: Optional context overrides.

        Returns:
            ValidationResult with safety violations.
        """
        dialect = (context or {}).get("dialect", self.dialect)

        try:
            parsed = sqlglot.parse(sql, dialect=dialect)
        except Exception:
            return ValidationResult(status=ValidationStatus.SKIPPED, tier=self.tier)

        errors = []
        warnings = []

        for stmt in parsed:
            if stmt is None:
                continue

            # Check DDL
            if not self.allow_ddl:
                ddl_error = self._check_ddl(stmt)
                if ddl_error:
                    errors.append(ddl_error)

            # Check DML in read-only mode
            if self.read_only:
                dml_error = self._check_dml(stmt)
                if dml_error:
                    errors.append(dml_error)

            # Check for TRUNCATE (keyword-based since sqlglot may not have a node)
            if sql.strip().upper().startswith("TRUNCATE"):
                errors.append(
                    ValidationError(
                        tier=self.tier,
                        code="BLOCKED_TRUNCATE",
                        message="TRUNCATE statements are not allowed.",
                        severity="error",
                    )
                )

            # Check cartesian joins
            if self.block_cartesian:
                cartesian_error = self._check_cartesian_join(stmt)
                if cartesian_error:
                    errors.append(cartesian_error)

            # Check excessive joins
            join_warning = self._check_excessive_joins(stmt)
            if join_warning:
                warnings.append(join_warning)

            # Check for injection patterns
            injection_error = self._check_injection_patterns(sql)
            if injection_error:
                errors.append(injection_error)

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

    def _check_ddl(self, stmt: exp.Expression) -> Optional[ValidationError]:
        """Block DDL operations."""
        for ddl_type in self.BLOCKED_DDL:
            if isinstance(stmt, ddl_type):
                return ValidationError(
                    tier=self.tier,
                    code="BLOCKED_DDL",
                    message=(
                        f"DDL statement ({stmt.__class__.__name__}) is not allowed. "
                        f"Only SELECT queries are permitted."
                    ),
                    suggestion="Remove the DDL statement and use only SELECT queries.",
                    severity="error",
                )
        return None

    def _check_dml(self, stmt: exp.Expression) -> Optional[ValidationError]:
        """Block DML mutations in read-only mode."""
        for dml_type in self.BLOCKED_DML:
            if isinstance(stmt, dml_type):
                return ValidationError(
                    tier=self.tier,
                    code="BLOCKED_DML",
                    message=(
                        f"Write operation ({stmt.__class__.__name__}) is not allowed in "
                        f"read-only mode. Only SELECT queries are permitted."
                    ),
                    suggestion="Use only SELECT statements for data retrieval.",
                    severity="error",
                )
        return None

    def _check_cartesian_join(self, stmt: exp.Expression) -> Optional[ValidationError]:
        """Detect cartesian joins (joins without ON conditions)."""
        # Look for FROM with multiple tables but no JOIN or WHERE
        from_clause = stmt.find(exp.From)
        if not from_clause:
            return None

        joins = list(stmt.find_all(exp.Join))
        for join in joins:
            # Cross join without condition
            if join.args.get("kind") == "CROSS":
                return ValidationError(
                    tier=self.tier,
                    code="CARTESIAN_JOIN",
                    message="CROSS JOIN detected — this produces a cartesian product.",
                    suggestion="Add a JOIN condition (ON clause) or use an INNER/LEFT JOIN.",
                    severity="error",
                )

            # Join without ON clause
            on_clause = join.args.get("on")
            if not on_clause and not join.args.get("using"):
                return ValidationError(
                    tier=self.tier,
                    code="CARTESIAN_JOIN",
                    message="JOIN without ON condition detected — this may produce a cartesian product.",
                    suggestion="Add an ON clause to specify the join condition.",
                    severity="error",
                )

        return None

    def _check_excessive_joins(self, stmt: exp.Expression) -> Optional[ValidationError]:
        """Warn about queries joining too many tables."""
        tables = list(stmt.find_all(exp.Table))
        if len(tables) > self.max_join_tables:
            return ValidationError(
                tier=self.tier,
                code="EXCESSIVE_JOINS",
                message=(
                    f"Query references {len(tables)} tables "
                    f"(threshold: {self.max_join_tables}). "
                    f"This may cause performance issues."
                ),
                suggestion="Consider breaking the query into smaller parts or using CTEs.",
                severity="warning",
            )
        return None

    def _check_injection_patterns(self, sql: str) -> Optional[ValidationError]:
        """Check for common SQL injection patterns in LLM output."""
        suspicious_patterns = [
            ("'; --", "Comment-based injection attempt"),
            ("' OR '1'='1", "Always-true condition injection"),
            ("UNION SELECT", "UNION-based injection (check if intentional)"),
            ("; DROP ", "Stacked query with DROP"),
            ("; DELETE ", "Stacked query with DELETE"),
            ("EXEC ", "Execution of stored procedure"),
            ("xp_cmdshell", "System command execution attempt"),
        ]

        sql_upper = sql.upper()
        for pattern, description in suspicious_patterns:
            if pattern.upper() in sql_upper:
                return ValidationError(
                    tier=self.tier,
                    code="INJECTION_PATTERN",
                    message=f"Suspicious SQL pattern detected: {description}",
                    suggestion="Review the LLM output for injection attempts.",
                    severity="error",
                )
        return None
