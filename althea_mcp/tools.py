from __future__ import annotations

import asyncio
import time
from typing import Any

from althea_mcp.client import AltheaClient
from althea_mcp.config import RuntimeConfig
from althea_mcp.errors import AltheaProtocolError


class AltheaTools:
    """MCP tool implementations bound to one configured Althea thread."""

    def __init__(self, client: AltheaClient, config: RuntimeConfig) -> None:
        self.client = client
        self.config = config

    async def ask_althea(self, message: str) -> str:
        """Send a message to the user's personal Althea and wait for her reply.

        Use this when the user wants to ask their Althea a question, share
        context, or request work. This reaches the same canonical Althea account
        used on the web and other channels. Through Althea, a request can also
        draw on her consent-first network of verified ML researchers. Follow-up
        calls continue the configured MCP thread.

        Args:
            message: The message to send to Althea.
        """
        sent_message = await self.client.send_message(
            thread_key=self.config.thread_key,
            content=message,
        )
        cycle = sent_message.info.get("cycle") if sent_message.info else None
        if type(cycle) is not int:
            raise AltheaProtocolError("Althea did not return cycle metadata for the sent message")
        deadline = time.monotonic() + self.config.poll_timeout

        while time.monotonic() < deadline:
            remaining_seconds = deadline - time.monotonic()
            await asyncio.sleep(min(self.config.poll_interval, remaining_seconds))
            responses = await self.client.get_messages(
                thread_key=self.config.thread_key,
                sender="assistant",
                cycle=cycle,
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
            "conversation_id": sent_message.agent_session_id,
            "created_at": sent_message.created_at,
            "cycle": sent_message.info.get("cycle") if sent_message.info else None,
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
                "conversation_id": message.agent_session_id,
                "thread_key": self.config.thread_key,
                "sender": message.payload.sender,
                "content": message.payload.content,
                "created_at": message.created_at,
                "cycle": message.info.get("cycle") if message.info else None,
            }
            for message in reversed(messages)
        ]

    async def search_althea_conversations(
        self,
        query: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find this user's Althea conversations across every channel.

        Use this before `get_althea_conversation_log` when the user identifies
        a prior conversation by title or topic rather than its conversation ID.
        With no query, this returns the most recently active conversations.

        Args:
            query: Optional title or topic to search for.
            limit: Maximum number of conversations to return, from 1 to 100.
        """
        normalized_query = query.strip() if query is not None else None
        if query is not None and not normalized_query:
            raise ValueError("query must contain non-whitespace characters")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        conversations = await self.client.search_conversations(
            query=normalized_query,
            limit=limit,
        )
        return [conversation.model_dump(mode="json") for conversation in conversations]

    async def get_althea_conversation_log(
        self,
        conversation_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Fetch the recent transcript of any conversation owned by this user.

        This reads conversations from the user's canonical Althea account,
        including web/app and other channel conversations, not only the
        configured MCP thread. Messages are returned chronologically. Use
        `search_althea_conversations` first when the conversation ID is unknown.

        Args:
            conversation_id: Conversation ID returned by the search tool.
            limit: Number of recent messages to return, from 1 to 100.
        """
        if not conversation_id.strip():
            raise ValueError("conversation_id must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        conversation_log = await self.client.get_conversation_log(
            conversation_id=conversation_id.strip(),
            limit=limit,
        )
        return conversation_log.model_dump(mode="json")
