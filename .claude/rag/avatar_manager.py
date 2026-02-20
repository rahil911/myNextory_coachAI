"""
Avatar Manager Module for Enhanced RAG System
Handles HeyGen avatar streaming and interaction
"""

import os
import re
import json
import requests
from typing import Dict, Optional, Any
import structlog

# Inline constants to avoid import-path shadowing between
# .claude/rag/config.py and .claude/command-center/backend/config.py.
HEYGEN_API_KEY = os.getenv("HAY_GEN_API")
AVATAR_ID = os.getenv("AVATAR_ID")
AUDIO_ID = os.getenv("AUDIO_ID")
HEYGEN_BASE_URL = "https://api.heygen.com/v1"

logger = structlog.get_logger()

class AvatarManager:
    """
    Manages HeyGen avatar sessions and streaming
    """
    
    def __init__(self):
        self.api_key = HEYGEN_API_KEY
        self.avatar_id = AVATAR_ID
        self.audio_id = AUDIO_ID
        self.base_url = HEYGEN_BASE_URL
        self.sessions = {}
        
        if not self.api_key:
            logger.warning("HeyGen API key not configured")
            
    def _get_headers(self) -> Dict[str, str]:
        """Get API headers for HeyGen requests"""
        return {
            "accept": "application/json",
            "X-Api-Key": self.api_key
        }
        
    def create_session(self, user_email: str, user_data: Dict = None) -> Dict[str, Any]:
        """
        Create a new HeyGen avatar streaming session
        
        Args:
            user_email: User's email address
            user_data: Optional user profile data
            
        Returns:
            Session creation response from HeyGen API
        """
        if not self.api_key:
            return {
                'status': False,
                'message': 'HeyGen API not configured',
                'code': -1
            }
            
        headers = self._get_headers()
        
        payload = {
            "quality": "medium",
            "avatar_id": self.avatar_id,
            "emotion": "Friendly",
            "voice": {
                "voice_id": self.audio_id,
                "emotion": "Friendly",
                "rate": 1
            },
            "disable_idle_timeout": False
        }
        
        try:
            url = f"{self.base_url}/streaming.new"
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()
            
            # Check for rate limiting or errors
            if response_data.get("code") == 10015:
                response_data['status'] = False
                response_data['message'] = 'Rate limit exceeded or API error'
            else:
                response_data['status'] = True
                # Store session info
                if 'session_id' in response_data:
                    self.sessions[response_data['session_id']] = {
                        'user_email': user_email,
                        'created_at': response_data.get('created_at'),
                        'user_data': user_data
                    }
                    
            logger.info(f"Avatar session created for user: {user_email}")
            return response_data
            
        except Exception as e:
            logger.error(f"Failed to create avatar session: {e}")
            return {
                'status': False,
                'message': str(e),
                'code': -1
            }
            
    def start_session(self, session_data: Dict) -> Dict[str, Any]:
        """
        Start the avatar streaming session with ICE candidates
        
        Args:
            session_data: Session data including session_id and sdp
            
        Returns:
            Start session response from HeyGen API
        """
        if not self.api_key:
            return {
                'status': False,
                'message': 'HeyGen API not configured'
            }
            
        headers = self._get_headers()
        
        try:
            url = f"{self.base_url}/streaming.start"
            response = requests.post(url, json=session_data, headers=headers)
            response_data = response.json()
            
            logger.info(f"Avatar session started: {session_data.get('session_id')}")
            return response_data
            
        except Exception as e:
            logger.error(f"Failed to start avatar session: {e}")
            return {
                'status': False,
                'message': str(e)
            }
            
    def handle_ice(self, ice_data: Dict) -> Dict[str, Any]:
        """
        Submit ICE information for WebRTC connection
        
        Args:
            ice_data: ICE candidate data
            
        Returns:
            ICE handling response from HeyGen API
        """
        if not self.api_key:
            return {
                'status': False,
                'message': 'HeyGen API not configured'
            }
            
        headers = self._get_headers()
        
        try:
            url = f"{self.base_url}/streaming.ice"
            response = requests.post(url, json=ice_data, headers=headers)
            response_data = response.json()
            
            logger.debug(f"ICE candidate handled for session: {ice_data.get('session_id')}")
            return response_data
            
        except Exception as e:
            logger.error(f"Failed to handle ICE: {e}")
            return {
                'status': False,
                'message': str(e)
            }
            
    def send_task(self, task_data: Dict) -> Dict[str, Any]:
        """
        Send text task to avatar for speech synthesis
        
        Args:
            task_data: Task data including session_id and text
            
        Returns:
            Task response from HeyGen API
        """
        if not self.api_key:
            return {
                'status': False,
                'message': 'HeyGen API not configured'
            }
            
        # Remove HTML tags from text
        if 'text' in task_data:
            clean_text = self._strip_html_tags(task_data['text'])
            task_data['text'] = clean_text
            
        headers = self._get_headers()
        
        try:
            url = f"{self.base_url}/streaming.task"
            response = requests.post(url, json=task_data, headers=headers)
            response_data = response.json()
            
            logger.info(f"Task sent to avatar session: {task_data.get('session_id')}")
            return response_data
            
        except Exception as e:
            logger.error(f"Failed to send task: {e}")
            return {
                'status': False,
                'message': str(e)
            }
            
    def stop_session(self, session_data: Dict) -> Dict[str, Any]:
        """
        Stop and close avatar streaming session
        
        Args:
            session_data: Session data including session_id
            
        Returns:
            Stop session response from HeyGen API
        """
        if not self.api_key:
            return {
                'status': False,
                'message': 'HeyGen API not configured'
            }
            
        headers = self._get_headers()
        session_id = session_data.get('session_id')
        
        try:
            url = f"{self.base_url}/streaming.stop"
            response = requests.post(url, json=session_data, headers=headers)
            response_data = response.json()
            
            # Remove from active sessions
            if session_id in self.sessions:
                del self.sessions[session_id]
                
            logger.info(f"Avatar session stopped: {session_id}")
            return response_data
            
        except Exception as e:
            logger.error(f"Failed to stop session: {e}")
            return {
                'status': False,
                'message': str(e)
            }
            
    def interrupt_task(self, interrupt_data: Dict) -> Dict[str, Any]:
        """
        Interrupt current avatar task
        
        Args:
            interrupt_data: Interrupt data including session_id
            
        Returns:
            Interrupt response from HeyGen API
        """
        if not self.api_key:
            return {
                'status': False,
                'message': 'HeyGen API not configured'
            }
            
        headers = self._get_headers()
        
        try:
            url = f"{self.base_url}/streaming.interrupt"
            response = requests.post(url, json=interrupt_data, headers=headers)
            response_data = response.json()
            
            logger.info(f"Task interrupted for session: {interrupt_data.get('session_id')}")
            return response_data
            
        except Exception as e:
            logger.error(f"Failed to interrupt task: {e}")
            return {
                'status': False,
                'message': str(e)
            }
            
    def _strip_html_tags(self, text: str) -> str:
        """
        Remove HTML tags from text for avatar speech
        
        Args:
            text: Text potentially containing HTML tags
            
        Returns:
            Clean text without HTML tags
        """
        # Remove HTML tags
        clean = re.compile('<.*?>')
        text = re.sub(clean, '', text)
        
        # Also remove common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = text.replace('&quot;', '"')
        text = text.replace('&apos;', "'")
        
        # Remove multiple spaces and trim
        text = ' '.join(text.split())
        
        return text
        
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        Get information about an active session
        
        Args:
            session_id: HeyGen session ID
            
        Returns:
            Session information if exists
        """
        return self.sessions.get(session_id)
        
    def list_active_sessions(self) -> Dict[str, Dict]:
        """
        Get all active avatar sessions
        
        Returns:
            Dictionary of active sessions
        """
        return self.sessions.copy()
        
    def cleanup_user_sessions(self, user_email: str) -> int:
        """
        Clean up all sessions for a specific user
        
        Args:
            user_email: User's email address
            
        Returns:
            Number of sessions cleaned up
        """
        sessions_to_remove = []
        
        for session_id, session_info in self.sessions.items():
            if session_info.get('user_email') == user_email:
                # Try to stop the session
                self.stop_session({'session_id': session_id})
                sessions_to_remove.append(session_id)
                
        # Remove from local tracking
        for session_id in sessions_to_remove:
            if session_id in self.sessions:
                del self.sessions[session_id]
                
        logger.info(f"Cleaned up {len(sessions_to_remove)} avatar sessions for user: {user_email}")
        return len(sessions_to_remove)
        
    def validate_api_key(self) -> bool:
        """
        Validate if HeyGen API key is configured and valid
        
        Returns:
            True if API key is valid
        """
        if not self.api_key:
            return False
            
        # Could make a test API call here to validate
        # For now, just check if key exists
        return True