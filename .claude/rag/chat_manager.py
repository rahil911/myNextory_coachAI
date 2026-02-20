"""
Chat Manager for MyNextory RAG System
Handles conversation history, context-aware chat, and three-tier memory.

Adapted from enhanced-rag-system:
- LLM: ChatOpenAI → ChatAnthropic (Claude Sonnet/Opus)
- Added three-tier memory: buffer (10 msgs), summary (50 msgs), key_facts (permanent)
- Added model tier routing (Sonnet default, Opus on demand)
- Added token budget tracking per session
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_anthropic import ChatAnthropic
import structlog

from config import (
    SONNET_MODEL, OPUS_MODEL, TIER_THRESHOLD,
    MEMORY_BUFFER_SIZE, MEMORY_SUMMARY_THRESHOLD, MEMORY_KEY_FACTS_MAX,
    MAX_TOTAL_TOKENS,
)

logger = structlog.get_logger()


class ThreeTierMemory:
    """
    Three-tier memory system for conversation context:
    1. Buffer: Last N messages kept verbatim (short-term)
    2. Summary: Older messages compressed into running summary (medium-term)
    3. Key Facts: Permanent facts extracted from conversation (long-term)
    """

    def __init__(
        self,
        buffer_size: int = MEMORY_BUFFER_SIZE,
        summary_threshold: int = MEMORY_SUMMARY_THRESHOLD,
        max_key_facts: int = MEMORY_KEY_FACTS_MAX,
    ):
        self.buffer_size = buffer_size
        self.summary_threshold = summary_threshold
        self.max_key_facts = max_key_facts

        self.buffer: List[Dict[str, str]] = []
        self.summary: str = ""
        self.key_facts: List[str] = []
        self.total_messages: int = 0

    def add_message(self, role: str, content: str):
        self.buffer.append({'role': role, 'content': content})
        self.total_messages += 1
        if len(self.buffer) > self.summary_threshold:
            self._compress_to_summary()

    def _compress_to_summary(self):
        """Move older messages from buffer into running summary."""
        to_summarize = self.buffer[:-self.buffer_size]
        self.buffer = self.buffer[-self.buffer_size:]

        parts = []
        for msg in to_summarize:
            parts.append(f"{msg['role']}: {msg['content'][:200]}")
        if parts:
            new_context = " | ".join(parts)
            if self.summary:
                self.summary = f"{self.summary} | {new_context}"
            else:
                self.summary = new_context
            # Truncate to prevent unbounded growth
            if len(self.summary) > 5000:
                self.summary = self.summary[-5000:]

    def add_key_fact(self, fact: str):
        if len(self.key_facts) < self.max_key_facts:
            if fact not in self.key_facts:
                self.key_facts.append(fact)

    def get_context_string(self) -> str:
        parts = []
        if self.key_facts:
            parts.append("Key facts about this learner: " + "; ".join(self.key_facts))
        if self.summary:
            parts.append("Conversation summary: " + self.summary)
        return "\n".join(parts)

    def get_recent_messages(self) -> List[Dict[str, str]]:
        return self.buffer[-self.buffer_size:]

    def to_dict(self) -> dict:
        return {
            'buffer': self.buffer,
            'summary': self.summary,
            'key_facts': self.key_facts,
            'total_messages': self.total_messages,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ThreeTierMemory':
        mem = cls()
        mem.buffer = data.get('buffer', [])
        mem.summary = data.get('summary', '')
        mem.key_facts = data.get('key_facts', [])
        mem.total_messages = data.get('total_messages', 0)
        return mem


class ChatManager:
    """
    Manages chat conversations with three-tier memory and model tier routing.
    """

    def __init__(self, model: str = None):
        self.chat_stores: Dict[str, BaseChatMessageHistory] = {}
        self.memories: Dict[str, ThreeTierMemory] = {}
        self.token_budgets: Dict[str, Dict[str, int]] = {}

        model_name = model or SONNET_MODEL
        self.llm = ChatAnthropic(
            model=model_name,
            temperature=0,
            max_tokens=4096,
            timeout=30,
            max_retries=2,
        )
        self.opus_llm = ChatAnthropic(
            model=OPUS_MODEL,
            temperature=0,
            max_tokens=4096,
            timeout=60,
            max_retries=2,
        )

    def get_llm(self, use_opus: bool = False) -> ChatAnthropic:
        return self.opus_llm if use_opus else self.llm

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        if session_id not in self.chat_stores:
            self.chat_stores[session_id] = ChatMessageHistory()
            self.memories[session_id] = ThreeTierMemory()
            self.token_budgets[session_id] = {
                'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
            }
            logger.info(f"Created new chat session: {session_id}")
        return self.chat_stores[session_id]

    def get_memory(self, session_id: str) -> ThreeTierMemory:
        if session_id not in self.memories:
            self.memories[session_id] = ThreeTierMemory()
        return self.memories[session_id]

    def track_tokens(self, session_id: str, input_tokens: int, output_tokens: int):
        if session_id not in self.token_budgets:
            self.token_budgets[session_id] = {
                'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
            }
        budget = self.token_budgets[session_id]
        budget['input_tokens'] += input_tokens
        budget['output_tokens'] += output_tokens
        budget['total_tokens'] += input_tokens + output_tokens

    def is_within_budget(self, session_id: str) -> bool:
        budget = self.token_budgets.get(session_id, {})
        return budget.get('total_tokens', 0) < MAX_TOTAL_TOKENS

    def clear_session_history(self, session_id: str) -> bool:
        if session_id in self.chat_stores:
            self.chat_stores[session_id].clear()
            self.memories.pop(session_id, None)
            self.token_budgets.pop(session_id, None)
            return True
        return False

    def get_contextualized_prompt(self) -> ChatPromptTemplate:
        contextualize_q_system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, "
            "formulate a standalone question which can be understood "
            "without the chat history. Do NOT answer the question, "
            "just reformulate it if needed and otherwise return it as is."
        )
        return ChatPromptTemplate.from_messages([
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

    def get_qa_prompt(
        self,
        is_global_chat: bool = False,
        memory_context: str = "",
    ) -> ChatPromptTemplate:
        memory_section = ""
        if memory_context:
            memory_section = f"\n\nLearner Context:\n{memory_context}\n"

        if not is_global_chat:
            system_prompt = (
                "You are Tory, a warm and insightful AI learning companion on the "
                "MyNextory coaching platform. Answer the learner's question using "
                "ONLY the provided context. If the context doesn't contain enough "
                "information, say so honestly."
                f"{memory_section}"
                "\n\nContext: {context}"
            )
        else:
            system_prompt = (
                "You are Tory, a warm and insightful AI learning companion. "
                "Use the provided context when available, and supplement with your "
                "knowledge when the context is insufficient. Always be encouraging "
                "and relate answers back to the learner's growth journey."
                f"{memory_section}"
                "\n\nContext: {context}"
            )

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

    def create_conversational_chain(
        self,
        retriever,
        is_global_chat: bool = False,
        session_id: str = None,
        use_opus: bool = False,
    ):
        memory_context = ""
        if session_id:
            memory = self.get_memory(session_id)
            memory_context = memory.get_context_string()

        llm = self.get_llm(use_opus=use_opus)
        contextualize_prompt = self.get_contextualized_prompt()
        qa_prompt = self.get_qa_prompt(is_global_chat, memory_context)

        history_aware_retriever = create_history_aware_retriever(
            llm, retriever, contextualize_prompt
        )
        question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
        rag_chain = create_retrieval_chain(
            history_aware_retriever, question_answer_chain
        )

        return RunnableWithMessageHistory(
            rag_chain,
            self.get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

    def process_query_with_history(
        self,
        query: str,
        session_id: str,
        retriever,
        is_global_chat: bool = False,
        use_opus: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            memory = self.get_memory(session_id)
            memory.add_message('human', query)

            chain = self.create_conversational_chain(
                retriever, is_global_chat, session_id, use_opus
            )
            response = chain.invoke(
                {"input": query},
                config={"configurable": {"session_id": session_id}},
            )

            answer = response.get("answer", "")
            memory.add_message('assistant', answer[:500])

            metadata = {
                "session_id": session_id,
                "is_global_chat": is_global_chat,
                "model": OPUS_MODEL if use_opus else SONNET_MODEL,
                "timestamp": datetime.now().isoformat(),
                "context_documents": len(response.get("context", [])),
                "chat_history_length": len(
                    self.get_session_history(session_id).messages
                ),
                "memory_tier_stats": {
                    "buffer_size": len(memory.buffer),
                    "summary_length": len(memory.summary),
                    "key_facts_count": len(memory.key_facts),
                    "total_messages": memory.total_messages,
                },
            }

            return answer, metadata

        except Exception as e:
            logger.error(f"Failed to process query with history: {e}")
            return (
                "I encountered an error processing your question. Please try again.",
                {"error": str(e), "session_id": session_id},
            )

    def save_conversation(
        self, session_id: str, user_id: str, filepath: str
    ) -> bool:
        try:
            if session_id not in self.chat_stores:
                return False

            history = self.chat_stores[session_id]
            messages = [
                {"type": m.type, "content": m.content}
                for m in history.messages
            ]

            conversation_data = {
                "session_id": session_id,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "messages": messages,
                "memory": (
                    self.memories[session_id].to_dict()
                    if session_id in self.memories else None
                ),
                "token_budget": self.token_budgets.get(session_id),
            }

            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(conversation_data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")
            return False

    def load_conversation(self, filepath: str) -> Optional[str]:
        try:
            if not os.path.exists(filepath):
                return None
            with open(filepath, 'r') as f:
                data = json.load(f)

            session_id = data.get("session_id")
            if not session_id:
                return None

            self.chat_stores[session_id] = ChatMessageHistory()
            for msg in data.get("messages", []):
                if msg["type"] == "human":
                    self.chat_stores[session_id].add_user_message(msg["content"])
                elif msg["type"] == "ai":
                    self.chat_stores[session_id].add_ai_message(msg["content"])

            if data.get("memory"):
                self.memories[session_id] = ThreeTierMemory.from_dict(data["memory"])
            if data.get("token_budget"):
                self.token_budgets[session_id] = data["token_budget"]

            return session_id
        except Exception as e:
            logger.error(f"Failed to load conversation: {e}")
            return None

    def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.chat_stores:
            return {
                "session_id": session_id,
                "message_count": 0,
                "turns": 0,
                "last_message": None,
            }

        history = self.chat_stores[session_id]
        messages = history.messages
        memory = self.memories.get(session_id)

        return {
            "session_id": session_id,
            "message_count": len(messages),
            "turns": len([m for m in messages if m.type == "human"]),
            "last_message": messages[-1].content if messages else None,
            "memory_stats": memory.to_dict() if memory else None,
            "token_budget": self.token_budgets.get(session_id),
        }
