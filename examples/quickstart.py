"""Quick start example for llm-sql-validator.

This demonstrates the core usage pattern in just a few lines.
Run: python examples/quickstart.py
"""

from llm_sql_validator import ValidationPipeline, ValidatorConfig


def main():
    # Load configuration from YAML files
    config = ValidatorConfig.from_yaml("examples/schema.yaml")

    # Optionally load business rules from a separate file
    import yaml
    from pathlib import Path

    rules_path = Path("examples/rules.yaml")
    with open(rules_path) as f:
        rules_data = yaml.safe_load(f)
    config.rules = rules_data.get("rules", [])

    # Create the validation pipeline
    pipeline = ValidationPipeline(config)

    print("=" * 60)
    print("llm-sql-validator Quick Start Demo")
    print("=" * 60)

    # Example 1: Valid query
    print("\n--- Example 1: Valid query ---")
    sql = "SELECT first_name, last_name FROM users WHERE is_deleted = false"
    result = pipeline.validate(sql)
    print(f"SQL: {sql}")
    print(f"Valid: {result.is_valid}")
    print(f"Status: {result.status.value}")

    # Example 2: Non-existent column (schema violation)
    print("\n--- Example 2: Non-existent column ---")
    sql = "SELECT customer_name FROM users WHERE is_deleted = false"
    result = pipeline.validate(sql)
    print(f"SQL: {sql}")
    print(f"Valid: {result.is_valid}")
    if not result.is_valid:
        print(f"Failed tier: {result.failed_tier.value}")
        for error in result.errors:
            print(f"  Error: {error.message}")
            if error.suggestion:
                print(f"  Suggestion: {error.suggestion}")

    # Example 3: Missing required filter (business rule violation)
    print("\n--- Example 3: Missing date filter on orders ---")
    sql = "SELECT amount, status FROM orders WHERE user_id = 123"
    result = pipeline.validate(sql)
    print(f"SQL: {sql}")
    print(f"Valid: {result.is_valid}")
    if not result.is_valid:
        print(f"Failed tier: {result.failed_tier.value}")
        for error in result.errors:
            print(f"  Error: {error.message}")

    # Example 4: PII access without masking
    print("\n--- Example 4: PII column without masking ---")
    sql = "SELECT first_name, email, ssn FROM users WHERE is_deleted = false"
    result = pipeline.validate(sql)
    print(f"SQL: {sql}")
    print(f"Valid: {result.is_valid}")
    if not result.is_valid:
        print(f"Failed tier: {result.failed_tier.value}")
        for error in result.errors:
            print(f"  Error: {error.message}")
            if error.suggestion:
                print(f"  Suggestion: {error.suggestion}")

    # Example 5: Dangerous operation (safety violation)
    print("\n--- Example 5: DROP TABLE attempt ---")
    sql = "DROP TABLE users"
    result = pipeline.validate(sql)
    print(f"SQL: {sql}")
    print(f"Valid: {result.is_valid}")
    if not result.is_valid:
        print(f"Failed tier: {result.failed_tier.value}")
        for error in result.errors:
            print(f"  Error: {error.message}")

    # Example 6: Anti-example detection
    print("\n--- Example 6: Anti-example detection ---")
    pipeline.record_anti_example(
        sql="SELECT COUNT(*) FROM orders",
        reason="Missing date filter — returned lifetime count instead of daily",
    )
    sql = "SELECT COUNT(*) FROM orders"
    result = pipeline.validate(sql)
    print(f"SQL: {sql}")
    print(f"Valid: {result.is_valid}")
    if result.warnings:
        for warning in result.warnings:
            print(f"  Warning: {warning.message}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
