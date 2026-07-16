"""Command and message routing for the Telegram bot.

Given an incoming Telegram update dict, returns the reply text(s) to send
back -- kept separate from bot.py's polling loop and from api.py's HTTP
calls so it's testable without a live bot token or network access. Talks
to the same notebooklm_tools.services functions the CLI/MCP/REST API use,
and reuses rest_api.client_pool for multi-account client resolution.
"""

from __future__ import annotations

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.exceptions import AuthenticationError, ProfileNotFoundError
from notebooklm_tools.services import notebooks as notebooks_service
from notebooklm_tools.services.chat import query as chat_query
from notebooklm_tools.services.errors import ServiceError, ValidationError

from rest_api.client_pool import get_client

from . import state

TELEGRAM_MAX_MESSAGE_LENGTH = 4096

WELCOME_TEXT = (
    "\U0001F44B Hola! Soy tu bot de NotebookLM.\n\n"
    "Comandos:\n"
    "/notebooks - listar tus notebooks\n"
    "/usar <numero> - elegir con cual notebook hablar\n"
    "/status - ver cual notebook tenes activo\n"
    "/perfil <nombre> - cambiar de cuenta (perfil de nlm login)\n\n"
    "Una vez que elijas un notebook con /usar, simplemente escribime tu pregunta."
)

UNKNOWN_COMMAND_TEXT = "Comando no reconocido. Probá /start para ver la lista de comandos."


def _chunk_text(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]


def _resolve_client(profile: str):
    """Return (client, None) on success, or (None, error_text) on failure."""
    try:
        return get_client(profile), None
    except ProfileNotFoundError:
        return None, (
            f"No hay credenciales guardadas para el perfil '{profile}'. "
            f"Corré 'nlm login --profile {profile}' en la máquina donde corre este bot."
        )
    except AuthenticationError as e:
        return None, f"El perfil '{profile}' tiene credenciales inválidas o corruptas: {e}"


def _handle_notebooks(chat_id: int, profile: str) -> list[str]:
    client, error = _resolve_client(profile)
    if error:
        return [error]
    try:
        result = notebooks_service.list_notebooks(client)
    except ServiceError as e:
        return [f"No pude listar tus notebooks: {e.user_message}"]

    notebooks = result["notebooks"]
    if not notebooks:
        return ["No tenés notebooks todavía. Creá uno en notebooklm.google.com."]

    index_map = {}
    lines = ["Tus notebooks:"]
    for i, nb in enumerate(notebooks, start=1):
        index_map[str(i)] = nb["id"]
        lines.append(f"{i}. {nb['title']} ({nb['source_count']} fuentes)")
    lines.append("\nUsá /usar <numero> para elegir uno.")

    state.set_last_list(chat_id, index_map)
    return ["\n".join(lines)]


def _handle_usar(chat_id: int, profile: str, arg: str) -> list[str]:
    if not arg:
        return ["Uso: /usar <numero>  (primero corré /notebooks para ver la lista)"]

    index_map = state.get_last_list(chat_id)
    notebook_id = index_map.get(arg, arg)  # si no es un número conocido, se prueba como ID directo

    client, error = _resolve_client(profile)
    if error:
        return [error]

    try:
        nb = notebooks_service.get_notebook(client, notebook_id)
    except ServiceError as e:
        return [f"No encontré ese notebook: {e.user_message}"]

    state.set_active_notebook_id(chat_id, notebook_id)
    return [f"Listo, ahora estás hablando con: {nb['title']}"]


def _handle_status(chat_id: int) -> list[str]:
    notebook_id = state.get_active_notebook_id(chat_id)
    profile = state.get_profile(chat_id)
    if not notebook_id:
        return ["No tenés ningún notebook activo. Usá /notebooks y después /usar <numero>."]
    return [f"Notebook activo: {notebook_id} (perfil: {profile})"]


def _handle_perfil(chat_id: int, arg: str) -> list[str]:
    if not arg:
        return ["Uso: /perfil <nombre>  (el nombre de un perfil de 'nlm login --profile <nombre>')"]
    profiles = AuthManager.list_profiles()
    if arg not in profiles:
        disponibles = ", ".join(profiles) or "ninguno todavía"
        return [f"No existe el perfil '{arg}'. Perfiles disponibles: {disponibles}"]
    state.set_profile(chat_id, arg)
    return [f"Perfil cambiado a '{arg}'."]


def _handle_question(chat_id: int, text: str) -> list[str]:
    notebook_id = state.get_active_notebook_id(chat_id)
    if not notebook_id:
        return ["Primero elegí un notebook: /notebooks y después /usar <numero>."]

    profile = state.get_profile(chat_id)
    client, error = _resolve_client(profile)
    if error:
        return [error]

    try:
        result = chat_query(client, notebook_id, text)
    except ValidationError as e:
        return [e.user_message]
    except ServiceError as e:
        return [f"No pude responder: {e.user_message}"]

    return _chunk_text(result["answer"])


def handle_update(
    update: dict, *, allowed_user_ids: set[int] | None = None
) -> list[tuple[int, list[str]]]:
    """Process one Telegram update. Returns [(chat_id, [reply texts])], possibly empty.

    `allowed_user_ids`: if given, messages from any other Telegram user id
    get a rejection reply instead of being processed.
    """
    message = update.get("message")
    if not message or "text" not in message:
        return []

    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id")

    if allowed_user_ids is not None and user_id not in allowed_user_ids:
        return [(chat_id, ["No estás autorizado a usar este bot."])]

    text = message["text"].strip()
    profile = state.get_profile(chat_id)

    if text in ("/start", "/help"):
        return [(chat_id, [WELCOME_TEXT])]
    if text == "/notebooks":
        return [(chat_id, _handle_notebooks(chat_id, profile))]
    if text.startswith("/usar"):
        return [(chat_id, _handle_usar(chat_id, profile, text[len("/usar") :].strip()))]
    if text == "/status":
        return [(chat_id, _handle_status(chat_id))]
    if text.startswith("/perfil"):
        return [(chat_id, _handle_perfil(chat_id, text[len("/perfil") :].strip()))]
    if text.startswith("/"):
        return [(chat_id, [UNKNOWN_COMMAND_TEXT])]

    return [(chat_id, _handle_question(chat_id, text))]
