from __future__ import annotations

import asyncio
import time
from typing import Any

from althea_mcp.client import AltheaClient
from althea_mcp.config import RuntimeConfig


class AltheaTools:
    """MCP tool implementations bound to one configured Althea thread."""

    def __init__(self, client: AltheaClient, config: RuntimeConfig) -> None:
        self.client = client
        self.config = config

    async def ask_althea(self, message: str) -> str:
        """Send a message to the user's personal Althea and wait for her reply.

        Use this when the user wants to ask their Althea a question, share
        context, or request work. This reaches the same canonical Althea account
        used on the web and other channels. Follow-up calls continue the
        configured MCP thread.

        Args:
            message: The message to send to Althea.
        """
        sent_message = await self.client.send_message(
            thread_key=self.config.thread_key,
            content=message,
        )
        deadline = time.monotonic() + self.config.poll_timeout

        while time.monotonic() < deadline:
            remaining_seconds = deadline - time.monotonic()
            await asyncio.sleep(min(self.config.poll_interval, remaining_seconds))
            responses = await self.client.get_messages(
                thread_key=self.config.thread_key,
                sender="assistant",
                created_after=sent_message.created_at,
                limit=1,
            )
            if responses:
                return responses[0].payload.content or ""

        raise TimeoutError(
            f"Althea did not reply within {self.config.poll_timeout:g} seconds. "
            "She may still be working; call `get_althea_messages` to check later."
        )

    async def send_message_to_althea(self, message: str) -> dict[str, Any]:
        """Send a message to the user's personal Althea without waiting.

        Use this for context, notes, or requests that do not need an immediate
        response. The message is real and Althea will process it; use
        `get_althea_messages` to retrieve her eventual reply.

        Args:
            message: The message to send to Althea.
        """
        sent_message = await self.client.send_message(
            thread_key=self.config.thread_key,
            content=message,
        )
        return {
            "status": "sent",
            "message_id": sent_message.id,
            "created_at": sent_message.created_at,
            "thread_key": self.config.thread_key,
        }

    async def get_althea_messages(
        self,
        sender: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent messages from the configured conversation with Althea.

        Use this to inspect history or retrieve a response after
        `send_message_to_althea`.

        Args:
            sender: Optionally filter by "user", "assistant", or "system".
            limit: Maximum number of messages to return, from 1 to 100.
        """
        if sender not in {None, "user", "assistant", "system"}:
            raise ValueError('sender must be one of "user", "assistant", "system", or null')
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        messages = await self.client.get_messages(
            thread_key=self.config.thread_key,
            sender=sender,
            limit=limit,
            most_recent_first=True,
        )
        return [
            {
                "id": message.id,
                "sender": message.payload.sender,
                "content": message.payload.content,
                "created_at": message.created_at,
            }
            for message in reversed(messages)
        ]
