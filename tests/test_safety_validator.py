"""Tests for Tier 4: Safety Validator."""

import pytest

from llm_sql_validator.validators.safety import SafetyValidator


@pytest.fixture
def validator():
    return SafetyValidator(read_only=True, dialect="postgres")


class TestSafetyValidator:
    """Test suite for safety validation."""

    def test_valid_select(self, validator):
        result = validator.validate("SELECT id FROM users WHERE id = 1")
        assert result.is_valid

    def test_block_drop_table(self, validator):
        result = validator.validate("DROP TABLE users")
        assert not result.is_valid
        assert any(e.code == "BLOCKED_DDL" for e in result.errors)

    def test_block_create_table(self, validator):
        result = validator.validate("CREATE TABLE test (id INT)")
        assert not result.is_valid
        assert any(e.code == "BLOCKED_DDL" for e in result.errors)

    def test_block_insert(self, validator):
        result = validator.validate("INSERT INTO users (first_name) VALUES ('test')")
        assert not result.is_valid
        assert any(e.code == "BLOCKED_DML" for e in result.errors)

    def test_block_update(self, validator):
        result = validator.validate("UPDATE users SET first_name = 'test' WHERE id = 1")
        assert not result.is_valid
        assert any(e.code == "BLOCKED_DML" for e in result.errors)

    def test_block_delete(self, validator):
        result = validator.validate("DELETE FROM users WHERE id = 1")
        assert not result.is_valid
        assert any(e.code == "BLOCKED_DML" for e in result.errors)

    def test_block_truncate(self, validator):
        result = validator.validate("TRUNCATE TABLE users")
        assert not result.is_valid

    def test_allow_dml_when_not_readonly(self):
        validator = SafetyValidator(read_only=False, dialect="postgres")
        result = validator.validate("INSERT INTO users (first_name) VALUES ('test')")
        # DML allowed, DDL still blocked
        assert not any(e.code == "BLOCKED_DML" for e in result.errors)

    def test_allow_ddl_when_configured(self):
        validator = SafetyValidator(read_only=True, allow_ddl=True, dialect="postgres")
        result = validator.validate("CREATE TABLE test (id INT)")
        assert not any(e.code == "BLOCKED_DDL" for e in result.errors)

    def test_detect_cross_join(self, validator):
        sql = "SELECT * FROM users CROSS JOIN orders"
        result = validator.validate(sql)
        assert not result.is_valid
        assert any(e.code == "CARTESIAN_JOIN" for e in result.errors)

    def test_detect_injection_pattern_comment(self, validator):
        sql = "SELECT * FROM users WHERE name = ''; -- DROP TABLE users"
        result = validator.validate(sql)
        assert not result.is_valid
        assert any(e.code == "INJECTION_PATTERN" for e in result.errors)

    def test_detect_injection_pattern_union(self, validator):
        sql = "SELECT id FROM users UNION SELECT password FROM admin_users"
        result = validator.validate(sql)
        assert not result.is_valid
        assert any(e.code == "INJECTION_PATTERN" for e in result.errors)

    def test_excessive_joins_warning(self):
        validator = SafetyValidator(max_join_tables=3, dialect="postgres")
        sql = """
        SELECT a.id FROM t1 a
        JOIN t2 b ON a.id = b.id
        JOIN t3 c ON b.id = c.id
        JOIN t4 d ON c.id = d.id
        JOIN t5 e ON d.id = e.id
        """
        result = validator.validate(sql)
        # Should have a warning about excessive joins
        assert any(w.code == "EXCESSIVE_JOINS" for w in result.warnings)

    def test_normal_join_passes(self, validator):
        sql = """
        SELECT u.first_name, o.amount
        FROM users u
        INNER JOIN orders o ON u.id = o.user_id
        """
        result = validator.validate(sql)
        assert result.is_valid
