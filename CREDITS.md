# Credits

kast-notebooklm is a personal, internal unification of ideas and code from
three separate MIT-licensed open-source projects that give programmatic
access to Google NotebookLM. It is **not** a publishable fork of any single
one of them — it's a new project, under new copyright, that vendors code
from one of the three and independently reimplements design ideas learned
from the other two. Full attribution to all three follows, as required by
the MIT License.

## 1. Base: jacob-bd/notebooklm-mcp-cli

- **Repository:** https://github.com/jacob-bd/notebooklm-mcp-cli
- **Author:** Jacob Ben-David
- **License:** MIT, Copyright (c) 2025 Jacob Ben-David (full text: `LICENSE-jacob-bd`)

`src/notebooklm_tools/` in this repository is a copy of this project's
source tree (CLI, MCP server, and the `core`/`services` layers underneath
both), used as the foundation kast-notebooklm builds on. It is the only one
of the three source projects whose code is vendored here directly rather
than reimplemented; its `LICENSE` is preserved unmodified as
`LICENSE-jacob-bd` per the MIT License's attribution requirement.

What jacob-bd/notebooklm-mcp-cli contributes: a Python client that talks to
NotebookLM's internal `batchexecute` API directly over HTTP (via `httpx`),
authenticating via cookies extracted through Chrome DevTools Protocol
(no browser-click automation); a `nlm` CLI (Typer); an MCP server
(FastMCP); and full Studio support (audio, video, infographic, presentation,
data table, report, flashcards, quiz, mind map), research, batch, and
cross-notebook operations.

## 2. REST API, encryption, and multi-account design: roomi-fields/notebooklm-mcp

- **Repository:** https://github.com/roomi-fields/notebooklm-mcp
- **Author:** Romain Peyrichou (@roomi-fields)
- **License:** MIT, Copyright (c) 2025 Romain Peyrichou (HTTP REST API wrapper);
  Copyright (c) 2025 Please Prompto! (original NotebookLM MCP server this project forked)

This is a TypeScript fork of PleasePrompto/notebooklm-mcp (see below). Its
own code is **not** vendored here — kast-notebooklm's `rest_api/` package
and the encryption/multi-account additions to `src/notebooklm_tools/core/`
are an independent Python reimplementation, informed by studying this
project's design:

- **REST API shape** (`rest_api/routers/`, `rest_api/main.py`): a thin
  HTTP transport layer over the same service functions the CLI/MCP already
  call, following the endpoint and response-envelope conventions of this
  project's Express wrapper (`{"success": bool, "data"/"error": ...}`).
- **Credential encryption at rest** (`src/notebooklm_tools/core/crypto.py`):
  same AES-256-GCM approach and key-resolution hierarchy (env var → key
  file → generated-and-persisted key) as this project's
  `src/accounts/crypto.ts`. The nonce length differs (12 bytes here vs. 16
  there) — see `core/crypto.py`'s module docstring for why.
- **Multi-account client pooling** (`rest_api/client_pool.py`): informed by
  this project's per-account credential/session isolation model, adapted to
  jacob-bd's existing `AuthManager` profile system rather than building a
  parallel account store.

kast-notebooklm also improves on this project in one respect noted during
review: its Express HTTP wrapper has no authentication at all (binds
`0.0.0.0` with open CORS). `rest_api/deps.py` adds a required API-key check
that project does not have.

## 3. Provenance marker and tool profiles: PleasePrompto/notebooklm-mcp

- **Repository:** https://github.com/PleasePrompto/notebooklm-mcp
- **Author:** Gérôme Dexheimer ("Please Prompto!")
- **License:** MIT, Copyright (c) 2025 Please Prompto!

The original NotebookLM MCP server (roomi-fields, above, is a fork of it).
Its own code is **not** vendored here — the following are independent
Python reimplementations of ideas from this project:

- **AI-generated / untrusted-content provenance marker**
  (`src/notebooklm_tools/services/provenance.py`): the same two-part
  design as this project's `src/utils/disclaimer.ts` — a `_provenance`
  metadata field attached alongside `answer` (not wrapping it), plus an
  inline `[AI-GENERATED ...]` text prefix on the answer itself, so the
  marker survives even if a caller only reads the raw answer string. Applied
  in `services/chat.py::query()`, the single point all three transports
  (CLI, MCP, REST) share.
- **Named MCP tool-visibility profiles** (`src/notebooklm_tools/mcp/profiles.py`):
  the same `minimal`/`standard`/`full` profile names and env-var selection
  as this project's `src/utils/settings-manager.ts`, built on top of
  jacob-bd's existing group-based tool gating (`mcp/tool_groups.py`) rather
  than reimplementing per-tool filtering from scratch.

## License compliance note

Per the MIT License, each of the three projects' copyright and permission
notices must be preserved. jacob-bd's is preserved via `LICENSE-jacob-bd`
(its code is vendored verbatim under `src/notebooklm_tools/`). roomi-fields'
and PleasePrompto's code is not copied here — only design ideas,
independently reimplemented in Python — but both are credited above in
full as a matter of good practice, beyond what MIT strictly requires for
non-copied work.
