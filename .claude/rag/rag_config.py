"""
MyNextory Enhanced RAG System Configuration
Adapted from enhanced-rag-system for the MyNextory coaching platform.

Key changes from original:
- LLM: GPT-4o-mini → Claude Sonnet (default) / Opus (on demand)
- Embeddings: text-embedding-3-small kept (uses OPENAI_API_KEY)
- Storage: Azure blob paths → local .claude/rag/indexes/
- Added: MyNextory DB settings, EPP dimensions, model tier config
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# API Keys (auto-loaded from .env by spawn.sh)
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# ---------------------------------------------------------------------------
# LLM Configuration — Claude models replace GPT-4o-mini
# ---------------------------------------------------------------------------
# Default model for most queries (cost-effective)
SONNET_MODEL = "claude-sonnet-4-20250514"
# Premium model for complex reasoning, coaching insights
OPUS_MODEL = "claude-opus-4-20250514"
# Which model to use by default
LLM_MODEL = SONNET_MODEL
# Tier routing: escalate to Opus when complexity score exceeds this
TIER_THRESHOLD = 0.7

# ---------------------------------------------------------------------------
# Embedding Configuration — OpenAI kept (best cost/quality ratio)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "text-embedding-3-small"  # $0.02/1M tokens
EMBEDDING_DIMENSIONS = 1536

# ---------------------------------------------------------------------------
# Cost Tracking
# ---------------------------------------------------------------------------
EMBEDDING_PRICE_PER_1K_TOKENS = 0.00002   # text-embedding-3-small
SONNET_INPUT_PRICE_PER_1K = 0.003          # Claude Sonnet input
SONNET_OUTPUT_PRICE_PER_1K = 0.015         # Claude Sonnet output
OPUS_INPUT_PRICE_PER_1K = 0.015            # Claude Opus input
OPUS_OUTPUT_PRICE_PER_1K = 0.075           # Claude Opus output

# ---------------------------------------------------------------------------
# Storage Configuration — local paths under .claude/rag/
# ---------------------------------------------------------------------------
# Base directory for all RAG storage (relative to project root)
RAG_BASE_DIR = os.path.join(os.path.dirname(__file__), 'indexes')
RAG_MANIFEST_FILE = os.path.join(RAG_BASE_DIR, 'manifest.json')
RAG_BLOOM_FILE = os.path.join(RAG_BASE_DIR, 'dedup_bloom.pkl')
RAG_FAISS_DIR = os.path.join(RAG_BASE_DIR, 'faiss_global')
RAG_FAISS_INDEX_PATH = os.path.join(RAG_FAISS_DIR, 'index.faiss')
RAG_TOKEN_USAGE_FILE = os.path.join(RAG_BASE_DIR, 'token_usage.csv')

# User overlay storage
USER_OVERLAY_DIR = os.path.join(RAG_BASE_DIR, 'user_overlays')

# Legacy aliases (some modules still reference these)
ENHANCED_BASE_DIR = RAG_BASE_DIR
ENHANCED_MANIFEST_FILE = RAG_MANIFEST_FILE
ENHANCED_BLOOM_FILE = RAG_BLOOM_FILE
ENHANCED_FAISS_DIR = RAG_FAISS_DIR
ENHANCED_FAISS_INDEX_PATH = RAG_FAISS_INDEX_PATH
ENHANCED_TOKEN_USAGE_FILE = RAG_TOKEN_USAGE_FILE
USER_STORAGE_DIR = USER_OVERLAY_DIR

# ---------------------------------------------------------------------------
# Text Chunking Configuration
# ---------------------------------------------------------------------------
CHUNK_SIZE_TOKENS = 1000           # Maximum tokens per chunk
CHUNK_OVERLAP_TOKENS = 200         # Overlap between chunks
CHUNK_SIZE_CHARS = 4000            # Character-based chunking fallback
CHUNK_OVERLAP_CHARS = 400          # Character overlap

# ---------------------------------------------------------------------------
# Deduplication (Bloom Filter)
# ---------------------------------------------------------------------------
BLOOM_FILTER_MAX_ELEMENTS = 1000000
BLOOM_FILTER_ERROR_RATE = 0.1

# ---------------------------------------------------------------------------
# Batch Processing
# ---------------------------------------------------------------------------
BATCH_SIZE = 50
EMBEDDING_BATCH_SIZE = 100

# ---------------------------------------------------------------------------
# FAISS Configuration
# ---------------------------------------------------------------------------
FAISS_INDEX_TYPE = 'flat'
FAISS_NLIST = 4096
FAISS_M = 64

# ---------------------------------------------------------------------------
# Query Configuration
# ---------------------------------------------------------------------------
DEFAULT_TOP_K = 4
DEFAULT_MAX_TOKENS = 500
SIMILARITY_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# MyNextory Database Configuration
# ---------------------------------------------------------------------------
DATABASE = "baap"
DB_QUERY_TIMEOUT = 60

# ---------------------------------------------------------------------------
# EPP (Employee Personality Profile) Dimensions
# ---------------------------------------------------------------------------
EPP_PERSONALITY_DIMS = [
    "Achievement", "Motivation", "Competitiveness", "Managerial",
    "Assertiveness", "Extroversion", "Cooperativeness", "Patience",
    "SelfConfidence", "Conscientiousness", "Openness", "Stability",
    "StressTolerance",
]

EPP_JOBFIT_DIMS = [
    "Accounting", "AdminAsst", "Analyst", "BankTeller", "Collections",
    "CustomerService", "FrontDesk", "Manager", "MedicalAsst",
    "Production", "Programmer", "Sales",
]

ALL_EPP_DIMS = EPP_PERSONALITY_DIMS + EPP_JOBFIT_DIMS

# ---------------------------------------------------------------------------
# Three-Tier Memory Configuration (for chat_manager)
# ---------------------------------------------------------------------------
MEMORY_BUFFER_SIZE = 10        # Recent messages kept verbatim
MEMORY_SUMMARY_THRESHOLD = 50  # After this many messages, summarize older ones
MEMORY_KEY_FACTS_MAX = 100     # Permanent key facts extracted from conversation

# ---------------------------------------------------------------------------
# Session & User Management
# ---------------------------------------------------------------------------
SESSION_TIMEOUT_HOURS = 24
MAX_SESSIONS_PER_USER = 5
MAX_USER_OVERLAYS = 100        # LRU cache size for user overlays in memory

# ---------------------------------------------------------------------------
# Token Budgets
# ---------------------------------------------------------------------------
MAX_TOTAL_TOKENS = 1000000     # Maximum tokens per session
MAX_CONTEXT_TOKENS = 8000      # Maximum context window for queries

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ---------------------------------------------------------------------------
# Processing Limits
# ---------------------------------------------------------------------------
MAX_DOCUMENTS_TO_PROCESS = None  # None = all docs
PROCESSING_TIMEOUT_SECONDS = 3600

# ---------------------------------------------------------------------------
# HeyGen Avatar Configuration (Phase D — not active yet)
# ---------------------------------------------------------------------------
HEYGEN_API_KEY = os.getenv('HAY_GEN_API')
AVATAR_ID = os.getenv('AVATAR_ID')
AUDIO_ID = os.getenv('AUDIO_ID')
HEYGEN_BASE_URL = 'https://api.heygen.com/v1'

# ---------------------------------------------------------------------------
# Create directories on import
# ---------------------------------------------------------------------------
os.makedirs(RAG_BASE_DIR, exist_ok=True)
os.makedirs(RAG_FAISS_DIR, exist_ok=True)
os.makedirs(USER_OVERLAY_DIR, exist_ok=True)
