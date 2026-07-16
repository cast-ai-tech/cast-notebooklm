"""Telegram bot entry point.

Long-polls Telegram for messages and replies using the same
notebooklm_tools services the CLI/MCP server/REST API already use. Not
part of any of the three upstream projects this repo is built on -- new
capability.

Requires:
  CAST_NLM_TELEGRAM_BOT_TOKEN     -- token from @BotFather
  CAST_NLM_TELEGRAM_ALLOWED_USERS -- comma-separated Telegram numeric user
      IDs allowed to use the bot. Required: the bot refuses to start
      without it, same as the REST API refusing to start without an API
      key (see rest_api/main.py). Message @userinfobot on Telegram to find
      your own numeric user id.
"""

from __future__ import annotations

import logging
import os
import time

from .api import TelegramClient
from .handlers import handle_update

logger = logging.getLogger(__name__)

BOT_TOKEN_ENV_VAR = "CAST_NLM_TELEGRAM_BOT_TOKEN"
ALLOWED_USERS_ENV_VAR = "CAST_NLM_TELEGRAM_ALLOWED_USERS"
POLL_TIMEOUT_SECONDS = 30
ERROR_BACKOFF_SECONDS = 5


def _parse_allowed_users(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning(f"Ignoring invalid Telegram user id in {ALLOWED_USERS_ENV_VAR}: {part!r}")
    return ids


def poll_once(client: TelegramClient, offset: int | None, allowed_user_ids: set[int]) -> int | None:
    """Fetch and handle one batch of updates. Returns the next offset to use."""
    updates = client.get_updates(offset=offset, timeout=POLL_TIMEOUT_SECONDS)
    for update in updates:
        offset = update["update_id"] + 1
        for chat_id, texts in handle_update(update, allowed_user_ids=allowed_user_ids):
            for text in texts:
                try:
                    client.send_message(chat_id, text)
                except Exception as e:
                    logger.warning(f"Failed to send Telegram message to {chat_id}: {e}")
    return offset


def run() -> None:
    """Entry point for the `cast-notebooklm-telegram` console script."""
    token = os.environ.get(BOT_TOKEN_ENV_VAR)
    if not token:
        raise SystemExit(
            f"{BOT_TOKEN_ENV_VAR} is not set. Create a bot with @BotFather on Telegram, "
            f"then set {BOT_TOKEN_ENV_VAR} to the token it gives you."
        )

    allowed_user_ids = _parse_allowed_users(os.environ.get(ALLOWED_USERS_ENV_VAR, ""))
    if not allowed_user_ids:
        raise SystemExit(
            f"{ALLOWED_USERS_ENV_VAR} is not set. Refusing to start the bot without an "
            "allowlist of Telegram user IDs -- anyone who finds the bot could otherwise "
            "query your notebooks. Message @userinfobot on Telegram to find your numeric "
            f"user id, then set {ALLOWED_USERS_ENV_VAR} to a comma-separated list of allowed IDs."
        )

    client = TelegramClient(token)
    logger.info(f"Telegram bot started. Allowed users: {sorted(allowed_user_ids)}")

    offset = None
    while True:
        try:
            offset = poll_once(client, offset, allowed_user_ids)
        except Exception as e:
            logger.warning(f"Failed to poll Telegram for updates: {e}")
            time.sleep(ERROR_BACKOFF_SECONDS)


if __name__ == "__main__":
    run()
