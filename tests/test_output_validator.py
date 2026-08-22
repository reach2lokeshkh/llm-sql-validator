"""Tests for Tier 5: Output Validator (Anti-Example Detection)."""

import pytest

from llm_sql_validator.result import ValidationStatus
from llm_sql_validator.validators.output import AntiExample, OutputValidator


@pytest.fixture
def validator():
    anti_examples = [
        AntiExample(
            sql="SELECT COUNT(*) FROM orders",
            reason="Missing date filter — returned lifetime count instead of daily",
        ),
        AntiExample(
            sql="SELECT SUM(amount) FROM orders GROUP BY user_id",
            reason="Missing date filter — summed all-time instead of period",
        ),
    ]
    return OutputValidator(anti_examples=anti_examples, similarity_threshold=0.75)


class TestOutputValidator:
    """Test suite for output validation and anti-example detection."""

    def test_no_match_passes(self, validator):
        sql = "SELECT first_name FROM users WHERE id = 1"
        result = validator.validate(sql)
        assert result.is_valid
        assert result.status == ValidationStatus.PASSED

    def test_exact_anti_example_match(self, validator):
        sql = "SELECT COUNT(*) FROM orders"
        result = validator.validate(sql)
        assert result.status == ValidationStatus.WARNING
        assert any(w.code == "ANTI_EXAMPLE_MATCH" for w in result.warnings)

    def test_similar_anti_example_match(self, validator):
        # Very similar to the recorded anti-example
        sql = "select count(*) from orders"
        result = validator.validate(sql)
        assert result.status == ValidationStatus.WARNING
        assert any(w.code == "ANTI_EXAMPLE_MATCH" for w in result.warnings)

    def test_different_query_no_match(self, validator):
        sql = "SELECT first_name, last_name FROM users WHERE created_at > '2024-01-01'"
        result = validator.validate(sql)
        assert result.is_valid

    def test_record_new_anti_example(self, validator):
        # Record a new anti-example
        validator.record_anti_example(
            sql="SELECT AVG(amount) FROM orders",
            reason="Returns overall average, not segmented",
        )
        assert len(validator.anti_examples) == 3

        # Now it should match
        sql = "SELECT AVG(amount) FROM orders"
        result = validator.validate(sql)
        assert result.status == ValidationStatus.WARNING

    def test_anti_example_includes_reason(self, validator):
        sql = "SELECT COUNT(*) FROM orders"
        result = validator.validate(sql)
        warning = next(w for w in result.warnings if w.code == "ANTI_EXAMPLE_MATCH")
        assert "Missing date filter" in warning.message

    def test_threshold_respected(self):
        # High threshold means only near-exact matches trigger
        validator = OutputValidator(
            anti_examples=[
                AntiExample(sql="SELECT COUNT(*) FROM orders", reason="test")
            ],
            similarity_threshold=0.99,
        )
        # Slightly different query should NOT match at 0.99 threshold
        sql = "SELECT COUNT(DISTINCT user_id) FROM orders WHERE order_date > '2024-01-01'"
        result = validator.validate(sql)
        assert result.is_valid

    def test_no_anti_examples_passes(self):
        validator = OutputValidator(anti_examples=[])
        sql = "SELECT COUNT(*) FROM orders"
        result = validator.validate(sql)
        assert result.is_valid

    def test_from_dict_config(self):
        validator = OutputValidator(
            anti_examples=[
                {"sql": "SELECT * FROM users", "reason": "Too broad"},
            ]
        )
        result = validator.validate("SELECT * FROM users")
        assert result.status == ValidationStatus.WARNING
