"""
Optimized User Management for MyNextory RAG System
Lightweight overlays per user identified by nx_user_id.
MD5 hash directories, LRU cache, thread-safe.

Adapted from enhanced-rag-system:
- User ID: email → nx_user_id (integer from nx_users table)
- Added overlay components: backpack, epp, onboarding, path_status
- Storage: user_storage/ → .claude/rag/indexes/user_overlays/
"""

import os
import json
import hashlib
import tempfile
import threading
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from pathlib import Path
import structlog

try:
    from filelock import FileLock
    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False

from config import USER_OVERLAY_DIR

logger = structlog.get_logger()


class OptimizedUserManager:
    """
    Manages user authentication and lightweight user-specific data overlays.
    Users identified by nx_user_id (integer).
    """

    def __init__(self):
        self.users_index: Dict[str, dict] = {}  # str(nx_user_id) → metadata
        self.sessions: Dict[str, dict] = {}
        self.overlay_cache: Dict[str, dict] = {}
        self.max_cache_size = 1000

        self._index_lock = threading.RLock()
        self._cache_lock = threading.RLock()

        self.base_dir = USER_OVERLAY_DIR
        self.index_file = os.path.join(USER_OVERLAY_DIR, 'users_index.json')
        self.index_lock_file = os.path.join(USER_OVERLAY_DIR, 'users_index.json.lock')

        self._ensure_directories()
        self._load_users_index()
        logger.info("Optimized User Manager initialized")

    def _ensure_directories(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def _load_users_index(self):
        if os.path.exists(self.index_file):
            try:
                if HAS_FILELOCK:
                    lock = FileLock(self.index_lock_file, timeout=10)
                    with lock:
                        with open(self.index_file, 'r') as f:
                            self.users_index = json.load(f)
                else:
                    with self._index_lock:
                        with open(self.index_file, 'r') as f:
                            self.users_index = json.load(f)
                logger.info(f"Loaded {len(self.users_index)} users from index")
            except Exception as e:
                logger.error(f"Failed to load users index: {e}")
                self.users_index = {}

    def _save_users_index(self):
        try:
            if HAS_FILELOCK:
                lock = FileLock(self.index_lock_file, timeout=10)
                with lock:
                    self._atomic_write_json(self.index_file, self.users_index)
            else:
                with self._index_lock:
                    self._atomic_write_json(self.index_file, self.users_index)
        except Exception as e:
            logger.error(f"Failed to save users index: {e}")

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

    def _get_user_hash(self, nx_user_id: int) -> str:
        """Generate a consistent hash for user directory naming."""
        return hashlib.md5(str(nx_user_id).encode()).hexdigest()[:16]

    def _get_user_dir(self, nx_user_id: int) -> str:
        user_hash = self._get_user_hash(nx_user_id)
        return os.path.join(self.base_dir, user_hash)

    def authenticate_user(self, nx_user_id: int) -> Dict[str, Any]:
        """
        Authenticate user by nx_user_id and create lightweight overlay if needed.
        Returns user metadata.
        """
        user_key = str(nx_user_id)

        if user_key not in self.users_index:
            user_hash = self._get_user_hash(nx_user_id)
            self.users_index[user_key] = {
                'nx_user_id': nx_user_id,
                'user_hash': user_hash,
                'created_at': datetime.now().isoformat(),
                'last_login': datetime.now().isoformat(),
                'storage_size_kb': 0,
            }

            user_dir = self._get_user_dir(nx_user_id)
            os.makedirs(user_dir, exist_ok=True)
            self._initialize_user_overlay(nx_user_id)
            self._save_users_index()
            logger.info(f"Created overlay for nx_user_id={nx_user_id}")
        else:
            self.users_index[user_key]['last_login'] = datetime.now().isoformat()
            self._save_users_index()

        return self.users_index[user_key]

    def _initialize_user_overlay(self, nx_user_id: int):
        """Initialize minimal user overlay with MyNextory components."""
        user_dir = self._get_user_dir(nx_user_id)

        metadata = {
            'nx_user_id': nx_user_id,
            'created_at': datetime.now().isoformat(),
            'version': '2.0',
        }
        with open(os.path.join(user_dir, 'metadata.json'), 'w') as f:
            json.dump(metadata, f, indent=2)

        # Overlay components specific to MyNextory
        for component_file, default_value in [
            ('profile.json', []),         # Basic profile data
            ('preferences.json', {}),      # User preferences
            ('backpack_meta.json', {'count': 0, 'last_updated': None}),
            ('epp_profile.json', {}),      # EPP scores and interpretation
            ('onboarding_qa.json', {}),    # Onboarding Q&A answers
            ('path_status.json', {}),      # Current learning path status
        ]:
            filepath = os.path.join(user_dir, component_file)
            with open(filepath, 'w') as f:
                json.dump(default_value, f, indent=2)

    def get_user_overlay(self, nx_user_id: int) -> Dict[str, Any]:
        """
        Get user overlay data (cached for performance).
        Includes all MyNextory overlay components.
        """
        user_key = str(nx_user_id)

        with self._cache_lock:
            if user_key in self.overlay_cache:
                return self.overlay_cache[user_key]

        user_dir = self._get_user_dir(nx_user_id)
        overlay = {
            'nx_user_id': nx_user_id,
            'profile': [],
            'preferences': {},
            'backpack_count': 0,
            'epp_profile': {},
            'onboarding_qa': {},
            'path_status': {},
            'assessment_summary': None,
        }

        try:
            component_files = {
                'profile': ('profile.json', []),
                'preferences': ('preferences.json', {}),
                'epp_profile': ('epp_profile.json', {}),
                'onboarding_qa': ('onboarding_qa.json', {}),
                'path_status': ('path_status.json', {}),
                'assessment_summary': ('assessment_summary.json', None),
            }

            for key, (filename, default) in component_files.items():
                filepath = os.path.join(user_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        overlay[key] = json.load(f)
                else:
                    overlay[key] = default

            # Backpack metadata
            backpack_file = os.path.join(user_dir, 'backpack_meta.json')
            if os.path.exists(backpack_file):
                with open(backpack_file, 'r') as f:
                    backpack_meta = json.load(f)
                    overlay['backpack_count'] = backpack_meta.get('count', 0)

            with self._cache_lock:
                if len(self.overlay_cache) < self.max_cache_size:
                    self.overlay_cache[user_key] = overlay
                else:
                    if self.overlay_cache:
                        self.overlay_cache.pop(next(iter(self.overlay_cache)))
                    self.overlay_cache[user_key] = overlay

            return overlay
        except Exception as e:
            logger.error(f"Failed to load overlay for nx_user_id={nx_user_id}: {e}")
            return overlay

    def update_user_profile(self, nx_user_id: int, profile_data: List[Dict]) -> bool:
        try:
            user_dir = self._get_user_dir(nx_user_id)
            lightweight_profile = []
            for item in profile_data:
                if isinstance(item, dict):
                    lightweight_profile.append({
                        'question': item.get('question', '')[:100],
                        'answer': item.get('answer', '')[:200],
                        'category': item.get('category', 'general'),
                    })

            with open(os.path.join(user_dir, 'profile.json'), 'w') as f:
                json.dump(lightweight_profile, f, indent=2)

            user_key = str(nx_user_id)
            if user_key in self.overlay_cache:
                self.overlay_cache[user_key]['profile'] = lightweight_profile
            return True
        except Exception as e:
            logger.error(f"Failed to update profile for nx_user_id={nx_user_id}: {e}")
            return False

    def update_epp_profile(self, nx_user_id: int, epp_data: Dict) -> bool:
        """Store parsed EPP profile (scores, strengths, gaps)."""
        try:
            user_dir = self._get_user_dir(nx_user_id)
            with open(os.path.join(user_dir, 'epp_profile.json'), 'w') as f:
                json.dump(epp_data, f, indent=2)

            user_key = str(nx_user_id)
            if user_key in self.overlay_cache:
                self.overlay_cache[user_key]['epp_profile'] = epp_data
            return True
        except Exception as e:
            logger.error(f"Failed to update EPP for nx_user_id={nx_user_id}: {e}")
            return False

    def update_onboarding_qa(self, nx_user_id: int, qa_data: Dict) -> bool:
        """Store onboarding Q&A answers."""
        try:
            user_dir = self._get_user_dir(nx_user_id)
            with open(os.path.join(user_dir, 'onboarding_qa.json'), 'w') as f:
                json.dump(qa_data, f, indent=2)

            user_key = str(nx_user_id)
            if user_key in self.overlay_cache:
                self.overlay_cache[user_key]['onboarding_qa'] = qa_data
            return True
        except Exception as e:
            logger.error(f"Failed to update onboarding QA for nx_user_id={nx_user_id}: {e}")
            return False

    def update_path_status(self, nx_user_id: int, path_data: Dict) -> bool:
        """Store current learning path status."""
        try:
            user_dir = self._get_user_dir(nx_user_id)
            with open(os.path.join(user_dir, 'path_status.json'), 'w') as f:
                json.dump(path_data, f, indent=2)

            user_key = str(nx_user_id)
            if user_key in self.overlay_cache:
                self.overlay_cache[user_key]['path_status'] = path_data
            return True
        except Exception as e:
            logger.error(f"Failed to update path status for nx_user_id={nx_user_id}: {e}")
            return False

    def update_user_backpack(self, nx_user_id: int, backpack_data: List[Dict]) -> bool:
        try:
            user_dir = self._get_user_dir(nx_user_id)
            backpack_meta = {
                'count': len(backpack_data),
                'last_updated': datetime.now().isoformat(),
            }
            with open(os.path.join(user_dir, 'backpack_meta.json'), 'w') as f:
                json.dump(backpack_meta, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to update backpack for nx_user_id={nx_user_id}: {e}")
            return False

    def create_session(
        self, nx_user_id: int, session_id: Optional[str] = None
    ) -> str:
        if not session_id:
            session_id = hashlib.sha256(
                f"{nx_user_id}{datetime.now().isoformat()}".encode()
            ).hexdigest()[:32]

        self.sessions[session_id] = {
            'nx_user_id': nx_user_id,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        if session_id in self.sessions:
            self.sessions[session_id]['last_activity'] = datetime.now().isoformat()
            return self.sessions[session_id]
        return None

    def _update_storage_size(self, nx_user_id: int):
        try:
            user_dir = self._get_user_dir(nx_user_id)
            total_size = 0
            for root, dirs, files in os.walk(user_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    total_size += os.path.getsize(filepath)

            user_key = str(nx_user_id)
            if user_key in self.users_index:
                self.users_index[user_key]['storage_size_kb'] = total_size / 1024
                self._save_users_index()
        except Exception as e:
            logger.error(f"Failed to update storage size for nx_user_id={nx_user_id}: {e}")

    def get_storage_stats(self) -> Dict[str, Any]:
        total_users = len(self.users_index)
        total_storage_kb = sum(
            user.get('storage_size_kb', 0)
            for user in self.users_index.values()
        )
        return {
            'total_users': total_users,
            'total_storage_mb': total_storage_kb / 1024,
            'avg_storage_per_user_kb': total_storage_kb / max(total_users, 1),
            'cached_overlays': len(self.overlay_cache),
            'active_sessions': len(self.sessions),
        }

    def clear_user_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
