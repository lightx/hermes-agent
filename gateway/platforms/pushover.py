"""Pushover platform adapter — outbound notifications only."""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
MAX_MESSAGE_LENGTH = 1024  # Pushover limit is 1024 chars per message


def check_pushover_requirements() -> bool:
    """Check if Pushover dependencies are available."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("PUSHOVER_APP_TOKEN") and os.getenv("PUSHOVER_USER_KEY"))


class PushoverAdapter(BasePlatformAdapter):
    """Outbound-only Pushover adapter.

    Sends push notifications to the Pushover API.
    Does NOT receive messages (no connect/disconnect needed).
    """

    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.PUSHOVER)
        self._app_token: str = os.getenv("PUSHOVER_APP_TOKEN", "")
        self._user_key: str = os.getenv("PUSHOVER_USER_KEY", "")
        # Optional: device identifier (can be set in config.extra)
        self._device: str = config.extra.get("device", "")

    async def connect(self) -> bool:
        # No persistent connection needed for outbound-only
        return True

    async def disconnect(self):
        # No persistent connection to tear down
        pass

    async def send(
        self,
        chat_id: str,
        text: str,
        **kwargs
    ) -> SendResult:
        """Send a Pushover notification.

        chat_id is ignored — we always send to PUSHOVER_USER_KEY.
        The text is the notification message.
        """
        if not self._app_token or not self._user_key:
            logger.error("Pushover: PUSHOVER_APP_TOKEN or PUSHOVER_USER_KEY not set")
            return SendResult(success=False, error="Pushover credentials not configured")

        # Truncate if needed
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[: MAX_MESSAGE_LENGTH - 3] + "..."

        payload: Dict[str, str] = {
            "token": self._app_token,
            "user": self._user_key,
            "message": text,
        }
        if self._device:
            payload["device"] = self._device

        # Optional: title can be passed in kwargs
        if "title" in kwargs:
            payload["title"] = kwargs["title"]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(PUSHOVER_API_URL, data=payload) as resp:
                    result = await resp.json()
                    if resp.status == 200 and result.get("status") == 1:
                        return SendResult(success=True, message_id=result.get("request"))
                    else:
                        error_msg = result.get("errors", [result.get("message", "Unknown error")])[0]
                        logger.error("Pushover send failed: %s", error_msg)
                        return SendResult(success=False, error=error_msg)
        except aiohttp.ClientError as e:
            logger.error("Pushover HTTP error: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_image(self, chat_id: str, image_url: str, caption: str = "") -> SendResult:
        """Send an image attachment via Pushover.

        Pushover supports image attachments via URL.
        For now, fall back to sending caption + URL as text.
        """
        content = f"{caption}\n\n{image_url}" if caption else image_url
        return await self.send(chat_id, content)

    def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Pushover doesn't support chat enumeration — return user key as name."""
        return {"name": "Pushover", "type": "user", "chat_id": self._user_key}
