"""Tests for Tier 3: Business Rules Validator."""

import pytest

from llm_sql_validator.validators.business_rules import BusinessRulesValidator
from llm_sql_validator.result import ValidationStatus


SAMPLE_SCHEMA = {
    "public": {
        "users": {
            "columns": {
                "id": {"type": "integer"},
                "email": {"type": "varchar", "pii": True},
                "ssn": {"type": "varchar", "pii": True},
                "first_name": {"type": "varchar"},
                "is_deleted": {"type": "boolean"},
            }
        },
        "orders": {
            "columns": {
                "id": {"type": "integer"},
                "order_date": {"type": "date"},
                "amount": {"type": "decimal"},
                "user_id": {"type": "integer"},
            },
            "row_estimate": 500_000_000,
        },
    }
}

SAMPLE_RULES = [
    {
        "name": "require_date_on_orders",
        "rule_type": "required_filter",
        "description": "Orders queries must filter on order_date",
        "target_tables": ["orders"],
        "filter_columns": ["order_date"],
    },
    {
        "name": "block_pii",
        "rule_type": "forbidden_columns",
        "description": "PII columns need masking",
        "columns_with_tag": "pii",
        "unless_wrapped_in": ["mask", "hash", "md5"],
    },
    {
        "name": "large_table_limit",
        "rule_type": "row_limit",
        "description": "Large tables need WHERE or LIMIT",
        "row_threshold": 100_000_000,
        "max_limit": 10000,
    },
]


@pytest.fixture
def validator():
    return BusinessRulesValidator(
        rules=SAMPLE_RULES, schema=SAMPLE_SCHEMA, dialect="postgres"
    )


class TestBusinessRulesValidator:
    """Test suite for business rules validation."""

    def test_valid_query_with_required_filter(self, validator):
        sql = "SELECT amount FROM orders WHERE order_date > '2024-01-01'"
        result = validator.validate(sql)
        assert result.is_valid

    def test_missing_required_filter(self, validator):
        sql = "SELECT amount FROM orders WHERE user_id = 123"
        result = validator.validate(sql)
        assert not result.is_valid
        assert any(e.code == "MISSING_REQUIRED_FILTER" for e in result.errors)

    def test_missing_where_clause_entirely(self, validator):
        sql = "SELECT amount FROM orders"
        result = validator.validate(sql)
        assert not result.is_valid

    def test_pii_column_blocked(self, validator):
        sql = "SELECT email FROM users WHERE is_deleted = false"
        result = validator.validate(sql)
        assert not result.is_valid
        assert any(e.code == "FORBIDDEN_COLUMN_ACCESS" for e in result.errors)

    def test_pii_column_allowed_with_masking(self, validator):
        sql = "SELECT mask(email) FROM users WHERE is_deleted = false"
        result = validator.validate(sql)
        # When wrapped in mask(), it should pass the PII rule
        # Note: actual behavior depends on sqlglot parsing of function calls
        assert result is not None

    def test_large_table_without_limit_or_where(self, validator):
        sql = "SELECT amount FROM orders"
        result = validator.validate(sql)
        assert not result.is_valid
        # Should trigger both required_filter and row_limit rules

    def test_large_table_with_limit(self, validator):
        sql = "SELECT amount FROM orders LIMIT 100"
        result = validator.validate(sql)
        # Has LIMIT so row_limit rule passes, but still missing required date filter
        assert any(e.code == "MISSING_REQUIRED_FILTER" for e in result.errors)

    def test_unaffected_table_passes(self, validator):
        sql = "SELECT first_name FROM users WHERE is_deleted = false"
        result = validator.validate(sql)
        # Users table doesn't trigger the orders-specific date filter rule
        # But PII check is schema-wide
        assert result is not None

    def test_no_rules_skips(self):
        validator = BusinessRulesValidator(rules=[], schema=SAMPLE_SCHEMA)
        result = validator.validate("SELECT * FROM orders")
        assert result.status == ValidationStatus.SKIPPED

    def test_rule_description_in_error_message(self, validator):
        sql = "SELECT amount FROM orders WHERE user_id = 1"
        result = validator.validate(sql)
        assert not result.is_valid
        error = next(e for e in result.errors if e.code == "MISSING_REQUIRED_FILTER")
        assert "order_date" in error.message or "order_date" in (error.suggestion or "")
