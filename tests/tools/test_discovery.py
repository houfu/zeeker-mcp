"""
Wave-0 stub for DISC-01; implemented in plan 04.

Tests:
- list_databases returns 4 configured databases with description + table_count.
- HIDDEN_TABLES are subtracted from table_count for affected databases.
- Provenance has database=None, table=None, license="mixed".
"""

import pytest


def test_list_databases():
    """DISC-01: list_databases returns 4 configured DBs with correct shape."""
    pytest.skip("Wave 0 stub — implemented in plan 04")
    # Will use: from mcp_zeeker.tools.discovery import list_databases
    # Will stub 4 httpx_mock responses (one per ALLOWED_DATABASES)
    # Will assert: len(envelope.data) == 4


def test_list_databases_names_match_config():
    """DISC-01: Database names in response match ALLOWED_DATABASES."""
    pytest.skip("Wave 0 stub — implemented in plan 04")
    # Will use: from mcp_zeeker import config


def test_list_databases_hidden_tables_excluded():
    """DISC-01: table_count for sglawwatch excludes HIDDEN_TABLES['sglawwatch']."""
    pytest.skip("Wave 0 stub — implemented in plan 04")


def test_list_databases_provenance():
    """DISC-01: Provenance has database=None, table=None, license='mixed'."""
    pytest.skip("Wave 0 stub — implemented in plan 04")
