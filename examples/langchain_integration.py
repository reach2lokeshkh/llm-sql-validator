"""Example: Integrating llm-sql-validator with LangChain SQL agents.

This shows how to use the validator as a guardrail in a LangChain pipeline,
blocking unsafe or incorrect queries before they reach the database.
"""

from llm_sql_validator import ValidationPipeline, ValidatorConfig


def create_validated_chain():
    """Create a LangChain chain with SQL validation.

    NOTE: This example requires langchain and an LLM provider to be installed.
    It demonstrates the integration pattern.
    """
    # Load validator config
    config = ValidatorConfig.from_yaml("examples/schema.yaml")
    pipeline = ValidationPipeline(config)

    def validate_sql(llm_output: str) -> str:
        """Validation step that sits between the LLM and database execution."""
        result = pipeline.validate(llm_output)

        if not result.is_valid:
            error_messages = "; ".join(e.message for e in result.errors)
            raise ValueError(
                f"LLM-generated SQL failed validation at tier "
                f"{result.failed_tier.value}: {error_messages}"
            )

        # Log warnings but don't block
        for warning in result.warnings:
            print(f"[WARN] {warning.message}")

        return llm_output

    # In a real LangChain setup:
    # chain = llm | validate_sql | db.run
    #
    # The validate_sql function raises ValueError if the query is unsafe,
    # which the chain can catch and retry with the error message as context.

    return validate_sql


def retry_with_validation_feedback():
    """Pattern for retrying with validation errors fed back to the LLM.

    When validation fails, the error message is sent back to the LLM
    as context so it can generate a corrected query.
    """
    config = ValidatorConfig.from_yaml("examples/schema.yaml")
    pipeline = ValidationPipeline(config)

    def validate_and_retry(sql: str, max_retries: int = 3) -> dict:
        """Validate SQL, returning errors that can be fed back to an LLM."""
        result = pipeline.validate(sql)

        if result.is_valid:
            return {
                "valid": True,
                "sql": sql,
                "warnings": [w.message for w in result.warnings],
            }

        return {
            "valid": False,
            "sql": sql,
            "errors": [
                {
                    "tier": e.tier.value,
                    "message": e.message,
                    "suggestion": e.suggestion,
                }
                for e in result.errors
            ],
            "retry_prompt": (
                f"The SQL query you generated failed validation. "
                f"Please fix the following issues and regenerate:\n"
                + "\n".join(
                    f"- {e.message}" + (f" Suggestion: {e.suggestion}" if e.suggestion else "")
                    for e in result.errors
                )
            ),
        }

    # Example usage:
    bad_sql = "SELECT customer_name, email FROM users"
    result = validate_and_retry(bad_sql)

    if not result["valid"]:
        print("Validation failed. Feed this back to LLM:")
        print(result["retry_prompt"])


if __name__ == "__main__":
    print("=== Validation Function Demo ===\n")
    validate_fn = create_validated_chain()

    # This should pass
    try:
        result = validate_fn("SELECT first_name FROM users WHERE is_deleted = false")
        print(f"PASSED: {result}")
    except ValueError as e:
        print(f"BLOCKED: {e}")

    # This should fail
    try:
        result = validate_fn("DROP TABLE users")
        print(f"PASSED: {result}")
    except ValueError as e:
        print(f"BLOCKED: {e}")

    print("\n=== Retry Pattern Demo ===\n")
    retry_with_validation_feedback()
