"""Tests for AI provider fallback chain."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ─────────────────────────── Error classification ───────────────────────────

class TestShouldFallback:
    def test_429_triggers_fallback(self):
        from openai import RateLimitError

        from app.ai.client import should_fallback

        # RateLimitError carries .status_code = 429
        e = RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429, request=MagicMock()),
            body=None,
        )
        assert should_fallback(e) is True

    def test_5xx_triggers_fallback(self):
        from openai import APIStatusError

        from app.ai.client import should_fallback

        e = APIStatusError(
            message="server err",
            response=MagicMock(status_code=503, request=MagicMock()),
            body=None,
        )
        assert should_fallback(e) is True

    def test_402_out_of_credits_triggers_fallback(self):
        from openai import APIStatusError

        from app.ai.client import should_fallback

        # 402 = hết credit OpenRouter → provider phụ (Gemini) có billing độc lập.
        e = APIStatusError(
            message="payment required",
            response=MagicMock(status_code=402, request=MagicMock()),
            body=None,
        )
        assert should_fallback(e) is True

    def test_4xx_auth_does_not_fallback(self):
        from openai import APIStatusError

        from app.ai.client import should_fallback

        # 401/403 = config issue, won't help to retry on another provider
        e = APIStatusError(
            message="unauthorized",
            response=MagicMock(status_code=401, request=MagicMock()),
            body=None,
        )
        assert should_fallback(e) is False

    def test_400_bad_request_does_not_fallback(self):
        from openai import APIStatusError

        from app.ai.client import should_fallback

        e = APIStatusError(
            message="bad",
            response=MagicMock(status_code=400, request=MagicMock()),
            body=None,
        )
        assert should_fallback(e) is False

    def test_404_model_not_found_does_fallback(self):
        from openai import APIStatusError

        from app.ai.client import should_fallback

        # Model not on this provider → try the other one
        e = APIStatusError(
            message="model not found",
            response=MagicMock(status_code=404, request=MagicMock()),
            body=None,
        )
        assert should_fallback(e) is True

    def test_connection_error_triggers_fallback(self):
        from openai import APIConnectionError

        from app.ai.client import should_fallback

        e = APIConnectionError(request=MagicMock())
        assert should_fallback(e) is True


# ─────────────────────────── Settings registry ───────────────────────────

class TestFallbackSettings:
    def test_fallback_keys_in_registry(self):
        from app.ai.config import SETTINGS_REGISTRY

        for key in (
            "fallback_enabled",
            "fallback_base_url",
            "fallback_api_key",
            "fallback_model_default",
            "fallback_model_fast",
            "fallback_model_deep",
        ):
            assert key in SETTINGS_REGISTRY, key

    def test_fallback_api_key_is_secret(self):
        from app.ai.config import SETTINGS_REGISTRY

        assert SETTINGS_REGISTRY["fallback_api_key"].is_secret is True

    def test_fallback_enabled_default_false(self):
        from app.ai.config import SETTINGS_REGISTRY

        assert SETTINGS_REGISTRY["fallback_enabled"].default is False


# ─────────────────────────── call_with_fallback ───────────────────────────

class TestCallWithFallback:
    def test_primary_success_no_fallback_invocation(self, monkeypatch):
        """When primary succeeds, fallback client must NOT be touched."""
        from app.ai.client import call_with_fallback

        primary = MagicMock()
        primary.chat.completions.create.return_value = "PRIMARY_OK"
        fallback = MagicMock()

        out = call_with_fallback(
            primary_client=primary,
            primary_model="m-primary",
            fallback_client=fallback,
            fallback_model="m-fallback",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            max_tokens=100,
        )
        assert out == "PRIMARY_OK"
        fallback.chat.completions.create.assert_not_called()

    def test_429_on_primary_falls_back(self, monkeypatch):
        from unittest.mock import MagicMock

        from openai import RateLimitError

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        primary.chat.completions.create.side_effect = RateLimitError(
            message="rate",
            response=MagicMock(status_code=429, request=MagicMock()),
            body=None,
        )
        fallback = MagicMock()
        fallback.chat.completions.create.return_value = "FALLBACK_OK"

        out = call_with_fallback(
            primary_client=primary,
            primary_model="m-primary",
            fallback_client=fallback,
            fallback_model="m-fallback",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            max_tokens=100,
        )
        assert out == "FALLBACK_OK"
        # Fallback received the FALLBACK model name
        kwargs = fallback.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "m-fallback"

    def test_auth_error_does_not_fallback(self):
        from unittest.mock import MagicMock

        from openai import APIStatusError

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        err = APIStatusError(
            message="bad key",
            response=MagicMock(status_code=401, request=MagicMock()),
            body=None,
        )
        primary.chat.completions.create.side_effect = err
        fallback = MagicMock()

        with pytest.raises(APIStatusError):
            call_with_fallback(
                primary_client=primary,
                primary_model="m-primary",
                fallback_client=fallback,
                fallback_model="m-fallback",
                messages=[],
                temperature=0.2,
                max_tokens=100,
            )
        fallback.chat.completions.create.assert_not_called()

    def test_no_fallback_client_propagates_error(self):
        from unittest.mock import MagicMock

        from openai import RateLimitError

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        err = RateLimitError(
            message="rate",
            response=MagicMock(status_code=429, request=MagicMock()),
            body=None,
        )
        primary.chat.completions.create.side_effect = err

        with pytest.raises(RateLimitError):
            call_with_fallback(
                primary_client=primary,
                primary_model="m-primary",
                fallback_client=None,
                fallback_model=None,
                messages=[],
                temperature=0.2,
                max_tokens=100,
            )

    def test_returns_actual_model_used_primary(self):
        from unittest.mock import MagicMock

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        primary.chat.completions.create.return_value = "OK"
        resp, used_model = call_with_fallback(
            primary_client=primary,
            primary_model="m-primary",
            fallback_client=None,
            fallback_model=None,
            messages=[],
            temperature=0.2,
            max_tokens=100,
            return_model=True,
        )
        assert resp == "OK"
        assert used_model == "m-primary"

    def test_returns_actual_model_used_fallback(self):
        from unittest.mock import MagicMock

        from openai import RateLimitError

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        primary.chat.completions.create.side_effect = RateLimitError(
            message="rate",
            response=MagicMock(status_code=429, request=MagicMock()),
            body=None,
        )
        fallback = MagicMock()
        fallback.chat.completions.create.return_value = "OK"
        resp, used_model = call_with_fallback(
            primary_client=primary,
            primary_model="m-primary",
            fallback_client=fallback,
            fallback_model="m-fallback",
            messages=[],
            temperature=0.2,
            max_tokens=100,
            return_model=True,
        )
        assert resp == "OK"
        assert used_model == "m-fallback"

    def test_default_behavior_returns_response_only(self):
        """Backward-compat: without return_model=True, return just the response."""
        from unittest.mock import MagicMock

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        primary.chat.completions.create.return_value = "OK"
        out = call_with_fallback(
            primary_client=primary,
            primary_model="m",
            fallback_client=None,
            fallback_model=None,
            messages=[],
            temperature=0.2,
            max_tokens=100,
        )
        assert out == "OK"  # not a tuple

    def test_stream_kwarg_forwarded(self):
        from unittest.mock import MagicMock

        from app.ai.client import call_with_fallback

        primary = MagicMock()
        primary.chat.completions.create.return_value = "STREAM"

        call_with_fallback(
            primary_client=primary,
            primary_model="m",
            fallback_client=None,
            fallback_model=None,
            messages=[],
            temperature=0.2,
            max_tokens=100,
            stream=True,
            tools=[{"type": "function"}],
        )
        kwargs = primary.chat.completions.create.call_args.kwargs
        assert kwargs["stream"] is True
        assert kwargs["tools"] == [{"type": "function"}]
