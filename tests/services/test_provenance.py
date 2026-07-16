"""Tests for the AI-generated/untrusted-content provenance marker."""

import notebooklm_tools.services.provenance as provenance
from notebooklm_tools.services.provenance import (
    PROVENANCE,
    apply_ai_marker,
)


class TestProvenanceEnvelope:
    def test_provenance_marks_content_as_ai_generated(self):
        assert PROVENANCE["ai_generated"] is True

    def test_provenance_has_expected_fields(self):
        for field in ("provider", "model", "via", "grounding", "ai_generated"):
            assert field in PROVENANCE


class TestApplyAiMarker:
    def test_prefixes_answer_by_default(self, monkeypatch):
        monkeypatch.delenv(provenance.AI_MARKER_ENV_VAR, raising=False)
        monkeypatch.delenv(provenance.AI_MARKER_PREFIX_ENV_VAR, raising=False)

        result = apply_ai_marker("The answer is 42.")

        assert result.startswith("[AI-GENERATED")
        assert result.endswith("The answer is 42.")
        assert "\n\n" in result

    def test_marker_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv(provenance.AI_MARKER_ENV_VAR, "false")

        result = apply_ai_marker("The answer is 42.")

        assert result == "The answer is 42."

    def test_marker_disabled_case_insensitive(self, monkeypatch):
        monkeypatch.setenv(provenance.AI_MARKER_ENV_VAR, "0")
        assert apply_ai_marker("x") == "x"

        monkeypatch.setenv(provenance.AI_MARKER_ENV_VAR, "NO")
        assert apply_ai_marker("x") == "x"

    def test_custom_prefix_via_env(self, monkeypatch):
        monkeypatch.delenv(provenance.AI_MARKER_ENV_VAR, raising=False)
        monkeypatch.setenv(provenance.AI_MARKER_PREFIX_ENV_VAR, "[CUSTOM MARKER]")

        result = apply_ai_marker("answer text")

        assert result == "[CUSTOM MARKER]\n\nanswer text"
