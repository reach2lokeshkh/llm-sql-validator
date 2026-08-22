"""Tests for Tier 2: Schema Validator."""

import pytest

from llm_sql_validator.result import ValidationStatus
from llm_sql_validator.validators.schema import SchemaValidator

SAMPLE_SCHEMA = {
    "public": {
        "users": {
            "columns": {
                "id": {"type": "integer", "primary_key": True},
                "first_name": {"type": "varchar"},
                "last_name": {"type": "varchar"},
                "email": {"type": "varchar", "pii": True},
                "created_at": {"type": "timestamp"},
                "is_deleted": {"type": "boolean"},
            }
        },
        "orders": {
            "columns": {
                "id": {"type": "integer", "primary_key": True},
                "user_id": {"type": "integer"},
                "amount": {"type": "decimal"},
                "order_date": {"type": "date"},
                "status": {"type": "varchar"},
            }
        },
    }
}


@pytest.fixture
def validator():
    return SchemaValidator(schema=SAMPLE_SCHEMA, dialect="postgres")


class TestSchemaValidator:
    """Test suite for schema validation."""

    def test_valid_columns(self, validator):
        sql = "SELECT first_name, last_name FROM users"
        result = validator.validate(sql)
        assert result.is_valid

    def test_valid_qualified_columns(self, validator):
        sql = "SELECT users.first_name, users.email FROM users"
        result = validator.validate(sql)
        assert result.is_valid

    def test_nonexistent_column(self, validator):
        sql = "SELECT customer_name FROM users"
        result = validator.validate(sql)
        assert not result.is_valid
        assert result.status == ValidationStatus.FAILED
        assert any(e.code == "COLUMN_NOT_FOUND" for e in result.errors)

    def test_nonexistent_table(self, validator):
        sql = "SELECT id FROM customers"
        result = validator.validate(sql)
        assert not result.is_valid
        assert any(e.code == "TABLE_NOT_FOUND" for e in result.errors)

    def test_fuzzy_column_suggestion(self, validator):
        sql = "SELECT firstname FROM users"
        result = validator.validate(sql)
        assert not result.is_valid
        # Should suggest 'first_name'
        error = next(e for e in result.errors if e.code == "COLUMN_NOT_FOUND")
        assert error.suggestion is not None
        assert "first_name" in error.suggestion

    def test_fuzzy_table_suggestion(self, validator):
        sql = "SELECT id FROM user"
        result = validator.validate(sql)
        assert not result.is_valid
        error = next(e for e in result.errors if e.code == "TABLE_NOT_FOUND")
        assert error.suggestion is not None
        assert "users" in error.suggestion

    def test_join_with_valid_columns(self, validator):
        sql = """
        SELECT u.first_name, o.amount
        FROM users u
        JOIN orders o ON u.id = o.user_id
        """
        result = validator.validate(sql)
        assert result.is_valid

    def test_star_select_passes(self, validator):
        sql = "SELECT * FROM users"
        result = validator.validate(sql)
        assert result.is_valid

    def test_no_schema_skips(self):
        validator = SchemaValidator(schema={})
        result = validator.validate("SELECT anything FROM anywhere")
        assert result.status == ValidationStatus.SKIPPED

    def test_multiple_errors(self, validator):
        sql = "SELECT fake_col1, fake_col2 FROM users"
        result = validator.validate(sql)
        assert not result.is_valid
        assert len(result.errors) >= 2
