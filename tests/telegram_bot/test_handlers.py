"""Tests for telegram_bot/handlers.py -- command routing, no live bot/network.

Chat state (telegram_bot/state.py) persists under NOTEBOOKLM_MCP_CLI_PATH,
which tests/conftest.py's autouse `_isolate_storage` fixture already points
at a fresh per-test tmp_path -- so state here is isolated for free.
"""

from unittest.mock import MagicMock

from notebooklm_tools.core.exceptions import AuthenticationError, ProfileNotFoundError
from notebooklm_tools.services.errors import ServiceError, ValidationError
from telegram_bot import handlers, state


def _msg(chat_id: int, user_id: int, text: str) -> dict:
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": text},
    }


class TestBasics:
    def test_start_returns_welcome(self):
        replies = handlers.handle_update(_msg(1, 1, "/start"))
        assert replies == [(1, [handlers.WELCOME_TEXT])]

    def test_message_without_text_is_ignored(self):
        update = {"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": 1}, "sticker": {}}}
        assert handlers.handle_update(update) == []

    def test_non_message_update_is_ignored(self):
        assert handlers.handle_update({"update_id": 1, "edited_message": {}}) == []

    def test_unknown_command_gets_a_hint(self):
        replies = handlers.handle_update(_msg(1, 1, "/frobnicate"))
        assert replies == [(1, [handlers.UNKNOWN_COMMAND_TEXT])]


class TestAllowlist:
    def test_disallowed_user_is_rejected(self):
        replies = handlers.handle_update(_msg(1, 999, "/start"), allowed_user_ids={1, 2})
        assert replies == [(1, ["No estás autorizado a usar este bot."])]

    def test_allowed_user_passes(self):
        replies = handlers.handle_update(_msg(1, 2, "/start"), allowed_user_ids={1, 2})
        assert replies == [(1, [handlers.WELCOME_TEXT])]

    def test_no_allowlist_configured_allows_everyone(self):
        replies = handlers.handle_update(_msg(1, 12345, "/start"), allowed_user_ids=None)
        assert replies == [(1, [handlers.WELCOME_TEXT])]


class TestNotebooks:
    def test_lists_notebooks_and_saves_index_map(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(handlers, "get_client", lambda profile: fake_client)
        monkeypatch.setattr(
            handlers.notebooks_service,
            "list_notebooks",
            lambda client: {
                "notebooks": [
                    {"id": "nb-1", "title": "Uno", "source_count": 3},
                    {"id": "nb-2", "title": "Dos", "source_count": 0},
                ]
            },
        )

        replies = handlers.handle_update(_msg(42, 1, "/notebooks"))

        assert replies[0][0] == 42
        text = replies[0][1][0]
        assert "Uno" in text and "Dos" in text
        assert state.get_last_list(42) == {"1": "nb-1", "2": "nb-2"}

    def test_empty_notebook_list(self, monkeypatch):
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())
        monkeypatch.setattr(
            handlers.notebooks_service, "list_notebooks", lambda client: {"notebooks": []}
        )

        replies = handlers.handle_update(_msg(1, 1, "/notebooks"))
        assert "No tenés notebooks" in replies[0][1][0]

    def test_missing_profile_surfaces_clean_error(self, monkeypatch):
        def raise_not_found(profile):
            raise ProfileNotFoundError(profile)

        monkeypatch.setattr(handlers, "get_client", raise_not_found)

        replies = handlers.handle_update(_msg(1, 1, "/notebooks"))
        assert "nlm login" in replies[0][1][0]

    def test_corrupted_profile_surfaces_clean_error(self, monkeypatch):
        def raise_auth_error(profile):
            raise AuthenticationError(message="boom")

        monkeypatch.setattr(handlers, "get_client", raise_auth_error)

        replies = handlers.handle_update(_msg(1, 1, "/notebooks"))
        assert "inválidas o corruptas" in replies[0][1][0]


class TestUsar:
    def test_usar_without_arg_shows_usage(self):
        replies = handlers.handle_update(_msg(1, 1, "/usar"))
        assert replies[0][1][0].startswith("Uso: /usar")

    def test_usar_resolves_number_from_last_list(self, monkeypatch):
        state.set_last_list(7, {"1": "nb-abc"})
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())
        monkeypatch.setattr(
            handlers.notebooks_service,
            "get_notebook",
            lambda client, nb_id: {"id": nb_id, "title": "Mi Notebook"},
        )

        replies = handlers.handle_update(_msg(7, 1, "/usar 1"))

        assert "Mi Notebook" in replies[0][1][0]
        assert state.get_active_notebook_id(7) == "nb-abc"

    def test_usar_falls_back_to_raw_id_when_not_in_map(self, monkeypatch):
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())
        seen = {}

        def fake_get_notebook(client, nb_id):
            seen["nb_id"] = nb_id
            return {"id": nb_id, "title": "Directo"}

        monkeypatch.setattr(handlers.notebooks_service, "get_notebook", fake_get_notebook)

        handlers.handle_update(_msg(8, 1, "/usar some-raw-uuid"))

        assert seen["nb_id"] == "some-raw-uuid"

    def test_usar_with_unknown_notebook_reports_error(self, monkeypatch):
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())

        def raise_not_found(client, nb_id):
            raise ServiceError("not found", user_message="No existe ese notebook.")

        monkeypatch.setattr(handlers.notebooks_service, "get_notebook", raise_not_found)

        replies = handlers.handle_update(_msg(9, 1, "/usar xyz"))
        assert "No encontré" in replies[0][1][0]


class TestStatus:
    def test_status_without_active_notebook(self):
        replies = handlers.handle_update(_msg(100, 1, "/status"))
        assert "No tenés ningún notebook activo" in replies[0][1][0]

    def test_status_with_active_notebook(self):
        state.set_active_notebook_id(101, "nb-active")
        state.set_profile(101, "trabajo")

        replies = handlers.handle_update(_msg(101, 1, "/status"))

        assert "nb-active" in replies[0][1][0]
        assert "trabajo" in replies[0][1][0]


class TestPerfil:
    def test_perfil_without_arg_shows_usage(self):
        replies = handlers.handle_update(_msg(1, 1, "/perfil"))
        assert replies[0][1][0].startswith("Uso: /perfil")

    def test_perfil_switches_to_known_profile(self, monkeypatch):
        monkeypatch.setattr(handlers.AuthManager, "list_profiles", staticmethod(lambda: ["default", "trabajo"]))

        replies = handlers.handle_update(_msg(20, 1, "/perfil trabajo"))

        assert "trabajo" in replies[0][1][0]
        assert state.get_profile(20) == "trabajo"

    def test_perfil_rejects_unknown_profile(self, monkeypatch):
        monkeypatch.setattr(handlers.AuthManager, "list_profiles", staticmethod(lambda: ["default"]))

        replies = handlers.handle_update(_msg(21, 1, "/perfil noexiste"))

        assert "No existe el perfil" in replies[0][1][0]
        assert state.get_profile(21) == "default"


class TestQuestion:
    def test_question_without_active_notebook_prompts(self):
        replies = handlers.handle_update(_msg(30, 1, "que dice el notebook?"))
        assert "Primero elegí" in replies[0][1][0]

    def test_question_queries_active_notebook(self, monkeypatch):
        state.set_active_notebook_id(31, "nb-31")
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())
        monkeypatch.setattr(
            handlers,
            "chat_query",
            lambda client, nb_id, text: {"answer": f"respuesta para {nb_id}: {text}"},
        )

        replies = handlers.handle_update(_msg(31, 1, "cual es el tema?"))

        assert replies[0][1][0] == "respuesta para nb-31: cual es el tema?"

    def test_question_validation_error_surfaces_user_message(self, monkeypatch):
        state.set_active_notebook_id(32, "nb-32")
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())

        def raise_validation(client, nb_id, text):
            raise ValidationError("empty", user_message="Escribí una pregunta.")

        monkeypatch.setattr(handlers, "chat_query", raise_validation)

        replies = handlers.handle_update(_msg(32, 1, ""))
        assert replies[0][1][0] == "Escribí una pregunta."

    def test_long_answer_is_chunked(self, monkeypatch):
        state.set_active_notebook_id(33, "nb-33")
        monkeypatch.setattr(handlers, "get_client", lambda profile: MagicMock())
        long_answer = "x" * 9000
        monkeypatch.setattr(handlers, "chat_query", lambda client, nb_id, text: {"answer": long_answer})

        replies = handlers.handle_update(_msg(33, 1, "pregunta larga"))

        chunks = replies[0][1]
        assert len(chunks) == 3
        assert all(len(c) <= handlers.TELEGRAM_MAX_MESSAGE_LENGTH for c in chunks)
        assert "".join(chunks) == long_answer
