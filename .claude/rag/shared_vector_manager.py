"""
Shared Vector Store Manager for MyNextory RAG System
Manages a single global FAISS index for lesson content shared across all users.
Singleton pattern, thread-safe, 15-min cache TTL.

Adapted from enhanced-rag-system:
- Index path → .claude/rag/indexes/faiss_global/
- Added lesson_detail_id metadata to FAISS documents
- Compatible with semantic chunks from Content Processor (A.3)
"""

import os
import time
import pickle
import tempfile
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import threading

import structlog
import faiss
import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document
from uuid import uuid4

from config import (
    EMBEDDING_MODEL, EMBEDDING_DIMENSIONS,
    RAG_FAISS_DIR, RAG_BASE_DIR,
)

logger = structlog.get_logger()


class SharedVectorManager:
    """
    Manages the shared global vector store for all lesson content.
    Singleton — one global FAISS index, thread-safe reads.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.vector_store = None
            self.embeddings = None
            self.cache: Dict[str, dict] = {}
            self.cache_ttl = timedelta(minutes=15)
            self.last_update: Optional[datetime] = None
            self.metadata_index: Dict[str, dict] = {}
            self.usage_stats = {
                'queries': 0,
                'cache_hits': 0,
                'cache_misses': 0,
                'last_query': None,
            }
            self._io_lock = threading.RLock()
            self.vector_store_path = RAG_FAISS_DIR
            self.ensure_directories()
            self.load_or_create_store()
            logger.info("Shared Vector Manager initialized (Singleton)")

    def ensure_directories(self):
        os.makedirs(self.vector_store_path, exist_ok=True)

    def load_or_create_store(self):
        try:
            index_path = os.path.join(self.vector_store_path, 'index.faiss')
            if os.path.exists(index_path):
                self.embeddings = OpenAIEmbeddings(
                    model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
                )
                self.vector_store = FAISS.load_local(
                    self.vector_store_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                self.last_update = datetime.now()

                # Load metadata index
                meta_dir = os.path.join(RAG_BASE_DIR, 'shared_knowledge')
                os.makedirs(meta_dir, exist_ok=True)
                meta_path = os.path.join(meta_dir, 'metadata_index.pkl')
                if os.path.exists(meta_path):
                    with open(meta_path, 'rb') as f:
                        self.metadata_index = pickle.load(f)

                logger.info(
                    f"Loaded shared vector store: {self.vector_store.index.ntotal} vectors"
                )
            else:
                self.create_empty_store()
                logger.info("Created new shared vector store")
        except Exception as e:
            logger.error(f"Failed to load shared vector store: {e}")
            self.create_empty_store()

    def create_empty_store(self):
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
        )
        index = faiss.IndexFlatL2(EMBEDDING_DIMENSIONS)
        self.vector_store = FAISS(
            embedding_function=self.embeddings,
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )
        self.last_update = datetime.now()

    def add_documents(
        self,
        documents: List[Document],
        source: str = "global",
    ):
        """
        Add documents to the shared vector store.
        Each document should have metadata including lesson_detail_id.
        Thread-safe with I/O lock.
        """
        if not documents:
            return

        with self._io_lock:
            try:
                uuids = [str(uuid4()) for _ in range(len(documents))]

                for doc in documents:
                    if 'source' not in doc.metadata:
                        doc.metadata['source'] = source
                    doc.metadata['added_at'] = datetime.now().isoformat()
                    doc.metadata['is_shared'] = True

                self.vector_store.add_documents(documents=documents, ids=uuids)

                for uid, doc in zip(uuids, documents):
                    self.metadata_index[uid] = {
                        'source': doc.metadata.get('source'),
                        'lesson_detail_id': doc.metadata.get('lesson_detail_id'),
                        'nx_lesson_id': doc.metadata.get('nx_lesson_id'),
                        'slide_type': doc.metadata.get('slide_type'),
                        'added_at': doc.metadata.get('added_at'),
                        'content_hash': hash(doc.page_content),
                    }

                self.save_store()
                self.clear_cache()
                logger.info(
                    f"Added {len(documents)} documents to shared store from {source}"
                )
            except Exception as e:
                logger.error(f"Failed to add documents to shared store: {e}")

    def save_store(self):
        try:
            self.vector_store.save_local(self.vector_store_path)

            meta_dir = os.path.join(RAG_BASE_DIR, 'shared_knowledge')
            os.makedirs(meta_dir, exist_ok=True)
            meta_path = os.path.join(meta_dir, 'metadata_index.pkl')
            self._atomic_write_pickle(meta_path, self.metadata_index)

            self.last_update = datetime.now()
            logger.info(f"Saved shared vector store to {self.vector_store_path}")
        except Exception as e:
            logger.error(f"Failed to save shared vector store: {e}")

    def _atomic_write_pickle(self, filepath: str, data):
        dir_path = os.path.dirname(filepath) or '.'
        os.makedirs(dir_path, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'wb') as f:
                pickle.dump(data, f)
            os.replace(tmp_path, filepath)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def search(
        self,
        query: str,
        k: int = 4,
        filter_metadata: Optional[Dict] = None,
        use_cache: bool = True,
    ) -> List[Tuple[Document, float]]:
        self.usage_stats['queries'] += 1
        self.usage_stats['last_query'] = datetime.now()

        cache_key = f"{query}_{k}_{str(filter_metadata)}"
        if use_cache and cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if datetime.now() - cache_entry['timestamp'] < self.cache_ttl:
                self.usage_stats['cache_hits'] += 1
                return cache_entry['results']

        self.usage_stats['cache_misses'] += 1

        try:
            if filter_metadata:
                results = self.vector_store.similarity_search_with_score(
                    query=query, k=k, filter=filter_metadata
                )
            else:
                results = self.vector_store.similarity_search_with_score(
                    query=query, k=k
                )

            if use_cache:
                self.cache[cache_key] = {
                    'results': results,
                    'timestamp': datetime.now(),
                }
            return results
        except Exception as e:
            logger.error(f"Failed to search shared vector store: {e}")
            return []

    def get_relevant_chunks(
        self,
        query: str,
        k: int = 4,
        relevance_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        results = self.search(query, k=k)
        relevant_chunks = []
        for doc, score in results:
            similarity = 1.0 / (1.0 + score)
            if similarity >= relevance_threshold:
                relevant_chunks.append({
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'similarity_score': similarity,
                    'source': doc.metadata.get('source', 'shared'),
                    'lesson_detail_id': doc.metadata.get('lesson_detail_id'),
                    'is_shared': True,
                })
        return relevant_chunks

    def clear_cache(self):
        self.cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        cache_size = len(self.cache)
        hit_rate = 0
        if self.usage_stats['queries'] > 0:
            hit_rate = self.usage_stats['cache_hits'] / self.usage_stats['queries']
        return {
            'total_vectors': self.vector_store.index.ntotal if self.vector_store else 0,
            'total_queries': self.usage_stats['queries'],
            'cache_hits': self.usage_stats['cache_hits'],
            'cache_misses': self.usage_stats['cache_misses'],
            'cache_hit_rate': hit_rate,
            'cache_size': cache_size,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'last_query': (
                self.usage_stats['last_query'].isoformat()
                if self.usage_stats['last_query']
                else None
            ),
        }

    def update_from_ingestion(self, new_documents: List[Document]):
        if not new_documents:
            return
        shared_docs = [
            doc for doc in new_documents
            if not doc.metadata.get('user_specific', False)
        ]
        if shared_docs:
            self.add_documents(shared_docs, source="ingestion")
            logger.info(
                f"Updated shared store with {len(shared_docs)} documents from ingestion"
            )

    def cleanup_old_cache(self):
        current_time = datetime.now()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time - entry['timestamp'] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.cache[key]


# Global singleton instance
shared_vector_manager = SharedVectorManager()
