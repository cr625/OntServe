"""
Wolfram AgentOne API Service for OntServe

Provides access to the Wolfram AgentOne chat completions API,
which combines LLM responses with Wolfram Language computations
and curated knowledge.

API Reference: https://www.wolfram.com/apis/documentation/cag/wolfram-agent-one-api/
"""

import os
import logging
import time
from typing import Dict, List, Any, Optional

import requests

logger = logging.getLogger(__name__)

AGENTONE_ENDPOINT = "https://services.wolfram.com/api/agent-one/v1/chat/completions"


class WolframService:
    """
    Client for the Wolfram AgentOne API.

    Handles authentication, request formatting, error handling,
    and conversation history for multi-turn interactions.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = 120):
        """
        Initialize the Wolfram service.

        Args:
            api_key: Wolfram API key. Falls back to WOLFRAM_API_KEY env var.
            timeout: Request timeout in seconds. AgentOne queries can involve
                     computation, so the default is generous.
        """
        self.api_key = api_key or os.environ.get("WOLFRAM_API_KEY", "")
        self.timeout = timeout
        self._session = requests.Session()

        if not self.api_key:
            logger.warning("WOLFRAM_API_KEY not configured -- Wolfram queries will fail")

    @property
    def is_configured(self) -> bool:
        """Check whether an API key is present."""
        return bool(self.api_key)

    def query(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a query to Wolfram AgentOne.

        Args:
            message: The user message to send.
            conversation_history: Prior messages for multi-turn context.
                Each dict has 'role' ("user" or "assistant") and 'content'.

        Returns:
            Dict with keys:
                - success (bool)
                - content (str): The assistant response text
                - model (str): Model identifier ("AgentOne")
                - uuid (str): Response identifier
                - error (str, optional): Error message on failure
        """
        if not self.is_configured:
            return {
                "success": False,
                "content": "",
                "error": "WOLFRAM_API_KEY is not configured.",
            }

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": message})

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
        }

        payload = {
            "messages": messages,
            "stream": False,
        }

        start = time.monotonic()
        try:
            resp = self._session.post(
                AGENTONE_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            elapsed = time.monotonic() - start
            logger.info("Wolfram AgentOne responded in %.1fs (HTTP %d)", elapsed, resp.status_code)

            if resp.status_code == 403:
                return {
                    "success": False,
                    "content": "",
                    "error": "Invalid or missing Wolfram API key (HTTP 403).",
                }

            if resp.status_code == 501:
                return {
                    "success": False,
                    "content": "",
                    "error": "Wolfram could not process the input (HTTP 501).",
                }

            if resp.status_code != 200:
                return {
                    "success": False,
                    "content": "",
                    "error": f"Wolfram API returned HTTP {resp.status_code}: {resp.text[:500]}",
                }

            data = resp.json()

            # Extract assistant message from OpenAI-compatible response
            choices = data.get("choices", [])
            if not choices:
                return {
                    "success": False,
                    "content": "",
                    "error": "Empty response from Wolfram AgentOne.",
                }

            assistant_message = choices[0].get("message", {}).get("content", "")

            return {
                "success": True,
                "content": assistant_message,
                "model": data.get("model", "AgentOne"),
                "uuid": data.get("uuid", ""),
            }

        except requests.Timeout:
            elapsed = time.monotonic() - start
            logger.error("Wolfram AgentOne request timed out after %.1fs", elapsed)
            return {
                "success": False,
                "content": "",
                "error": f"Request timed out after {self.timeout}s.",
            }
        except requests.ConnectionError as exc:
            logger.error("Wolfram AgentOne connection error: %s", exc)
            return {
                "success": False,
                "content": "",
                "error": "Could not connect to Wolfram API.",
            }
        except Exception as exc:
            logger.error("Wolfram AgentOne unexpected error: %s", exc, exc_info=True)
            return {
                "success": False,
                "content": "",
                "error": str(exc),
            }

    def get_status(self) -> Dict[str, Any]:
        """
        Return service status information.
        """
        return {
            "service": "Wolfram AgentOne",
            "configured": self.is_configured,
            "endpoint": AGENTONE_ENDPOINT,
            "timeout_seconds": self.timeout,
        }
