from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from althea_mcp.config import RuntimeConfig
from althea_mcp.models import (
    Conversation,
    ConversationLog,
    ConversationMessage,
    Message,
    MessagePayload,
)
from althea_mcp.tools import AltheaTools


def make_message(
    message_id: str,
    sender: str,
    content: str,
    created_at: float,
    cycle: int = 7,
) -> Message:
    return Message(
        id=message_id,
        agent_session_id="session-1",
        payload=MessagePayload(sender=sender, content=content),
        read=False,
        created_at=created_at,
        info={"cycle": cycle},
    )


class FakeMessageClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.responses: list[list[Message]] = []
        self.conversations: list[Conversation] = []
        self.conversation_log: ConversationLog | None = None

    async def send_message(self, *, thread_key: str, content: str) -> Message:
        self.sent.append((thread_key, content))
        return make_message("sent", "user", content, 10)

    async def get_messages(self, **arguments: Any) -> list[Message]:
        self.get_calls.append(arguments)
        return self.responses.pop(0)

    async def search_conversations(self, **_arguments: Any) -> list[Conversation]:
        return self.conversations

    async def get_conversation_log(self, **_arguments: Any) -> ConversationLog:
        assert self.conversation_log is not None
        return self.conversation_log


def make_config() -> RuntimeConfig:
    return RuntimeConfig(
        app_url="https://althea.example",
        public_site_url="https://www.althea.example",
        thread_key="codex",
        credentials_path=Path("not-used"),
        http_timeout=60,
        poll_interval=0.001,
        poll_timeout=1,
        user_agent="test",
        log_level="WARNING",
    )


async def test_ask_althea_waits_for_first_assistant_reply() -> None:
    client = FakeMessageClient()
    client.responses = [
        [],
        [make_message("reply", "assistant", "The answer", 11)],
    ]
    tools = AltheaTools(client, make_config())

    result = await tools.ask_althea("Question")

    assert result == "The answer"
    assert client.sent == [("codex", "Question")]
    assert client.get_calls[-1]["sender"] == "assistant"
    assert client.get_calls[-1]["cycle"] == 7
    assert client.get_calls[-1]["created_after"] == 10


async def test_send_message_receipt_identifies_its_conversation() -> None:
    client = FakeMessageClient()
    tools = AltheaTools(client, make_config())

    receipt = await tools.send_message_to_althea("Context")

    assert receipt["conversation_id"] == "session-1"
    assert receipt["thread_key"] == "codex"


async def test_get_messages_returns_chronological_public_shape() -> None:
    client = FakeMessageClient()
    client.responses = [
        [
            make_message("new", "assistant", "Second", 2),
            make_message("old", "user", "First", 1),
        ]
    ]
    tools = AltheaTools(client, make_config())

    messages = await tools.get_althea_messages(limit=2)

    assert [message["content"] for message in messages] == ["First", "Second"]
    assert {message["conversation_id"] for message in messages} == {"session-1"}
    assert {message["thread_key"] for message in messages} == {"codex"}
    assert client.get_calls[0]["most_recent_first"] is True


async def test_get_messages_rejects_invalid_filter() -> None:
    tools = AltheaTools(FakeMessageClient(), make_config())

    with pytest.raises(ValueError, match="sender"):
        await tools.get_althea_messages(sender="Althea")


async def test_search_conversations_returns_public_metadata() -> None:
    client = FakeMessageClient()
    client.conversations = [
        Conversation(
            id="ags_kimi",
            title="Analysis of the Kimi K3 Technical Report",
            platform="app",
            created_at=1,
            updated_at=2,
        )
    ]
    tools = AltheaTools(client, make_config())

    conversations = await tools.search_althea_conversations(" Kimi K3 ")

    assert conversations[0]["id"] == "ags_kimi"
    assert conversations[0]["title"] == "Analysis of the Kimi K3 Technical Report"


async def test_conversation_log_preserves_count_and_chronology() -> None:
    client = FakeMessageClient()
    client.conversation_log = ConversationLog(
        conversation=Conversation(
            id="ags_kimi",
            title="Kimi K3",
            platform="app",
            created_at=1,
        ),
        total_message_count=102,
        returned_message_count=100,
        has_earlier_messages=True,
        messages=[
            ConversationMessage(
                id="message-3",
                sender="user",
                content="Third message",
                created_at=3,
            ),
            ConversationMessage(
                id="message-102",
                sender="assistant",
                content="Last message",
                created_at=102,
            ),
        ],
    )
    tools = AltheaTools(client, make_config())

    conversation_log = await tools.get_althea_conversation_log("ags_kimi")

    assert conversation_log["total_message_count"] == 102
    assert conversation_log["has_earlier_messages"] is True
    assert [message["id"] for message in conversation_log["messages"]] == [
        "message-3",
        "message-102",
    ]
