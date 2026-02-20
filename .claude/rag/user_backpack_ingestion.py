"""
User Backpack Ingestion for MyNextory RAG System
Processes per-learner data into personal FAISS overlays:
- Backpack reflections from `backpacks` table (JSON array `data` field)
- EPP scores from `nx_user_onboardings.assesment_result`
- Onboarding Q&A from `nx_user_onboardings` columns

Adapted from enhanced-rag-system:
- Input: PDFs → backpacks table (11,951 rows of learner reflections)
- Added EPP score ingestion into personal overlay
- Added onboarding Q&A ingestion into personal overlay
- Chunk strategy: short texts (~100-500 tokens each), no overlap needed
"""

import json
import os
import pickle
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Generator, Optional

import structlog
import tiktoken
import xxhash
from bloom_filter2 import BloomFilter
from langchain_core.documents import Document

# Inline constants to avoid import-path shadowing between
# .claude/rag/config.py and .claude/command-center/backend/config.py.
DATABASE = "baap"
DB_QUERY_TIMEOUT = 60
USER_OVERLAY_DIR = os.path.join(os.path.dirname(__file__), "indexes", "user_overlays")
EMBEDDING_PRICE_PER_1K_TOKENS = 0.00002

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# MySQL helper (same pattern as tag_content.py)
# ---------------------------------------------------------------------------

def _mysql_query_xml(sql: str) -> list[dict]:
    """Execute query and parse XML output."""
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


class UserBackpackIngestion:
    """
    Per-learner data ingestion: backpack reflections, EPP scores, onboarding Q&A.
    Each user gets isolated bloom filter, manifest, and processing stats.
    """

    def __init__(self, nx_user_id: int, user_hash: str):
        self.nx_user_id = nx_user_id
        self.user_hash = user_hash
        self.user_path = os.path.join(USER_OVERLAY_DIR, user_hash)

        self.tokenizer = tiktoken.encoding_for_model("gpt-4")

        # User-specific state files
        self.manifest_file = os.path.join(self.user_path, 'backpack_manifest.json')
        self.bloom_file = os.path.join(self.user_path, 'backpack_bloom.pkl')
        self.stats_file = os.path.join(self.user_path, 'processing_stats.json')

        self.manifest: Dict[str, Any] = {}
        self.bloom_filter = None
        self.processing_stats = {
            'total_documents': 0,
            'total_chunks': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'duplicate_chunks_avoided': 0,
            'last_processed': None,
            'created_at': datetime.now().isoformat(),
        }

        Path(self.user_path).mkdir(parents=True, exist_ok=True)
        self._load_manifest()
        self._load_bloom_filter()
        self._load_stats()
        logger.info(f"UserBackpackIngestion initialized for nx_user_id={nx_user_id}")

    # ------------------------------------------------------------------
    # State persistence (manifest, bloom, stats)
    # ------------------------------------------------------------------

    def _load_manifest(self):
        if os.path.exists(self.manifest_file):
            try:
                with open(self.manifest_file, 'r') as f:
                    self.manifest = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load manifest: {e}")
                self.manifest = {}

    def _save_manifest(self):
        try:
            self._atomic_write_json(self.manifest_file, self.manifest)
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")

    def _load_bloom_filter(self):
        if os.path.exists(self.bloom_file):
            try:
                with open(self.bloom_file, 'rb') as f:
                    self.bloom_filter = pickle.load(f)
            except Exception:
                self._create_bloom_filter()
        else:
            self._create_bloom_filter()

    def _create_bloom_filter(self):
        self.bloom_filter = BloomFilter(max_elements=10000, error_rate=0.001)

    def _save_bloom_filter(self):
        try:
            self._atomic_write_pickle(self.bloom_file, self.bloom_filter)
        except Exception as e:
            logger.error(f"Failed to save bloom filter: {e}")

    def _load_stats(self):
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    loaded = json.load(f)
                    self.processing_stats.update(loaded)
            except Exception as e:
                logger.error(f"Failed to load stats: {e}")

    def _save_stats(self):
        try:
            self.processing_stats['last_processed'] = datetime.now().isoformat()
            self._atomic_write_json(self.stats_file, self.processing_stats)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

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
    # Hashing & chunking
    # ------------------------------------------------------------------

    def content_hash(self, text: str) -> str:
        return xxhash.xxh64(text.encode('utf-8')).hexdigest()

    def chunk_text_tokens(
        self, text: str, max_tokens: int = 500, overlap_tokens: int = 50,
    ) -> Generator[str, None, None]:
        """Chunk text by token count. Smaller chunks for personal data."""
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            yield text
            return
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            yield self.tokenizer.decode(chunk_tokens).strip()
            if end >= len(tokens):
                break
            start = end - overlap_tokens

    # ------------------------------------------------------------------
    # Backpack ingestion (from `backpacks` table)
    # ------------------------------------------------------------------

    def fetch_backpack_entries(self) -> List[Dict[str, Any]]:
        """Fetch all backpack entries for this user from the DB."""
        sql = (
            f"SELECT id, nx_lesson_id, lesson_detail_id, lesson_slide_id, "
            f"form_type, data, created_at "
            f"FROM backpacks "
            f"WHERE created_by = {int(self.nx_user_id)} "
            f"AND user_type = 'User' "
            f"AND deleted_at IS NULL "
            f"ORDER BY created_at ASC"
        )
        return _mysql_query_xml(sql)

    def ingest_backpacks(self) -> List[Document]:
        """
        Ingest backpack reflections into Document objects for FAISS embedding.
        The `data` field is a JSON array of answers.
        """
        entries = self.fetch_backpack_entries()
        if not entries:
            logger.info(f"No backpack entries for nx_user_id={self.nx_user_id}")
            return []

        documents = []
        new_chunks = 0
        duplicate_chunks = 0
        total_tokens = 0

        for entry in entries:
            raw_data = entry.get('data')
            if not raw_data:
                continue

            # Parse JSON array of answers
            try:
                answers = json.loads(raw_data)
                if not isinstance(answers, list):
                    answers = [str(answers)]
            except (json.JSONDecodeError, TypeError):
                answers = [str(raw_data)]

            # Build text from all answers
            text_parts = [a.strip() for a in answers if a and str(a).strip()]
            if not text_parts:
                continue

            full_text = " | ".join(text_parts)

            # Chunk (backpack entries are short, usually 1 chunk)
            for chunk in self.chunk_text_tokens(full_text, max_tokens=500):
                chunk_hash = self.content_hash(chunk)
                chunk_tokens = len(self.tokenizer.encode(chunk))
                total_tokens += chunk_tokens

                if chunk_hash not in self.bloom_filter:
                    self.bloom_filter.add(chunk_hash)
                    new_chunks += 1

                    doc = Document(
                        page_content=chunk,
                        metadata={
                            'source': 'backpack',
                            'nx_user_id': self.nx_user_id,
                            'backpack_id': int(entry.get('id', 0)),
                            'nx_lesson_id': entry.get('nx_lesson_id'),
                            'lesson_detail_id': entry.get('lesson_detail_id'),
                            'lesson_slide_id': entry.get('lesson_slide_id'),
                            'form_type': entry.get('form_type', ''),
                            'created_at': entry.get('created_at', ''),
                            'chunk_hash': chunk_hash,
                        },
                    )
                    documents.append(doc)
                else:
                    duplicate_chunks += 1

        # Update stats
        self.processing_stats['total_chunks'] += new_chunks
        self.processing_stats['total_tokens'] += total_tokens
        self.processing_stats['duplicate_chunks_avoided'] += duplicate_chunks
        cost = (total_tokens / 1000) * EMBEDDING_PRICE_PER_1K_TOKENS
        self.processing_stats['total_cost'] += cost

        self._save_manifest()
        self._save_bloom_filter()
        self._save_stats()

        logger.info(
            f"Backpack ingestion: {new_chunks} new, {duplicate_chunks} dupes, "
            f"{len(entries)} entries for nx_user_id={self.nx_user_id}"
        )
        return documents

    # ------------------------------------------------------------------
    # EPP ingestion (from `nx_user_onboardings.assesment_result`)
    # ------------------------------------------------------------------

    def fetch_epp_scores(self) -> Optional[Dict[str, Any]]:
        """Fetch raw EPP scores from the assessment result JSON."""
        sql = (
            f"SELECT assesment_result FROM nx_user_onboardings "
            f"WHERE nx_user_id = {int(self.nx_user_id)} "
            f"AND assesment_result IS NOT NULL "
            f"AND deleted_at IS NULL "
            f"ORDER BY updated_at DESC LIMIT 1"
        )
        rows = _mysql_query_xml(sql)
        if not rows or not rows[0].get('assesment_result'):
            return None

        try:
            return json.loads(rows[0]['assesment_result'])
        except (json.JSONDecodeError, TypeError):
            return None

    def ingest_epp(self) -> Dict[str, Any]:
        """
        Parse EPP scores and return structured profile for the overlay.
        Returns dict with scores, strengths, gaps — NOT Documents (EPP is
        structured data used as context, not embedded in FAISS).
        """
        raw = self.fetch_epp_scores()
        if not raw:
            return {}

        scores_raw = raw.get('scores', {})
        if not scores_raw:
            return {}

        # Extract personality scores (EPP-prefixed keys)
        personality = {}
        jobfit = {}
        for key, value in scores_raw.items():
            if value is None or isinstance(value, bool):
                continue
            try:
                score = float(value)
            except (ValueError, TypeError):
                continue

            if key.startswith('EPP'):
                clean_key = key.replace('EPP', '')
                if clean_key in ('PercentMatch', 'Inconsistency', 'Invalid'):
                    continue
                personality[clean_key] = score
            elif key in (
                'Accounting', 'AdminAsst', 'Analyst', 'BankTeller',
                'Collections', 'CustomerService', 'FrontDesk', 'Manager',
                'MedicalAsst', 'Production', 'Programmer', 'Sales',
            ):
                jobfit[key] = score

        # Identify strengths (>70) and gaps (<30)
        all_scores = {**personality, **{f"{k}_JobFit": v for k, v in jobfit.items()}}
        strengths = [
            {'trait': k, 'score': v, 'type': 'strength'}
            for k, v in sorted(all_scores.items(), key=lambda x: -x[1])
            if v > 70
        ]
        gaps = [
            {'trait': k, 'score': v, 'type': 'gap'}
            for k, v in sorted(all_scores.items(), key=lambda x: x[1])
            if v < 30
        ]

        epp_profile = {
            'personality_scores': personality,
            'jobfit_scores': jobfit,
            'strengths': strengths,
            'gaps': gaps,
            'source': 'criteria_corp_epp',
            'processed_at': datetime.now().isoformat(),
        }

        logger.info(
            f"EPP ingestion: {len(personality)} personality, {len(jobfit)} jobfit "
            f"scores for nx_user_id={self.nx_user_id}"
        )
        return epp_profile

    # ------------------------------------------------------------------
    # Onboarding Q&A ingestion (from `nx_user_onboardings` columns)
    # ------------------------------------------------------------------

    def fetch_onboarding_qa(self) -> Dict[str, Any]:
        """Fetch onboarding Q&A answers from the onboarding record."""
        sql = (
            f"SELECT why_did_you_come, own_reason, call_yourself, "
            f"advance_your_career, imp_thing_career_plan, best_boss, "
            f"success_look_like, in_first_professional_job, stay_longer, "
            f"future_months "
            f"FROM nx_user_onboardings "
            f"WHERE nx_user_id = {int(self.nx_user_id)} "
            f"AND deleted_at IS NULL "
            f"ORDER BY updated_at DESC LIMIT 1"
        )
        rows = _mysql_query_xml(sql)
        if not rows:
            return {}
        return rows[0]

    def ingest_onboarding_qa(self) -> Dict[str, Any]:
        """
        Parse onboarding Q&A into structured data for the overlay.
        Some fields are JSON arrays, some are plain text.
        """
        raw = self.fetch_onboarding_qa()
        if not raw:
            return {}

        qa_data = {}
        question_map = {
            'why_did_you_come': 'Why did you join MyNextory?',
            'own_reason': 'What is your own reason for being here?',
            'call_yourself': 'How would you describe your experience level?',
            'advance_your_career': 'How motivated are you to advance?',
            'imp_thing_career_plan': 'What matters most in your career plan?',
            'best_boss': 'What did your best boss do?',
            'success_look_like': 'What does success look like for you?',
            'in_first_professional_job': 'Is this your first professional job?',
            'stay_longer': 'Do you plan to stay at your company?',
            'future_months': 'How many months into the future are you planning?',
        }

        for field, question in question_map.items():
            value = raw.get(field)
            if not value:
                continue

            # Try to parse as JSON array (some fields are stored that way)
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    answer = ", ".join(str(item) for item in parsed)
                else:
                    answer = str(parsed)
            except (json.JSONDecodeError, TypeError):
                answer = str(value)

            if answer.strip():
                qa_data[field] = {
                    'question': question,
                    'answer': answer.strip(),
                }

        logger.info(
            f"Onboarding QA ingestion: {len(qa_data)} answers "
            f"for nx_user_id={self.nx_user_id}"
        )
        return qa_data

    # ------------------------------------------------------------------
    # Full ingestion pipeline
    # ------------------------------------------------------------------

    def ingest_all(self) -> Dict[str, Any]:
        """
        Run complete ingestion for one user: backpacks, EPP, onboarding Q&A.
        Returns {backpack_docs: [...], epp_profile: {...}, onboarding_qa: {...}}.
        """
        start_time = time.time()

        backpack_docs = self.ingest_backpacks()
        epp_profile = self.ingest_epp()
        onboarding_qa = self.ingest_onboarding_qa()

        duration = time.time() - start_time
        logger.info(
            f"Full ingestion for nx_user_id={self.nx_user_id}: "
            f"{len(backpack_docs)} backpack docs, "
            f"EPP={'yes' if epp_profile else 'no'}, "
            f"QA={len(onboarding_qa)} answers, "
            f"in {duration:.1f}s"
        )

        return {
            'backpack_docs': backpack_docs,
            'epp_profile': epp_profile,
            'onboarding_qa': onboarding_qa,
            'stats': self.get_processing_stats(),
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_processing_stats(self) -> Dict[str, Any]:
        return {
            **self.processing_stats,
            'manifest_count': len(self.manifest),
            'bloom_filter_loaded': self.bloom_filter is not None,
        }

    def get_manifest(self) -> Dict[str, Any]:
        return self.manifest.copy()

    def reset_deduplication(self):
        self._create_bloom_filter()
        self.manifest = {}
        self.processing_stats['duplicate_chunks_avoided'] = 0
        self._save_manifest()
        self._save_bloom_filter()
        self._save_stats()
        logger.info(f"Reset deduplication for nx_user_id={self.nx_user_id}")

    def cleanup_user_data(self):
        try:
            for file_path in [self.manifest_file, self.bloom_file, self.stats_file]:
                if os.path.exists(file_path):
                    os.remove(file_path)
            logger.info(f"Cleaned up processing data for nx_user_id={self.nx_user_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup user data: {e}")
