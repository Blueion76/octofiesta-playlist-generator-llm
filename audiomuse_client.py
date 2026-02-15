#!/usr/bin/env python3
"""AudioMuse-AI Client for Octogen

Provides integration with AudioMuse-AI for sonic analysis-based playlist generation.
"""

import requests
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class AudioMuseClient:
    """Client for interacting with AudioMuse-AI API"""
    
    def __init__(self, base_url: str, ai_provider: str, ai_model: str, api_key: Optional[str] = None):
        """
        Initialize AudioMuse-AI client
        
        Args:
            base_url: AudioMuse-AI server URL
            ai_provider: AI provider (gemini, openai, ollama, mistral)
            ai_model: AI model name
            api_key: Optional API key for AI provider
        """
        self.base_url = base_url.rstrip('/')
        self.ai_provider = ai_provider.upper()  # Normalize to uppercase for consistent comparison
        self.ai_model = ai_model
        self.api_key = api_key
        
    def generate_playlist(self, user_request: str, num_songs: int = 25) -> List[Dict]:
        """
        Generate playlist using AudioMuse-AI chat API
        
        Args:
            user_request: Natural language request for playlist
            num_songs: Number of songs to request
            
        Returns:
            List of song dictionaries with keys: title, artist, item_id
        """
        endpoint = f"{self.base_url}/chat/api/chatPlaylist"
        
        payload = {
            "userInput": user_request,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "get_songs": num_songs
        }
        
        # Add API key if provided (case-sensitive comparison with normalized uppercase provider)
        if self.api_key:
            if self.ai_provider == "GEMINI":
                payload["gemini_api_key"] = self.api_key
            elif self.ai_provider == "OPENAI":
                payload["openai_api_key"] = self.api_key
            elif self.ai_provider == "MISTRAL":
                payload["mistral_api_key"] = self.api_key
        
        try:
            response = requests.post(endpoint, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            songs = data.get('query_results', [])
            
            logger.info(f"AudioMuse-AI returned {len(songs)} songs for request: '{user_request}'")
            return songs
            
        except requests.exceptions.RequestException as e:
            logger.error(f"AudioMuse-AI API error: {e}")
            return []
    
    def check_health(self) -> bool:
        """Check if AudioMuse-AI server is accessible"""
        try:
            response = requests.get(f"{self.base_url}/api/config", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
