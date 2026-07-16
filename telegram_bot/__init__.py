"""Telegram bot for cast-notebooklm.

Not part of any of the three upstream projects this repo is built on --
new capability. Talks to the same notebooklm_tools.services layer the
CLI, MCP server, and REST API already use. See bot.py for the entry point,
api.py for the thin Telegram Bot HTTP API wrapper, handlers.py for command
routing, and state.py for per-chat state (active notebook/profile).
"""
