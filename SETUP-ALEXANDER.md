# SETUP-ALEXANDER.md

Personal setup notes for Alexander Cast. This project is written to be
installable by anyone (see README.md for the generic version) — this file
is the "how I actually run it" cheat sheet, including the secondary-account
rule.

## ⚠️ Account rule

**Authenticate with a secondary/test Google account, never your primary
one.** This project talks to NotebookLM's internal, undocumented API
directly (no official Google API), and Google can rotate or restrict that
API without notice. Keep it isolated from `founder@kreoon.com` or any
account tied to real KREOON/Infiny data.

## 1. Install

Requires Python 3.11+.

```bash
cd path/to/kast-notebooklm
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
```

Verify:

```bash
nlm --help
```

## 2. Authenticate (secondary account)

```bash
nlm login
```

This opens a Chrome window (Chrome DevTools Protocol) — log in with the
**secondary** Google account when prompted. Credentials are extracted as
cookies only (no password stored) and written **encrypted at rest**
(AES-256-GCM) to `~/.notebooklm-mcp-cli/` — see "Encryption key" below.

For a second account (multi-account), use a named profile:

```bash
nlm login --profile work
nlm login switch work    # make it the active profile for CLI/MCP
```

## 3. Encryption key

The first time any credentials are saved, a key is generated automatically
at `~/.notebooklm-mcp-cli/encryption.key` (permissions `0o600`) and a
warning is printed. **Back that file up** — losing it makes existing
encrypted credentials unrecoverable (you'd just re-run `nlm login`, no data
loss beyond re-authenticating).

To pin the key explicitly instead (e.g. to share across machines, or set
via a secrets manager), set it before first use:

```bash
export KAST_NLM_ENCRYPTION_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

## 4. Running each mode

### CLI

```bash
nlm notebook list
nlm chat query --notebook-id <id> --query "..."
```

### MCP server (for Claude Desktop, Cursor, etc.)

stdio (default, for desktop app configs):

```bash
notebooklm-mcp
```

HTTP (for network access):

```bash
notebooklm-mcp --transport http --port 8000
```

Optional: restrict which tools are visible to the host agent (saves
context) with a named profile:

```bash
KAST_NLM_PROFILE=minimal notebooklm-mcp     # read-only browsing + chat + health
KAST_NLM_PROFILE=standard notebooklm-mcp    # + content/notebook/source management, auth, labels
# unset, or KAST_NLM_PROFILE=full           # everything (default, unchanged behavior)
```

### REST API (for n8n / Zapier / Make)

Requires at least one API key configured — the server refuses to start
without one:

```bash
export KAST_NLM_API_KEYS=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
kast-notebooklm-api
```

Defaults to `127.0.0.1:8008` (override with `KAST_NLM_API_HOST` /
`KAST_NLM_API_PORT`). Every request needs the header `X-API-Key: <one of
the configured keys>`. Interactive docs at `http://127.0.0.1:8008/docs`.

Example call:

```bash
curl -X POST http://127.0.0.1:8008/chat/ask \
  -H "X-API-Key: $KAST_NLM_API_KEYS" \
  -H "Content-Type: application/json" \
  -d '{"notebook_id": "<id>", "question": "Summarize this notebook."}'
```

Multi-account: pass `"profile": "work"` in any request body (or
`?profile=work` on GET routes) to use a specific `nlm login --profile`
account instead of `default`.

Every `/chat/ask` response includes a `_provenance` field and the answer
text is prefixed with an `[AI-GENERATED ...]` marker — this is intentional
(anti prompt-injection labeling, see CREDITS.md §3). To disable just the
inline text prefix (the `_provenance` field always stays): set
`KAST_NLM_AI_MARKER=false`.

## 5. Known caveats

- `nlm doctor` and the legacy migration path (`utils/config.py::run_migration`)
  can still find *plaintext* credentials from an old install of the
  upstream `notebooklm-mcp-cli` tool (pre-dating this fork). If that
  happens, credential loading fails gracefully and logs a warning — just
  re-run `nlm login`.
- One pre-existing test (`tests/test_cdp_port_map.py::test_mapped_chrome_owns_profile_matches_user_data_dir_flag`)
  fails on this Windows machine independent of anything built here — it's
  unmodified from the jacob-bd base repo.
- The MCP `/health` endpoint reports `"version":"0.8.7"` (the jacob-bd
  base's version string) rather than kast-notebooklm's own version —
  cosmetic, not wired up, harmless.
