"""
Tests for LiteLLMMessagesToCompletionTransformationHandler

Focuses on the _route_openai_thinking_to_responses_api_if_needed method
which decides whether to route OpenAI-provider requests to the Responses API
when thinking params are present.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath("../../../../.."))

import litellm
from litellm.llms.anthropic.experimental_pass_through.adapters.handler import (
    LiteLLMMessagesToCompletionTransformationHandler,
)


class TestRouteOpenaiThinkingToResponsesApi:
    """Tests for _route_openai_thinking_to_responses_api_if_needed"""

    def test_routes_to_responses_api_when_openai_thinking_enabled(self):
        """When provider is openai and thinking is enabled, model should get responses/ prefix"""
        original_setting = litellm.use_chat_completions_url_for_anthropic_messages
        try:
            litellm.use_chat_completions_url_for_anthropic_messages = False
            kwargs = {
                "model": "gpt-4",
                "custom_llm_provider": "openai",
            }
            thinking = {"type": "enabled", "budget_tokens": 1024}

            LiteLLMMessagesToCompletionTransformationHandler._route_openai_thinking_to_responses_api_if_needed(
                kwargs, thinking=thinking
            )

            assert kwargs["model"] == "responses/gpt-4"
        finally:
            litellm.use_chat_completions_url_for_anthropic_messages = original_setting

    def test_does_not_route_when_use_chat_completions_url_set(self):
        """When use_chat_completions_url_for_anthropic_messages is True,
        the responses/ prefix should NOT be added even with thinking enabled.

        This is critical for setups where the upstream endpoint (e.g. Open WebUI)
        does not support /v1/responses.
        """
        original_setting = litellm.use_chat_completions_url_for_anthropic_messages
        try:
            litellm.use_chat_completions_url_for_anthropic_messages = True
            kwargs = {
                "model": "openai/anthropic.claude-sonnet-4-5-20250929",
                "custom_llm_provider": "openai",
            }
            thinking = {"type": "enabled", "budget_tokens": 10000}

            LiteLLMMessagesToCompletionTransformationHandler._route_openai_thinking_to_responses_api_if_needed(
                kwargs, thinking=thinking
            )

            # Model should remain unchanged - no responses/ prefix
            assert kwargs["model"] == "openai/anthropic.claude-sonnet-4-5-20250929"
        finally:
            litellm.use_chat_completions_url_for_anthropic_messages = original_setting

    def test_does_not_route_when_thinking_not_enabled(self):
        """When thinking is not enabled, no routing should happen"""
        original_setting = litellm.use_chat_completions_url_for_anthropic_messages
        try:
            litellm.use_chat_completions_url_for_anthropic_messages = False
            kwargs = {
                "model": "gpt-4",
                "custom_llm_provider": "openai",
            }
            thinking = None

            LiteLLMMessagesToCompletionTransformationHandler._route_openai_thinking_to_responses_api_if_needed(
                kwargs, thinking=thinking
            )

            assert kwargs["model"] == "gpt-4"
        finally:
            litellm.use_chat_completions_url_for_anthropic_messages = original_setting

    def test_does_not_route_for_non_openai_provider(self):
        """Non-openai providers should never get routed to responses API"""
        original_setting = litellm.use_chat_completions_url_for_anthropic_messages
        try:
            litellm.use_chat_completions_url_for_anthropic_messages = False
            kwargs = {
                "model": "claude-sonnet-4-20250514",
                "custom_llm_provider": "anthropic",
            }
            thinking = {"type": "enabled", "budget_tokens": 1024}

            LiteLLMMessagesToCompletionTransformationHandler._route_openai_thinking_to_responses_api_if_needed(
                kwargs, thinking=thinking
            )

            assert kwargs["model"] == "claude-sonnet-4-20250514"
        finally:
            litellm.use_chat_completions_url_for_anthropic_messages = original_setting
