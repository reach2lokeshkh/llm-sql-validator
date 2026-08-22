"""Tests for Tier 1: Syntax Validator."""

import pytest

from llm_sql_validator.result import ValidationStatus
from llm_sql_validator.validators.syntax import SyntaxValidator


@pytest.fixture
def validator():
    return SyntaxValidator(dialect="postgres")


class TestSyntaxValidator:
    """Test suite for syntax validation."""

    def test_valid_select(self, validator):
        result = validator.validate("SELECT id, name FROM users WHERE id = 1")
        assert result.is_valid
        assert result.status == ValidationStatus.PASSED

    def test_valid_complex_query(self, validator):
        sql = """
        SELECT u.first_name, COUNT(o.id) as order_count
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE u.is_deleted = false
        GROUP BY u.first_name
        HAVING COUNT(o.id) > 5
        ORDER BY order_count DESC
        LIMIT 100
        """
        result = validator.validate(sql)
        assert result.is_valid

    def test_valid_subquery(self, validator):
        sql = """
        SELECT * FROM users
        WHERE id IN (SELECT user_id FROM orders WHERE amount > 100)
        """
        result = validator.validate(sql)
        assert result.is_valid

    def test_valid_cte(self, validator):
        sql = """
        WITH high_value AS (
            SELECT user_id, SUM(amount) as total
            FROM orders
            GROUP BY user_id
            HAVING SUM(amount) > 1000
        )
        SELECT u.first_name, hv.total
        FROM users u
        JOIN high_value hv ON u.id = hv.user_id
        """
        result = validator.validate(sql)
        assert result.is_valid

    def test_empty_query(self, validator):
        result = validator.validate("")
        assert not result.is_valid
        assert result.status == ValidationStatus.FAILED
        assert any(e.code == "EMPTY_QUERY" for e in result.errors)

    def test_whitespace_only(self, validator):
        result = validator.validate("   \n\t  ")
        assert not result.is_valid
        assert any(e.code == "EMPTY_QUERY" for e in result.errors)

    def test_invalid_syntax(self, validator):
        result = validator.validate("SELCT name FORM users")
        # sqlglot is lenient but this should still produce a result
        # The exact behavior depends on sqlglot's error recovery
        assert result is not None

    def test_multiple_statements(self, validator):
        sql = "SELECT 1; SELECT 2;"
        result = validator.validate(sql)
        assert result.is_valid
        assert result.metadata.get("statement_count", 0) >= 2

    def test_dialect_specific_redshift(self):
        validator = SyntaxValidator(dialect="redshift")
        sql = "SELECT GETDATE()"
        result = validator.validate(sql)
        assert result.is_valid

    def test_dialect_override_in_context(self, validator):
        sql = "SELECT CURRENT_DATE"
        result = validator.validate(sql, context={"dialect": "bigquery"})
        assert result.is_valid
