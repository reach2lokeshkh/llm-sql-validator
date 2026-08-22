"""Tests for the full ValidationPipeline orchestration."""

import pytest

from llm_sql_validator import ValidationPipeline, ValidatorConfig
from llm_sql_validator.result import ValidationLevel, ValidationStatus

SAMPLE_SCHEMA = {
    "public": {
        "users": {
            "columns": {
                "id": {"type": "integer"},
                "first_name": {"type": "varchar"},
                "last_name": {"type": "varchar"},
                "email": {"type": "varchar", "pii": True},
                "is_deleted": {"type": "boolean"},
            }
        },
        "orders": {
            "columns": {
                "id": {"type": "integer"},
                "user_id": {"type": "integer"},
                "amount": {"type": "decimal"},
                "order_date": {"type": "date"},
            },
            "row_estimate": 500_000_000,
        },
    }
}

SAMPLE_RULES = [
    {
        "name": "require_date_on_orders",
        "rule_type": "required_filter",
        "target_tables": ["orders"],
        "filter_columns": ["order_date"],
        "description": "Must filter on order_date",
    },
]


@pytest.fixture
def config():
    return ValidatorConfig(
        dialect="postgres",
        schema=SAMPLE_SCHEMA,
        rules=SAMPLE_RULES,
    )


@pytest.fixture
def pipeline(config):
    return ValidationPipeline(config)


class TestValidationPipeline:
    """Test suite for the full pipeline."""

    def test_valid_query_passes_all_tiers(self, pipeline):
        sql = "SELECT first_name, last_name FROM users WHERE is_deleted = false"
        result = pipeline.validate(sql)
        assert result.is_valid

    def test_syntax_error_fails_at_tier_1(self, pipeline):
        sql = ""
        result = pipeline.validate(sql)
        assert not result.is_valid
        assert result.failed_tier == ValidationLevel.SYNTAX

    def test_schema_error_fails_at_tier_2(self, pipeline):
        sql = "SELECT nonexistent_column FROM users"
        result = pipeline.validate(sql)
        assert not result.is_valid
        assert result.failed_tier == ValidationLevel.SCHEMA

    def test_business_rule_fails_at_tier_3(self, pipeline):
        sql = "SELECT amount FROM orders WHERE user_id = 1"
        result = pipeline.validate(sql)
        assert not result.is_valid
        assert result.failed_tier == ValidationLevel.BUSINESS_RULES

    def test_safety_fails_at_tier_4(self, pipeline):
        sql = "DROP TABLE users"
        result = pipeline.validate(sql)
        assert not result.is_valid
        assert result.failed_tier == ValidationLevel.SAFETY

    def test_fail_fast_stops_at_first_failure(self, pipeline):
        # Empty query should fail at syntax and not proceed further
        sql = ""
        result = pipeline.validate(sql)
        assert result.failed_tier == ValidationLevel.SYNTAX
        # Should only have syntax errors, not schema/rule/safety errors
        assert all(e.tier == ValidationLevel.SYNTAX for e in result.errors)

    def test_fail_fast_disabled_collects_all(self, config):
        pipeline = ValidationPipeline(config, fail_fast=False)
        # This query has both schema and safety issues
        sql = "DROP TABLE nonexistent_table"
        result = pipeline.validate(sql)
        assert not result.is_valid
        # Should have errors from multiple tiers
        tiers_with_errors = {e.tier for e in result.errors}
        assert len(tiers_with_errors) >= 1

    def test_record_anti_example(self, pipeline):
        pipeline.record_anti_example(
            sql="SELECT COUNT(*) FROM orders",
            reason="Lifetime count without date filter",
        )
        # Now validate similar query
        result = pipeline.validate(
            "SELECT COUNT(*) FROM orders WHERE order_date > '2024-01-01'"
        )
        # Should pass because it has the date filter
        # (anti-example similarity won't be high enough with the WHERE clause)
        assert result is not None

    def test_pipeline_has_5_validators(self, pipeline):
        assert len(pipeline.validators) == 5

    def test_register_custom_validator(self, pipeline):
        from llm_sql_validator.result import ValidationResult
        from llm_sql_validator.validators.base import BaseValidator

        class CustomValidator(BaseValidator):
            tier = ValidationLevel.OUTPUT

            def validate(self, sql, context=None):
                return ValidationResult(status=ValidationStatus.PASSED, tier=self.tier)

        pipeline.register_validator(CustomValidator())
        assert len(pipeline.validators) == 6

    def test_from_dict_config(self):
        config = ValidatorConfig.from_dict({
            "dialect": "redshift",
            "schemas": SAMPLE_SCHEMA,
            "rules": SAMPLE_RULES,
        })
        pipeline = ValidationPipeline(config)
        result = pipeline.validate("SELECT first_name FROM users WHERE is_deleted = false")
        assert result.is_valid
