"""
Incremental Ingestion for MyNextory RAG System
Processes lesson_slides table into semantic chunks in FAISS.
Uses bloom filter dedup and incremental update pattern.

Adapted from enhanced-rag-system:
- Input: Azure Blob PDFs → lesson_slides table
- Text extraction: PDF extraction → extract_text_from_slide() (from tag_content.py)
- Keep: bloom filter dedup, incremental update, token-based chunking
- Output: semantic chunks in global FAISS index with lesson_detail_id metadata
"""

import csv
import hashlib
import json
import os
import pickle
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Dict, List, Generator, Optional, Tuple, Any

import faiss
import numpy as np
import structlog
import tiktoken
import xxhash
from bloom_filter2 import BloomFilter
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

# Inline constants to avoid import-path shadowing between
# .claude/rag/config.py and .claude/command-center/backend/config.py.
_rag_dir = os.path.dirname(__file__)
DATABASE = "baap"
DB_QUERY_TIMEOUT = 60
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_PRICE_PER_1K_TOKENS = 0.00002
CHUNK_SIZE_TOKENS = 1000
CHUNK_OVERLAP_TOKENS = 200
BLOOM_FILTER_MAX_ELEMENTS = 1000000
BLOOM_FILTER_ERROR_RATE = 0.1
RAG_BASE_DIR = os.path.join(_rag_dir, "indexes")
RAG_MANIFEST_FILE = os.path.join(RAG_BASE_DIR, "manifest.json")
RAG_BLOOM_FILE = os.path.join(RAG_BASE_DIR, "dedup_bloom.pkl")
RAG_FAISS_DIR = os.path.join(RAG_BASE_DIR, "faiss_global")
RAG_TOKEN_USAGE_FILE = os.path.join(RAG_BASE_DIR, "token_usage.csv")
MAX_DOCUMENTS_TO_PROCESS = None

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# MySQL helper
# ---------------------------------------------------------------------------

def _mysql_query_xml(sql: str) -> list[dict]:
    result = subprocess.run(
        ["mysql", DATABASE, "--xml", "-e", sql],
        capture_output=True, text=True, timeout=DB_QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MySQL error: {result.stderr.strip()}")
    if not result.stdout.strip():
        return []
    root = ET.fromstring(result.stdout)
    rows = []
    for row_el in root.findall("row"):
        row = {}
        for field in row_el.findall("field"):
            name = field.get("name")
            is_null = field.get("{http://www.w3.org/2001/XMLSchema-instance}nil")
            row[name] = None if is_null == "true" else (field.text or "")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Slide text extraction (reused from tag_content.py)
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fix_unicode_escapes(text: str) -> str:
    def replace_unicode(m):
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)
    return re.sub(r'u([0-9a-fA-F]{4})', replace_unicode, text)


def extract_text_from_slide(slide_content: Optional[str]) -> str:
    """Extract readable text from slide_content JSON.
    Identical to tag_content.py::extract_text_from_slide.
    """
    if not slide_content:
        return ""
    content = _fix_unicode_escapes(slide_content)
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return _strip_html(content)

    if not isinstance(data, dict):
        return str(data)

    text_parts = []
    text_fields = [
        "slide_title", "content", "short_description", "greetings",
        "message", "message_1", "message_2", "card_title", "card_content",
        "appreciation", "advisor_content", "note",
    ]
    for field in text_fields:
        val = data.get(field)
        if val and isinstance(val, str):
            text_parts.append(_strip_html(val))

    questions = data.get("questions", [])
    if isinstance(questions, list):
        for q in questions:
            if isinstance(q, str):
                text_parts.append(_strip_html(q))
            elif isinstance(q, dict):
                for k in ("question", "title", "answer"):
                    if k in q and isinstance(q[k], str):
                        text_parts.append(_strip_html(q[k]))

    decisions = data.get("decision", [])
    if isinstance(decisions, list):
        for d in decisions:
            if isinstance(d, dict):
                for k in ("title", "content"):
                    if k in d and isinstance(d[k], str):
                        text_parts.append(_strip_html(d[k]))

    examples = data.get("examples", [])
    if isinstance(examples, list):
        for group in examples:
            if isinstance(group, list):
                for ex in group:
                    if isinstance(ex, str):
                        text_parts.append(_strip_html(ex))

    bulb = data.get("bulbExamples", {})
    if isinstance(bulb, dict):
        for side in bulb.values():
            if isinstance(side, list):
                for ex in side:
                    if isinstance(ex, str):
                        text_parts.append(_strip_html(ex))

    heads_up = data.get("heads_up")
    if heads_up and isinstance(heads_up, str):
        text_parts.append(_strip_html(heads_up))

    return " ".join(text_parts)


# ---------------------------------------------------------------------------
# Lesson content helpers
# ---------------------------------------------------------------------------

def build_lesson_mapping() -> Dict[int, int]:
    """Build lesson_detail_id -> nx_lesson_id mapping."""
    mapping = {}
    rows = _mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id, lesson_detail_id "
        "FROM backpacks WHERE deleted_at IS NULL "
        "AND nx_lesson_id IS NOT NULL AND lesson_detail_id IS NOT NULL"
    )
    for r in rows:
        mapping[int(r["lesson_detail_id"])] = int(r["nx_lesson_id"])

    rows = _mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id, lesson_detail_id "
        "FROM nx_user_ratings WHERE deleted_at IS NULL "
        "AND nx_lesson_id IS NOT NULL AND lesson_detail_id IS NOT NULL"
    )
    for r in rows:
        ld_id = int(r["lesson_detail_id"])
        if ld_id not in mapping:
            mapping[ld_id] = int(r["nx_lesson_id"])
    return mapping


def get_all_lesson_detail_ids() -> List[int]:
    rows = _mysql_query_xml(
        "SELECT DISTINCT lesson_detail_id FROM lesson_slides "
        "WHERE deleted_at IS NULL AND lesson_detail_id IS NOT NULL "
        "ORDER BY lesson_detail_id ASC"
    )
    return [int(r["lesson_detail_id"]) for r in rows]


def get_slides_for_lesson(lesson_detail_id: int) -> List[Dict]:
    """Get all slides for a lesson with their content."""
    rows = _mysql_query_xml(
        f"SELECT id, type, slide_content, priority FROM lesson_slides "
        f"WHERE lesson_detail_id = {int(lesson_detail_id)} "
        f"AND deleted_at IS NULL ORDER BY priority ASC, id ASC"
    )
    return rows


# ---------------------------------------------------------------------------
# Incremental Ingestion Engine
# ---------------------------------------------------------------------------

class IncrementalIngestion:
    """
    Processes lesson_slides into FAISS with bloom filter dedup
    and incremental updates.
    """

    def __init__(self):
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        self.vector_store = None
        self.manifest: Dict[str, Any] = {}
        self.bloom_filter = None

        Path(RAG_BASE_DIR).mkdir(parents=True, exist_ok=True)

        self._load_manifest()
        self._load_bloom_filter()
        self._load_or_create_vector_store()
        logger.info("Incremental ingestion engine initialized")

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _load_manifest(self):
        if os.path.exists(RAG_MANIFEST_FILE):
            with open(RAG_MANIFEST_FILE, 'r') as f:
                self.manifest = json.load(f)
            logger.info(f"Loaded manifest with {len(self.manifest)} lessons")
        else:
            self.manifest = {}

    def _save_manifest(self):
        self._atomic_write_json(RAG_MANIFEST_FILE, self.manifest)

    def _load_bloom_filter(self):
        if os.path.exists(RAG_BLOOM_FILE):
            with open(RAG_BLOOM_FILE, 'rb') as f:
                self.bloom_filter = pickle.load(f)
            logger.info("Loaded bloom filter")
        else:
            self.bloom_filter = BloomFilter(
                max_elements=BLOOM_FILTER_MAX_ELEMENTS,
                error_rate=BLOOM_FILTER_ERROR_RATE,
            )

    def _save_bloom_filter(self):
        self._atomic_write_pickle(RAG_BLOOM_FILE, self.bloom_filter)

    def _load_or_create_vector_store(self):
        index_path = os.path.join(RAG_FAISS_DIR, 'index.faiss')
        if os.path.exists(index_path):
            try:
                embeddings = OpenAIEmbeddings(
                    model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
                )
                self.vector_store = FAISS.load_local(
                    RAG_FAISS_DIR, embeddings,
                    allow_dangerous_deserialization=True,
                )
                logger.info(
                    f"Loaded vector store: {self.vector_store.index.ntotal} vectors"
                )
            except Exception as e:
                logger.warning(f"Failed to load vector store: {e}")
                self._create_new_vector_store()
        else:
            self._create_new_vector_store()

    def _create_new_vector_store(self):
        embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
        )
        index = faiss.IndexFlatL2(EMBEDDING_DIMENSIONS)
        self.vector_store = FAISS(
            embedding_function=embeddings,
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )
        logger.info("Created new FAISS vector store")

    def _save_vector_store(self):
        if self.vector_store is None:
            self._create_new_vector_store()
        self.vector_store.save_local(RAG_FAISS_DIR)
        logger.info(f"Saved vector store: {self.vector_store.index.ntotal} vectors")

    def _atomic_write_json(self, filepath: str, data: dict):
        dir_path = os.path.dirname(filepath) or '.'
        os.makedirs(dir_path, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, filepath)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

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

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def content_hash(self, text: str) -> str:
        return xxhash.xxh64(text.encode('utf-8')).hexdigest()

    def chunk_text_tokens(
        self,
        text: str,
        max_tokens: int = CHUNK_SIZE_TOKENS,
        overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
    ) -> Generator[str, None, None]:
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            yield text
            return
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            yield self.tokenizer.decode(tokens[start:end])
            if end >= len(tokens):
                break
            start = end - overlap_tokens

    # ------------------------------------------------------------------
    # Core: process one lesson
    # ------------------------------------------------------------------

    def process_lesson(
        self,
        lesson_detail_id: int,
        nx_lesson_id: Optional[int] = None,
    ) -> Tuple[int, int, float]:
        """
        Process all slides for one lesson_detail_id into chunks.
        Returns (new_chunks, total_tokens, cost).
        """
        ld_key = str(lesson_detail_id)

        # Get slides from DB
        slides = get_slides_for_lesson(lesson_detail_id)
        if not slides:
            return 0, 0, 0.0

        # Build content hash from all slides to detect changes
        slide_texts = []
        for slide in slides:
            text = extract_text_from_slide(slide.get('slide_content'))
            if text:
                slide_type = slide.get('type', 'unknown')
                slide_texts.append(f"[{slide_type}] {text}")

        if not slide_texts:
            return 0, 0, 0.0

        full_text = "\n".join(slide_texts)
        content_digest = hashlib.md5(full_text.encode()).hexdigest()

        # Check if lesson changed since last processing
        if ld_key in self.manifest:
            if self.manifest[ld_key].get('content_hash') == content_digest:
                return 0, 0, 0.0

        # Chunk the full lesson text
        chunks = list(self.chunk_text_tokens(full_text))
        new_chunks = []
        chunk_hashes = []
        total_tokens = 0

        for chunk in chunks:
            chunk_hash = self.content_hash(chunk)
            chunk_hashes.append(chunk_hash)
            chunk_tokens = len(self.tokenizer.encode(chunk))
            total_tokens += chunk_tokens

            if chunk_hash not in self.bloom_filter:
                new_chunks.append(chunk)
                self.bloom_filter.add(chunk_hash)

        if not new_chunks:
            self.manifest[ld_key] = {
                'content_hash': content_digest,
                'chunk_hashes': chunk_hashes,
                'processed_at': datetime.now().isoformat(),
            }
            return 0, 0, 0.0

        # Create Document objects with lesson metadata
        documents = []
        for i, chunk in enumerate(new_chunks):
            doc = Document(
                page_content=chunk,
                metadata={
                    'source': f'lesson_{lesson_detail_id}',
                    'lesson_detail_id': lesson_detail_id,
                    'nx_lesson_id': nx_lesson_id,
                    'chunk_index': i,
                    'tokens': len(self.tokenizer.encode(chunk)),
                    'processed_at': datetime.now().isoformat(),
                },
            )
            documents.append(doc)

        # Add to vector store
        self.vector_store.add_documents(documents)

        cost = total_tokens * EMBEDDING_PRICE_PER_1K_TOKENS / 1000

        # Update manifest
        self.manifest[ld_key] = {
            'content_hash': content_digest,
            'nx_lesson_id': nx_lesson_id,
            'chunk_hashes': chunk_hashes,
            'new_chunks_added': len(new_chunks),
            'total_tokens': total_tokens,
            'cost': cost,
            'processed_at': datetime.now().isoformat(),
        }

        self._log_token_usage(f'lesson_{lesson_detail_id}', total_tokens, cost)
        return len(new_chunks), total_tokens, cost

    def _log_token_usage(self, document: str, tokens: int, cost: float):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'document': document,
            'tokens': tokens,
            'cost': cost,
            'model': EMBEDDING_MODEL,
        }
        file_exists = os.path.exists(RAG_TOKEN_USAGE_FILE)
        with open(RAG_TOKEN_USAGE_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=log_entry.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(log_entry)

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def process_all_lessons(
        self,
        max_lessons: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process all lessons from lesson_slides table."""
        logger.info("Starting incremental lesson processing")

        stats = {
            'total_lessons': 0,
            'processed_lessons': 0,
            'skipped_lessons': 0,
            'new_chunks': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'start_time': time.time(),
        }

        # Build mapping
        lesson_mapping = build_lesson_mapping()
        all_ld_ids = get_all_lesson_detail_ids()

        limit = max_lessons or MAX_DOCUMENTS_TO_PROCESS
        if limit:
            all_ld_ids = all_ld_ids[:limit]

        stats['total_lessons'] = len(all_ld_ids)
        logger.info(f"Found {len(all_ld_ids)} lessons to process")

        for i, ld_id in enumerate(all_ld_ids, 1):
            nx_lesson_id = lesson_mapping.get(ld_id)

            new_chunks, tokens, cost = self.process_lesson(ld_id, nx_lesson_id)

            if new_chunks > 0:
                stats['processed_lessons'] += 1
                stats['new_chunks'] += new_chunks
                stats['total_tokens'] += tokens
                stats['total_cost'] += cost
                logger.info(
                    f"[{i}/{len(all_ld_ids)}] lesson_detail_id={ld_id}: "
                    f"+{new_chunks} chunks"
                )
            else:
                stats['skipped_lessons'] += 1

        # Save state
        self._save_manifest()
        self._save_bloom_filter()
        self._save_vector_store()

        stats['duration'] = time.time() - stats['start_time']

        logger.info(
            f"Processing complete: {stats['processed_lessons']}/{stats['total_lessons']} "
            f"lessons, {stats['new_chunks']} new chunks, "
            f"${stats['total_cost']:.4f}, {stats['duration']:.1f}s"
        )
        return stats


def main():
    ingestion = IncrementalIngestion()
    stats = ingestion.process_all_lessons()

    print(f"\n{'='*50}")
    print("Incremental Lesson Ingestion Summary")
    print(f"{'='*50}")
    print(f"Lessons processed: {stats['processed_lessons']}")
    print(f"Lessons skipped: {stats['skipped_lessons']}")
    print(f"New chunks: {stats['new_chunks']}")
    print(f"Tokens: {stats['total_tokens']:,}")
    print(f"Cost: ${stats['total_cost']:.4f}")
    print(f"Duration: {stats['duration']:.1f}s")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
