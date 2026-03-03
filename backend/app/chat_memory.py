from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .config import settings


@dataclass
class ChatTurn:
    user: str
    assistant: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConversationState:
    turns: list[ChatTurn] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conversations: dict[str, ConversationState] = {}

    def _cleanup_expired_locked(self) -> None:
        ttl = timedelta(minutes=max(1, settings.ai_chat_session_ttl_minutes))
        cutoff = datetime.now(timezone.utc) - ttl
        expired_ids = [conv_id for conv_id, state in self._conversations.items() if state.updated_at < cutoff]
        for conv_id in expired_ids:
            self._conversations.pop(conv_id, None)

    @staticmethod
    def _sanitize_conversation_id(conversation_id: str | None) -> str:
        if not conversation_id:
            return uuid4().hex
        normalized = conversation_id.strip()
        if not normalized or not re.fullmatch(r"[a-zA-Z0-9_\-]{8,128}", normalized):
            return uuid4().hex
        return normalized

    def get_history(self, conversation_id: str | None) -> tuple[str, list[ChatTurn]]:
        with self._lock:
            self._cleanup_expired_locked()
            conv_id = self._sanitize_conversation_id(conversation_id)
            state = self._conversations.setdefault(conv_id, ConversationState())
            state.updated_at = datetime.now(timezone.utc)
            turns = state.turns[-max(1, settings.ai_chat_memory_turns) :]
            return conv_id, turns

    def append_turn(self, conversation_id: str, user: str, assistant: str) -> None:
        with self._lock:
            self._cleanup_expired_locked()
            conv_id = self._sanitize_conversation_id(conversation_id)
            state = self._conversations.setdefault(conv_id, ConversationState())
            state.turns.append(ChatTurn(user=user, assistant=assistant))
            max_turns = max(1, settings.ai_chat_memory_turns)
            if len(state.turns) > max_turns:
                state.turns = state.turns[-max_turns:]
            state.updated_at = datetime.now(timezone.utc)

    def clear(self, conversation_id: str | None) -> str:
        conv_id = self._sanitize_conversation_id(conversation_id)
        with self._lock:
            self._conversations.pop(conv_id, None)
        return conv_id


chat_memory_store = ChatMemoryStore()
