"""
Hybrid Query Engine for MyNextory RAG System
Combines shared lesson knowledge with user-specific overlays.
Parallel retrieval, personal boost, EPP-aware context, scope enforcement.

Adapted from enhanced-rag-system:
- LLM: OpenAI → Anthropic Claude (Sonnet/Opus)
- Added EPP-aware context injection (learner profile in search context)
- Added scope enforcement: Companion (assigned lessons only), Curator (all)
- User ID: email → nx_user_id
- Keep: parallel search, 1.5x personal boost, smart merge
"""

import hashlib
import json
import os
import pickle
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any

import faiss
import numpy as np
import structlog
from anthropic import Anthropic
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings

from rag_config import (
    EMBEDDING_MODEL, EMBEDDING_DIMENSIONS,
    SONNET_MODEL, OPUS_MODEL, TIER_THRESHOLD,
    USER_OVERLAY_DIR, MAX_USER_OVERLAYS,
    MAX_CONTEXT_TOKENS,
)
from shared_vector_manager import shared_vector_manager
from user_manager_optimized import OptimizedUserManager
from chat_manager import ChatManager
from user_backpack_ingestion import UserBackpackIngestion

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Scope enforcement constants
# ---------------------------------------------------------------------------
SCOPE_COMPANION = 'companion'  # Learner-facing: only assigned lessons
SCOPE_CURATOR = 'curator'      # Coach-facing: all lessons


class UserOverlay:
    """Lightweight user-specific data overlay identified by nx_user_id."""

    def __init__(self, nx_user_id: int):
        self.nx_user_id = nx_user_id
        self.user_hash = hashlib.md5(str(nx_user_id).encode()).hexdigest()[:16]
        self.overlay_path = os.path.join(USER_OVERLAY_DIR, self.user_hash)
        self.profile_data: List[Dict] = []
        self.epp_profile: Dict = {}
        self.onboarding_qa: Dict = {}
        self.personal_index = None

        self._backpack_ingestion = None
        self.ensure_directories()
        self.load_overlay()

    def ensure_directories(self):
        os.makedirs(self.overlay_path, exist_ok=True)

    def load_overlay(self):
        try:
            # Profile
            profile_path = os.path.join(self.overlay_path, 'profile.json')
            if os.path.exists(profile_path):
                with open(profile_path, 'r') as f:
                    self.profile_data = json.load(f)

            # EPP profile
            epp_path = os.path.join(self.overlay_path, 'epp_profile.json')
            if os.path.exists(epp_path):
                with open(epp_path, 'r') as f:
                    self.epp_profile = json.load(f)

            # Onboarding Q&A
            qa_path = os.path.join(self.overlay_path, 'onboarding_qa.json')
            if os.path.exists(qa_path):
                with open(qa_path, 'r') as f:
                    self.onboarding_qa = json.load(f)

            # Personal FAISS index
            personal_index_dir = os.path.join(self.overlay_path, 'personal_index')
            if os.path.exists(os.path.join(personal_index_dir, 'index.faiss')):
                try:
                    embeddings = OpenAIEmbeddings(
                        model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
                    )
                    self.personal_index = FAISS.load_local(
                        personal_index_dir, embeddings,
                        allow_dangerous_deserialization=True,
                    )
                except Exception as e:
                    logger.error(f"Failed to load personal index: {e}")
                    self.personal_index = None

        except Exception as e:
            logger.error(
                f"Failed to load overlay for nx_user_id={self.nx_user_id}: {e}"
            )

    def save_overlay(self):
        try:
            # Profile
            with open(os.path.join(self.overlay_path, 'profile.json'), 'w') as f:
                json.dump(self.profile_data, f, indent=2)

            # EPP
            if self.epp_profile:
                with open(os.path.join(self.overlay_path, 'epp_profile.json'), 'w') as f:
                    json.dump(self.epp_profile, f, indent=2)

            # Onboarding Q&A
            if self.onboarding_qa:
                with open(os.path.join(self.overlay_path, 'onboarding_qa.json'), 'w') as f:
                    json.dump(self.onboarding_qa, f, indent=2)

            # Personal FAISS index
            if self.personal_index:
                personal_dir = os.path.join(self.overlay_path, 'personal_index')
                os.makedirs(personal_dir, exist_ok=True)
                if hasattr(self.personal_index, 'index') and self.personal_index.index.ntotal > 0:
                    self.personal_index.save_local(personal_dir)

        except Exception as e:
            logger.error(f"Failed to save overlay: {e}")

    def search_personal_index(self, query: str, k: int = 4) -> List[Dict]:
        """Search user's personal FAISS index (backpack docs)."""
        results = []
        try:
            if (
                self.personal_index
                and hasattr(self.personal_index, 'index')
                and self.personal_index.index.ntotal > 0
            ):
                docs_with_scores = self.personal_index.similarity_search_with_score(
                    query, k=k
                )
                for doc, score in docs_with_scores:
                    similarity = 1.0 / (1.0 + score)
                    results.append({
                        'content': doc.page_content,
                        'metadata': doc.metadata,
                        'similarity_score': similarity,
                        'source': doc.metadata.get('source', 'personal'),
                        'is_personal': True,
                    })
        except Exception as e:
            logger.warning(f"Error searching personal index: {e}")

        # Dedup and sort
        seen = set()
        unique = []
        for r in results:
            key = hash(r['content'][:100])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        unique.sort(key=lambda x: x['similarity_score'], reverse=True)
        return unique[:k]

    def get_epp_context_string(self) -> str:
        """Build natural-language EPP context for injection into prompts."""
        if not self.epp_profile:
            return ""

        parts = []
        strengths = self.epp_profile.get('strengths', [])
        gaps = self.epp_profile.get('gaps', [])

        if strengths:
            top = strengths[:3]
            traits = ", ".join(
                f"{s['trait']} ({s['score']:.0f})" for s in top
            )
            parts.append(f"Top strengths: {traits}")

        if gaps:
            top_gaps = gaps[:3]
            traits = ", ".join(
                f"{g['trait']} ({g['score']:.0f})" for g in top_gaps
            )
            parts.append(f"Growth areas: {traits}")

        return "; ".join(parts)

    def get_onboarding_context_string(self) -> str:
        """Build context from onboarding Q&A."""
        if not self.onboarding_qa:
            return ""
        parts = []
        for field, data in self.onboarding_qa.items():
            if isinstance(data, dict) and data.get('answer'):
                parts.append(f"{data['question']}: {data['answer'][:150]}")
        return " | ".join(parts[:5])  # Limit to 5 most relevant

    @property
    def backpack_ingestion(self) -> UserBackpackIngestion:
        if self._backpack_ingestion is None:
            self._backpack_ingestion = UserBackpackIngestion(
                self.nx_user_id, self.user_hash
            )
        return self._backpack_ingestion


class HybridQueryEngine:
    """
    Hybrid query engine combining shared lesson content with personal data.
    Supports scope enforcement (Companion vs Curator) and EPP-aware context.
    """

    def __init__(self, nx_user_id: int = None):
        self.shared_manager = shared_vector_manager
        self.user_manager = OptimizedUserManager()
        self.chat_manager = ChatManager()
        self.anthropic_client = Anthropic()
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
        )
        self.user_overlays: OrderedDict[int, UserOverlay] = OrderedDict()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.nx_user_id = nx_user_id

        logger.info(f"Hybrid Query Engine initialized for nx_user_id={nx_user_id}")

    def get_user_overlay(self, nx_user_id: int) -> UserOverlay:
        if nx_user_id in self.user_overlays:
            self.user_overlays.move_to_end(nx_user_id)
            return self.user_overlays[nx_user_id]

        overlay = UserOverlay(nx_user_id)
        self.user_overlays[nx_user_id] = overlay

        while len(self.user_overlays) > MAX_USER_OVERLAYS:
            oldest = next(iter(self.user_overlays))
            del self.user_overlays[oldest]

        return overlay

    # ------------------------------------------------------------------
    # Scope enforcement
    # ------------------------------------------------------------------

    def _get_assigned_lesson_ids(self, nx_user_id: int) -> Optional[set]:
        """
        Get lesson IDs assigned to this learner via tory_recommendations.
        Returns None if no assignments found (fallback to all).
        """
        try:
            import subprocess
            import xml.etree.ElementTree as ET
            from rag_config import DATABASE, DB_QUERY_TIMEOUT

            result = subprocess.run(
                [
                    "mysql", DATABASE, "--xml", "-e",
                    f"SELECT DISTINCT nx_lesson_id FROM tory_recommendations "
                    f"WHERE nx_user_id = {int(nx_user_id)} "
                    f"AND deleted_at IS NULL",
                ],
                capture_output=True, text=True, timeout=DB_QUERY_TIMEOUT,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None

            root = ET.fromstring(result.stdout)
            ids = set()
            for row in root.findall("row"):
                for field in row.findall("field"):
                    if field.get("name") == "nx_lesson_id" and field.text:
                        ids.add(int(field.text))
            return ids if ids else None
        except Exception:
            return None

    def _filter_by_scope(
        self,
        results: List[Dict],
        scope: str,
        nx_user_id: int,
    ) -> List[Dict]:
        """
        Enforce scope:
        - COMPANION: only results from assigned lessons
        - CURATOR: all results (no filtering)
        """
        if scope == SCOPE_CURATOR:
            return results

        # Companion scope: filter to assigned lessons only
        assigned = self._get_assigned_lesson_ids(nx_user_id)
        if assigned is None:
            return results  # No assignments found, don't filter

        return [
            r for r in results
            if r.get('metadata', {}).get('nx_lesson_id') in assigned
            or r.get('is_personal', False)  # Always include personal data
        ]

    # ------------------------------------------------------------------
    # Parallel retrieval
    # ------------------------------------------------------------------

    def parallel_retrieve(
        self,
        query: str,
        nx_user_id: int,
        k_shared: int = 4,
        k_personal: int = 2,
    ) -> Tuple[List[Dict], List[Dict]]:
        futures = {}
        futures['shared'] = self.executor.submit(
            self.shared_manager.get_relevant_chunks, query, k_shared
        )

        user_overlay = self.get_user_overlay(nx_user_id)
        futures['personal'] = self.executor.submit(
            user_overlay.search_personal_index, query, k_personal
        )

        shared_results = []
        personal_results = []

        for key, future in futures.items():
            try:
                result = future.result(timeout=5)
                if key == 'shared':
                    shared_results = result
                else:
                    personal_results = result
            except Exception as e:
                logger.error(f"Failed to retrieve from {key}: {e}")

        return shared_results, personal_results

    def merge_and_rerank(
        self,
        shared_results: List[Dict],
        personal_results: List[Dict],
        top_k: int = 5,
    ) -> List[Dict]:
        """Merge results with 1.5x personal boost."""
        all_results = []

        for result in shared_results:
            result['source_type'] = 'shared'
            result['adjusted_score'] = result.get('similarity_score', 0.5)
            all_results.append(result)

        for result in personal_results:
            result['source_type'] = 'personal'
            # 1.5x boost for personal results
            result['adjusted_score'] = result.get('similarity_score', 0.5) * 1.5
            all_results.append(result)

        all_results.sort(key=lambda x: x['adjusted_score'], reverse=True)
        return all_results[:top_k]

    # ------------------------------------------------------------------
    # Context building with EPP awareness
    # ------------------------------------------------------------------

    def build_hybrid_context(
        self,
        merged_results: List[Dict],
        user_overlay: UserOverlay = None,
    ) -> str:
        """Build context combining search results + EPP + onboarding."""
        context_parts = []

        # Inject EPP-aware learner context
        if user_overlay:
            epp_ctx = user_overlay.get_epp_context_string()
            if epp_ctx:
                context_parts.append(f"Learner Profile: {epp_ctx}")

            onboarding_ctx = user_overlay.get_onboarding_context_string()
            if onboarding_ctx:
                context_parts.append(f"Learner Background: {onboarding_ctx}")

            if context_parts:
                context_parts.append("")

        # Add retrieved context
        for i, result in enumerate(merged_results, 1):
            source = result.get('source_type', 'unknown')
            score = result.get('adjusted_score', 0)
            content = result.get('content', '')
            context_parts.append(
                f"Context {i} ({source}, relevance: {score:.2f}):"
            )
            context_parts.append(content[:500])
            context_parts.append("")

        return "\n".join(context_parts)

    # ------------------------------------------------------------------
    # Main query entry point
    # ------------------------------------------------------------------

    def query(
        self,
        query: str,
        nx_user_id: int = None,
        session_id: Optional[str] = None,
        scope: str = SCOPE_COMPANION,
        use_chat_history: bool = True,
        use_opus: bool = False,
        max_tokens: int = 500,
    ) -> Dict[str, Any]:
        """
        Process a query with scope enforcement and EPP context.

        Args:
            scope: 'companion' (assigned only) or 'curator' (all)
            use_opus: Force Opus model for complex queries
        """
        start_time = time.time()

        try:
            if not nx_user_id:
                nx_user_id = self.nx_user_id

            user_data = self.user_manager.authenticate_user(nx_user_id)
            user_overlay = self.get_user_overlay(nx_user_id)

            if not session_id:
                session_id = self.user_manager.create_session(nx_user_id)

            # Parallel retrieval
            shared_results, personal_results = self.parallel_retrieve(
                query, nx_user_id, k_shared=4, k_personal=2
            )

            # Scope enforcement on shared results
            shared_results = self._filter_by_scope(
                shared_results, scope, nx_user_id
            )

            # Merge and rerank
            merged_results = self.merge_and_rerank(
                shared_results, personal_results, top_k=5
            )

            # Build EPP-aware context
            context = self.build_hybrid_context(merged_results, user_overlay)

            # Generate response
            if use_chat_history:
                retriever = self._create_hybrid_retriever(merged_results)
                answer, metadata = self.chat_manager.process_query_with_history(
                    query, session_id, retriever,
                    is_global_chat=(scope == SCOPE_CURATOR),
                    use_opus=use_opus,
                )
            else:
                answer = self._generate_answer(
                    query, context,
                    is_global=(scope == SCOPE_CURATOR),
                    max_tokens=max_tokens,
                    use_opus=use_opus,
                )
                metadata = {}

            response_time = time.time() - start_time

            return {
                'query': query,
                'answer': answer,
                'sources': merged_results,
                'metadata': {
                    **metadata,
                    'nx_user_id': nx_user_id,
                    'session_id': session_id,
                    'scope': scope,
                    'model': OPUS_MODEL if use_opus else SONNET_MODEL,
                    'response_time': response_time,
                    'shared_sources': len(shared_results),
                    'personal_sources': len(personal_results),
                    'epp_context_used': bool(user_overlay.epp_profile),
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                },
            }

        except Exception as e:
            logger.error(f"Failed to process hybrid query: {e}")
            return {
                'query': query,
                'answer': "I encountered an error processing your question. Please try again.",
                'sources': [],
                'metadata': {
                    'error': str(e),
                    'nx_user_id': nx_user_id,
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                },
            }

    def _create_hybrid_retriever(self, merged_results: List[Dict]):
        from pydantic import ConfigDict

        results = merged_results

        class HybridRetriever(BaseRetriever):
            model_config = ConfigDict(arbitrary_types_allowed=True)

            def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
                return [
                    Document(
                        page_content=r['content'],
                        metadata=r.get('metadata', {}),
                    )
                    for r in results
                ]

        return HybridRetriever()

    def _generate_answer(
        self,
        query: str,
        context: str,
        is_global: bool,
        max_tokens: int,
        use_opus: bool = False,
    ) -> str:
        """Generate answer using Anthropic Claude."""
        try:
            if is_global:
                system_prompt = (
                    "You are Tory, a warm and insightful AI learning companion. "
                    "Use the provided context when available. Be encouraging and "
                    "relate answers back to the learner's growth journey."
                )
            else:
                system_prompt = (
                    "You are Tory, a warm and insightful AI learning companion. "
                    "Answer based only on the provided context. If the context "
                    "doesn't contain enough information, say so honestly."
                )

            model = OPUS_MODEL if use_opus else SONNET_MODEL

            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"Context:\n{context}\n\nQuestion: {query}",
                    }
                ],
                timeout=30,
            )

            return response.content[0].text.strip()

        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return "I apologize, but I encountered an error generating a response."

    # ------------------------------------------------------------------
    # User data management
    # ------------------------------------------------------------------

    def add_to_backpack(
        self,
        documents: List[Document],
    ) -> Dict[str, Any]:
        """Add documents to user's personal FAISS index."""
        try:
            nx_user_id = self.nx_user_id
            overlay = self.get_user_overlay(nx_user_id)

            if not overlay.personal_index:
                index = faiss.IndexFlatL2(EMBEDDING_DIMENSIONS)
                overlay.personal_index = FAISS(
                    embedding_function=self.embeddings,
                    index=index,
                    docstore=InMemoryDocstore(),
                    index_to_docstore_id={},
                )

            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]
            overlay.personal_index.add_texts(texts, metadatas=metadatas)
            overlay.save_overlay()

            return {
                'success': True,
                'processed_count': len(documents),
            }
        except Exception as e:
            logger.error(f"Failed to add to backpack: {e}")
            return {'success': False, 'error': str(e)}

    def get_usage_stats(self) -> Dict[str, Any]:
        shared_stats = self.shared_manager.get_stats()
        return {
            'shared_store': shared_stats,
            'active_user_overlays': len(self.user_overlays),
        }
