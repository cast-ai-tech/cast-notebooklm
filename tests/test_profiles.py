"""Tests for named MCP tool-visibility profiles (minimal/standard/full)."""

from unittest.mock import MagicMock

from notebooklm_tools.mcp import profiles, tool_groups


def _clear_env(monkeypatch):
    monkeypatch.delenv(profiles.PROFILE_ENV_VAR, raising=False)


def test_unset_profile_resolves_to_none(monkeypatch):
    _clear_env(monkeypatch)
    assert profiles._resolve_profile_name() is None


def test_full_profile_resolves_and_hides_nothing(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(profiles.PROFILE_ENV_VAR, "full")

    assert profiles._resolve_profile_name() == "full"

    mcp = MagicMock()
    name = profiles.apply(mcp)

    assert name == "full"
    mcp.local_provider.disable.assert_not_called()


def test_invalid_profile_is_ignored(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(profiles.PROFILE_ENV_VAR, "nonexistent")

    assert profiles._resolve_profile_name() is None

    mcp = MagicMock()
    name = profiles.apply(mcp)

    assert name is None
    mcp.local_provider.disable.assert_not_called()


def test_profile_selection_is_case_insensitive(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(profiles.PROFILE_ENV_VAR, "MINIMAL")
    assert profiles._resolve_profile_name() == "minimal"


def test_minimal_profile_hides_everything_outside_its_groups(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(profiles.PROFILE_ENV_VAR, "minimal")
    mcp = MagicMock()

    name = profiles.apply(mcp)

    assert name == "minimal"
    expected_disabled_groups = set(tool_groups.TOOL_GROUPS) - profiles.PROFILES["minimal"]
    expected_tools: set[str] = set()
    for group in expected_disabled_groups:
        expected_tools |= tool_groups.TOOL_GROUPS[group]

    mcp.local_provider.disable.assert_called_once_with(names=expected_tools)
    # Core chat/query tools must survive minimal.
    assert "notebook_query" not in expected_tools
    assert "notebook_list" not in expected_tools
    # Destructive/management tools must not survive minimal.
    assert "notebook_delete" in expected_tools
    assert "studio_create" in expected_tools


def test_standard_profile_is_a_strict_superset_of_minimal():
    minimal_groups = profiles.PROFILES["minimal"]
    standard_groups = profiles.PROFILES["standard"]
    assert minimal_groups < standard_groups


def test_every_profile_group_name_exists_in_tool_groups():
    for name, groups in profiles.PROFILES.items():
        if groups is None:
            continue
        unknown = groups - set(tool_groups.TOOL_GROUPS)
        assert not unknown, f"profile {name!r} references unknown group(s): {unknown}"
