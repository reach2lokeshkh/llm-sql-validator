# Contributing to llm-sql-validator

Thank you for your interest in contributing! This project aims to make LLM-generated SQL safer for everyone, and community contributions are essential to that mission.

## How to Contribute

### Reporting Bugs

- Open a [GitHub Issue](https://github.com/reach2lokeshkh/llm-sql-validator/issues)
- Include the SQL query that triggered the bug
- Include your configuration (schema/rules YAML)
- Include the actual vs. expected validation result
- Specify the SQL dialect and Python version

### Suggesting Features

- Open an issue with the `enhancement` label
- Describe the use case: what problem does it solve?
- Provide example SQL and expected behavior if possible

### Submitting Code

1. **Fork the repository** and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Install development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Write your code** following the style guidelines below.

4. **Add tests** for any new functionality. We aim for >90% coverage.

5. **Run the test suite:**
   ```bash
   pytest
   ```

6. **Run linting:**
   ```bash
   ruff check src/ tests/
   ```

7. **Run type checking:**
   ```bash
   mypy src/
   ```

8. **Submit a Pull Request** with a clear description of what changed and why.

---

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/llm-sql-validator.git
cd llm-sql-validator

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests to verify setup
pytest
```

---

## Areas Where Help is Most Needed

### New Business Rule Types
- `required_join` — enforce mandatory joins (e.g., always join with access control table)
- `column_combination` — certain columns cannot be selected together
- `aggregation_guard` — require approval for expensive aggregations
- `time_window` — enforce recency filters (e.g., only last 90 days)

### SQL Dialect Support
- Trino/Presto (currently beta)
- Azure Synapse
- Databricks SQL
- ClickHouse

### Integrations
- Vanna.ai integration example
- Dataherald integration example
- CrewAI / AutoGen agent integration
- FastAPI middleware for text-to-SQL APIs

### Documentation
- Tutorials for common setups
- Architecture deep-dive
- Video walkthrough

---

## Code Style Guidelines

- **Python 3.9+** compatible
- **Type hints** on all public functions and methods
- **Docstrings** on all public classes and functions (Google style)
- **Line length** max 100 characters
- Use `ruff` for formatting and linting
- Use `mypy` strict mode for type checking

### Naming Conventions

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`
- Test functions: `test_descriptive_name`

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add required_join rule type
fix: handle NULL column names in schema validator
docs: add Vanna.ai integration example
test: add edge case tests for cartesian join detection
```

---

## Writing a Custom Validator

Custom validators are the primary extension point. Here's the pattern:

```python
from llm_sql_validator.validators.base import BaseValidator
from llm_sql_validator.result import (
    ValidationError,
    ValidationLevel,
    ValidationResult,
    ValidationStatus,
)


class MyCustomValidator(BaseValidator):
    """One-line description of what this validates."""

    tier = ValidationLevel.SAFETY  # or whichever tier is appropriate

    def __init__(self, my_param: str = "default", **kwargs):
        super().__init__(**kwargs)
        self.my_param = my_param

    def validate(self, sql: str, context: dict | None = None) -> ValidationResult:
        # Your validation logic here
        if something_wrong:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                tier=self.tier,
                errors=[
                    ValidationError(
                        tier=self.tier,
                        code="MY_ERROR_CODE",
                        message="Clear description of what's wrong",
                        suggestion="How to fix it",
                    )
                ],
            )
        return ValidationResult(status=ValidationStatus.PASSED, tier=self.tier)
```

Register it:
```python
pipeline.register_validator(MyCustomValidator(my_param="value"))
```

---

## Writing a Business Rule

Business rules are YAML-configured and don't require code changes. But if you need a new rule *type*, add it to `BusinessRulesValidator._check_rule()`:

1. Add the new `rule_type` string to the dispatch logic
2. Implement `_check_your_rule_type(self, stmt, rule)` method
3. Add tests in `tests/test_business_rules_validator.py`
4. Document the new rule type in the README

---

## Testing Philosophy

- Every validator should have tests for: valid input passes, invalid input fails with correct error code, edge cases, and fuzzy matching behavior
- Use `pytest` fixtures for common setup
- Test error messages contain useful information (not just that they exist)
- Test the pipeline integration, not just individual validators

---

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to make data engineering safer.

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
