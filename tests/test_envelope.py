"""
Wave-0 stub for ENV-06; implemented in plan 02.

Tests:
- Envelope, Provenance, Pagination Pydantic models exist with extra='forbid'.
- Envelope.for_database_list returns correct provenance shape.
- retrieved_at is timezone-aware UTC.
"""

import pytest


def test_envelope_extra_forbid():
    """ENV-06: Envelope rejects unknown keys (extra='forbid')."""
    pytest.skip("Wave 0 stub — implemented in plan 02")
    # Will use: from mcp_zeeker.core.envelope import Envelope, Provenance, Pagination


def test_provenance_extra_forbid():
    """ENV-06: Provenance rejects unknown keys (extra='forbid')."""
    pytest.skip("Wave 0 stub — implemented in plan 02")


def test_pagination_extra_forbid():
    """ENV-06: Pagination rejects unknown keys (extra='forbid')."""
    pytest.skip("Wave 0 stub — implemented in plan 02")


def test_for_database_list_provenance_shape():
    """ENV-06: for_database_list produces database=None, table=None, license=LICENSE_MIXED."""
    pytest.skip("Wave 0 stub — implemented in plan 02")


def test_retrieved_at_is_utc():
    """ENV-06: retrieved_at is timezone-aware UTC datetime."""
    pytest.skip("Wave 0 stub — implemented in plan 02")
