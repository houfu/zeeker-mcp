"""
Wave-0 stub for ANNO-04; implemented in plan 05.

Tests:
- All six input models (Pydantic) in tools/*_models.py use
  model_config = ConfigDict(extra='forbid').
"""

import pytest


def test_all_input_models_extra_forbid():
    """ANNO-04: All input models use model_config = ConfigDict(extra='forbid')."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
    # Will iterate: discovery_models, retrieval_models, search_models
    # Will check: model.model_config.get("extra") == "forbid"


def test_schemas_flat():
    """ANNO-04: Input model schemas are flat (no nesting under args)."""
    pytest.skip("Wave 0 stub — implemented in plan 05")
