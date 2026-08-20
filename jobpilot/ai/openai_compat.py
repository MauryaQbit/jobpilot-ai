"""OpenAI-compatible chat completions provider.

Uses ``httpx`` to call any endpoint implementing the OpenAI chat completions
JSON contract. The API key is read from settings at request time and is never
logged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from jobpilot.ai.provider import AIProviderError, AITimeoutError
from jobpilot.config import Settings

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    """Call an OpenAI-compatible ``/chat/completions`` endpoint."""

    name = "openai_compatible"

    def __init__(self, settings: Settings) -> None:
        self.base_url = (settings.ai_base_url or "https://api.openai.com/v1").rstrip(
            "/"
        )
        self.api_key = settings.ai_api_key
        self.model = settings.ai_model
        self.timeout = settings.ai_timeout_seconds
        self.temperature = settings.ai_temperature
        self.retries = settings.ai_retries

    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def complete_json(
        self, system: str, user: str, max_tokens: int = 2000
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        attempts = self.retries + 1
        for attempt in range(attempts):
            try:
                response = httpx.post(
                    self._endpoint(),
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise AIProviderError(
                        f"AI provider returned a non-object JSON value: {type(parsed).__name__}"
                    )
                return parsed
            except httpx.TimeoutException:
                last_error = AITimeoutError(
                    f"AI provider timed out after {self.timeout:.0f}s (attempt {attempt + 1}/{attempts})"
                )
                logger.warning("%s", last_error)
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status in {429, 500, 502, 503, 504} and attempt < attempts - 1:
                    last_error = AIProviderError(f"AI provider HTTP {status}; retrying")
                    logger.warning("%s", last_error)
                    continue
                last_error = AIProviderError(
                    f"AI provider returned HTTP {status}: {error.response.text[:200]}"
                )
                break
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                json.JSONDecodeError,
            ) as error:
                last_error = AIProviderError(f"AI provider request failed: {error}")
                break
            except Exception as error:
                last_error = AIProviderError(f"AI provider unexpected failure: {error}")
                break

        raise last_error or AIProviderError("AI provider request failed")
