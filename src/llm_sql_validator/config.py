"""Configuration loading and management for the validation pipeline."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

warnings.filterwarnings("ignore", message='Field name "schema".*', category=UserWarning)


class ValidatorConfig(BaseModel):
    """Configuration for the validation pipeline.

    Can be loaded from YAML files or constructed programmatically.
    """

    model_config = ConfigDict(protected_namespaces=(), ignored_types=())

    dialect: str = "postgres"
    schema: dict = Field(default_factory=dict)
    rules: list[dict] = Field(default_factory=list)
    safety: dict = Field(default_factory=lambda: {
        "read_only": True,
        "allow_ddl": False,
        "max_join_tables": 6,
        "block_cartesian": True,
    })
    output: dict = Field(default_factory=lambda: {
        "anti_examples": [],
        "similarity_threshold": 0.75,
    })

    @classmethod
    def from_yaml(cls, path: str | Path) -> ValidatorConfig:
        """Load configuration from a YAML file.

        The YAML file can contain schema definitions, business rules,
        and safety settings all in one file, or reference separate files.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            ValidatorConfig instance.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data, base_path=path.parent)

    @classmethod
    def from_dict(cls, data: dict) -> ValidatorConfig:
        """Create config from a dictionary."""
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict, base_path: Optional[Path] = None) -> ValidatorConfig:
        """Internal config builder with file resolution support."""
        config_data: dict[str, Any] = {}

        # Dialect
        config_data["dialect"] = data.get("dialect", "postgres")

        # Schema — inline or from file
        if "schemas" in data:
            config_data["schema"] = data["schemas"]
        elif "schema_file" in data and base_path:
            schema_path = base_path / data["schema_file"]
            with open(schema_path) as f:
                config_data["schema"] = yaml.safe_load(f) or {}

        # Rules — inline or from file
        if "rules" in data:
            config_data["rules"] = data["rules"]
        elif "rules_file" in data and base_path:
            rules_path = base_path / data["rules_file"]
            with open(rules_path) as f:
                rules_data = yaml.safe_load(f) or {}
                config_data["rules"] = rules_data.get("rules", [])

        # Safety settings
        if "safety" in data:
            config_data["safety"] = data["safety"]

        # Output settings
        if "output" in data:
            config_data["output"] = data["output"]

        return cls(**config_data)
