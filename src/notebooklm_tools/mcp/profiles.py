"""Named MCP tool-visibility profiles: minimal / standard / full.

Python port of the *shape* of PleasePrompto/notebooklm-mcp's
src/utils/settings-manager.ts profile system (MIT licensed, see CREDITS.md):
the same three profile names, selected the same way (one env var, resolved
once at server start), for the same reason -- a host agent only sees the
tools it needs, which saves context.

This does not reimplement tool filtering. It sits on top of this codebase's
existing group-based gating (mcp/tool_groups.py): a profile is defined as
the set of tool GROUPS it exposes, and applying a profile disables every
group *not* in that set via the same FastMCP visibility transform
(mcp.local_provider.disable) that tool_groups.apply() already uses. The two
compose: whichever one hides a given tool, it stays hidden.

Because gating in this codebase is per-group rather than per-tool, group
membership doesn't split as finely as the original's individual tool lists
(e.g. our "chat" group bundles notebook_query with chat_configure and the
async query_start/query_status pair -- there is no narrower "answer
questions only" group). Profiles here approximate the original's intent at
the group granularity this codebase exposes.

Selection: CAST_NLM_PROFILE=minimal|standard|full (env var only -- this
codebase has no settings.json to layer under it). Unset or full: no-op,
i.e. every tool stays visible unless NOTEBOOKLM_DISABLED_GROUPS/
NOTEBOOKLM_DISABLED_TOOLS says otherwise (unchanged default behavior).
Invalid values are ignored with a warning (treated as unset).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PROFILE_ENV_VAR = "CAST_NLM_PROFILE"

# Each profile lists the tool_groups.TOOL_GROUPS keys it exposes.
# "full" is represented as None: no group is hidden.
PROFILES: dict[str, set[str] | None] = {
    # Read-only notebook browsing + the core chat/query surface + health.
    "minimal": {"notebooks_read", "chat", "server"},
    # Everything a day-to-day user needs: minimal + content/source
    # management, notebook lifecycle, auth maintenance, and organization
    # (labels/tags) -- but not batch/pipeline automation or sharing.
    "standard": {
        "notebooks_read",
        "notebooks_manage",
        "sources_read",
        "sources_manage",
        "chat",
        "auth",
        "organization",
        "server",
    },
    "full": None,
}


def _resolve_profile_name() -> str | None:
    """Read CAST_NLM_PROFILE; return None if unset, invalid, or 'full'."""
    raw = os.environ.get(PROFILE_ENV_VAR, "").strip().lower()
    if not raw:
        return None
    if raw not in PROFILES:
        logger.warning(
            f"Ignoring invalid {PROFILE_ENV_VAR}={raw!r}; "
            f"expected one of: {', '.join(PROFILES)}"
        )
        return None
    return raw


def apply(mcp: Any) -> str | None:
    """Hide tools outside the active profile's groups, if one is configured.

    Returns the resolved profile name ("minimal", "standard", "full"), or
    None if CAST_NLM_PROFILE is unset/invalid (equivalent to "full": no
    tools hidden by this function).
    """
    from . import tool_groups

    name = _resolve_profile_name()
    if name is None or PROFILES[name] is None:
        return name

    allowed_groups = PROFILES[name]
    disabled_group_names = set(tool_groups.TOOL_GROUPS) - allowed_groups

    disabled_tool_names: set[str] = set()
    for group in disabled_group_names:
        disabled_tool_names |= tool_groups.TOOL_GROUPS[group]

    if disabled_tool_names:
        mcp.local_provider.disable(names=disabled_tool_names)

    return name
