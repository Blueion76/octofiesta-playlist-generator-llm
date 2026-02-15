"""AI music recommendation engine with configurable backends"""

import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from octogen.storage.cache import LOW_RATING_MIN, LOW_RATING_MAX

# Try to import OpenAI
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Try to import Gemini SDK
try:
    from google import genai
    from google.genai import types
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False


logger = logging.getLogger(__name__)


class AIRecommendationEngine:
    """AI music recommendations with configurable backend."""

    def __init__(
        self,
        api_key: str,
        model: str,
        backend: str = "gemini",
        base_url: Optional[str] = None,
        max_context_songs: int = 500,
        max_output_tokens: int = 65535,
        data_dir: Optional[Path] = None
    ):
        """Initialize AI recommendation engine.
        
        Args:
            api_key: API key for AI service
            model: Model name
            backend: Backend type (gemini, openai, etc.)
            base_url: Optional base URL for OpenAI-compatible APIs
            max_context_songs: Maximum songs to include in context
            max_output_tokens: Maximum output tokens
            data_dir: Data directory for cache files
        """
        self.api_key = api_key
        self.model = model
        self.backend = backend.lower()
        self.max_context_songs = max_context_songs
        self.max_output_tokens = max_output_tokens
        
        # Set up data directory
        if data_dir is None:
            data_dir = Path(os.getenv("OCTOGEN_DATA_DIR", Path.cwd()))
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.cache_file = self.data_dir / "gemini_cache.json"
        self.call_tracker_file = self.data_dir / "ai_last_call.json"
        self.library_hash_file = self.data_dir / "library_hash.txt"
        
        # State management
        self.call_count = 0
        self.max_calls = 1
        self.response_cache: Optional[Dict[str, List[Dict]]] = None

        logger.info("✓ AI Backend: %s", self.backend)
        logger.info("✓ AI Model: %s", self.model)

        if self.backend == "gemini":
            if not GEMINI_SDK_AVAILABLE:
                logger.error("Gemini backend selected but google-genai not installed!")
                logger.error("Run: pip install google-genai")
                sys.exit(1)
            self.genai_client = genai.Client(api_key=api_key)
            logger.info("✓ Gemini SDK initialized with caching support")
        else:
            if OpenAI is None:
                logger.error("OpenAI library not installed!")
                logger.error("Run: pip install openai")
                sys.exit(1)
            if base_url:
                self.client = OpenAI(api_key=api_key, base_url=base_url)
                logger.info("✓ OpenAI-compatible API: %s", base_url)
            else:
                self.client = OpenAI(api_key=api_key)
                logger.info("✓ OpenAI API initialized")

    def _can_call_ai_today(self) -> bool:
        """Check if AI can be called today (once per day limit).
        
        Returns:
            True if AI can be called today
        """
        if not self.call_tracker_file.exists():
            return True
        
        try:
            with open(self.call_tracker_file, 'r') as f:
                data = json.load(f)
                last_call_date = data.get('last_call_date')
                today = datetime.now().strftime("%Y-%m-%d")
                
                if last_call_date == today:
                    logger.warning("AI already called today (%s). Using cached data or skipping.", today)
                    return False
                return True
        except Exception as e:
            logger.warning("Could not read call tracker: %s", str(e))
            return True
    
    def _record_ai_call(self) -> None:
        """Record that AI was called today."""
        try:
            with open(self.call_tracker_file, 'w') as f:
                json.dump({
                    'last_call_date': datetime.now().strftime("%Y-%m-%d"),
                    'last_call_timestamp': datetime.now().isoformat()
                }, f)
            logger.info("Recorded AI call timestamp")
        except Exception as e:
            logger.error("Could not write call tracker: %s", str(e))
            
    def _get_library_hash(self, favorited_songs: List[Dict]) -> str:
        """Generate hash of library for cache invalidation.
        
        Args:
            favorited_songs: List of favorited songs
            
        Returns:
            MD5 hash string
        """
        # Hash based on song count and sample of song IDs
        # Using first 20 and last 20 songs to detect changes
        sample_size = min(20, len(favorited_songs))
        first_songs = [s.get("id", "") for s in favorited_songs[:sample_size]]
        last_songs = [s.get("id", "") for s in favorited_songs[-sample_size:]]
        
        hash_input = f"{len(favorited_songs)}:{','.join(first_songs)}:{','.join(last_songs)}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _should_invalidate_cache(self, favorited_songs: List[Dict]) -> bool:
        """Check if library changed significantly since last cache.
        
        Args:
            favorited_songs: List of favorited songs
            
        Returns:
            True if cache should be invalidated
        """
        current_hash = self._get_library_hash(favorited_songs)
        
        # If no previous hash, store current and don't invalidate
        if not self.library_hash_file.exists():
            logger.info("First run - storing library fingerprint")
            try:
                self.library_hash_file.write_text(current_hash)
            except Exception as e:
                logger.warning("Could not write library hash: %s", str(e))
            return False
        
        try:
            stored_hash = self.library_hash_file.read_text().strip()
        except Exception as e:
            logger.warning("Could not read library hash: %s", str(e))
            return False
        
        if current_hash != stored_hash:
            logger.info("Library changed detected (songs added/removed)")
            logger.info("  Previous library fingerprint: %s", stored_hash[:8])
            logger.info("  Current library fingerprint:  %s", current_hash[:8])
            
            # Update stored hash
            try:
                self.library_hash_file.write_text(current_hash)
            except Exception as e:
                logger.warning("Could not update library hash: %s", str(e))
            
            return True
        
        return False
    
    def _invalidate_cache(self) -> None:
        """Invalidate all caches (in-memory and on-disk)."""
        logger.info("Invalidating AI caches...")
        
        # Clear in-memory cache
        self.response_cache = None
        
        # Delete Gemini cache file
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.info("  Deleted Gemini cache file")
            except Exception as e:
                logger.warning("  Could not delete cache file: %s", str(e))
        
        # Note: We don't delete call tracker to preserve daily limit
        logger.info("Cache invalidation complete")

    def _build_cached_context(
        self,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None,
    ) -> str:
        """Build the static context that will be cached.
        
        Args:
            top_artists: List of top artist names
            top_genres: List of top genres
            favorited_songs: List of favorited songs
            low_rated_songs: Optional list of low-rated songs to avoid
            
        Returns:
            Context string for AI
        """
        artist_list = ", ".join(top_artists[:10])
        genre_list = ", ".join(top_genres[:6])

        # Limit context for memory efficiency
        favorited_sample = [
            f"{s.get('artist','')} - {s.get('title','')}"
            for s in favorited_songs[: self.max_context_songs]
        ]
        favorited_context = "\n".join(favorited_sample)

        negative_context = ""
        if low_rated_songs:
            negative_sample = [
                f"{s.get('artist','')} - {s.get('title','')}"
                for s in low_rated_songs[:50]
            ]
            negative_context = f"""
SONGS TO AVOID (rated {LOW_RATING_MIN}-{LOW_RATING_MAX} stars by user):
{chr(10).join(negative_sample)}
CRITICAL: Never recommend these songs or very similar style/sound."""

        return f"""You are a JSON API for music recommendations.

USER MUSIC PROFILE:
- Favorited songs: {len(favorited_songs)}
- Top artists: {artist_list}
- Top genres: {genre_list}

SAMPLE FAVORITED SONGS:
{favorited_context}{negative_context}

Use songs from this library for "library songs" and recommend NEW similar songs."""

    def _get_or_create_gemini_cache(
        self,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None,
    ):
        """Get or create Gemini cached content with daily invalidation.
        
        Args:
            top_artists: List of top artist names
            top_genres: List of top genres
            favorited_songs: List of favorited songs
            low_rated_songs: Optional list of low-rated songs
            
        Returns:
            Gemini cached content object
        """
        today = datetime.now().strftime("%Y-%m-%d")

        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                cache_name = cache_data.get("name")
                cache_date = cache_data.get("date")

                # Invalidate if cache is from previous day
                if cache_date == today:
                    try:
                        cached_content = self.genai_client.caches.get(name=cache_name)
                        logger.info("Using existing cache: %s", cache_name)
                        return cached_content
                    except Exception:
                        pass
                else:
                    logger.info("Cache is from previous day, creating fresh cache")
            except Exception as e:
                logger.warning("Cache invalid: %s", str(e)[:100])
                if self.cache_file.exists():
                    self.cache_file.unlink()

        # Shuffle songs for daily variety
        shuffled_songs = favorited_songs.copy()
        random.shuffle(shuffled_songs)

        cached_content_text = self._build_cached_context(
            top_artists, top_genres, shuffled_songs, low_rated_songs
        )

        logger.info("Creating context cache (10-20 seconds)...")
        cached_content = self.genai_client.caches.create(
            model=self.model,
            config={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": cached_content_text}]
                    }
                ],
                "ttl": "86400s",  # 24 hours
            }
        )

        with open(self.cache_file, 'w') as f:
            json.dump({
                "name": cached_content.name,
                "created": datetime.now().isoformat(),
                "date": today
            }, f)

        logger.info("Cache created: %s (expires in 24 hours)", cached_content.name)
        return cached_content

    def _build_task_prompt(self, top_genres: List[str]) -> str:
        """Build the task-specific prompt.
        
        Args:
            top_genres: List of top genres
            
        Returns:
            Task prompt string
        """
        top_genres_list = top_genres if top_genres else ["Mix"]
        genre_instructions = []

        for i in range(6):
            genre_name = top_genres_list[i] if i < len(top_genres_list) else "Mix"
            genre_instructions.append(
                f'{i+2}. "Daily Mix {i+1}" (30 songs, genre: {genre_name}): 25 library + 5 new'
            )

        variety_seed = random.randint(1000, 9999)

        return f"""Generate exactly 11 playlists (Variety Seed: {variety_seed}):

1. "Discovery" (50 songs): 45 new discoveries + 5 library
{chr(10).join(genre_instructions)}
8. "Chill Vibes" (30 songs): 25 library + 5 new relaxing
9. "Workout Energy" (30 songs): 25 library + 5 new high-energy
10. "Focus Flow" (30 songs): 25 library + 5 new ambient/instrumental
11. "Drive Time" (30 songs): 25 library + 5 new upbeat

Return ONLY valid JSON:
{{
  "Discovery": [
    {{"artist": "Artist", "title": "Song"}},
    {{"artist": "Artist", "title": "Song"}}
  ],
  "Daily Mix 1": [{{"artist": "Artist", "title": "Song"}}]
}}

CRITICAL RULES:
- Both "artist" and "title" required
- Double quotes for ALL strings
- No trailing commas
- NEVER recommend avoided songs
- No markdown, just raw JSON
- ESCAPE ALL BACKSLASHES: Use \\\\ not \\
- If song title has backslash, use double backslash
- Example: "AC\\\\DC" not "AC\\DC"
"""

    def _generate_with_gemini(
        self,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None,
    ) -> str:
        """Generate playlists using Gemini SDK with caching.
        
        Args:
            top_artists: List of top artist names
            top_genres: List of top genres
            favorited_songs: List of favorited songs
            low_rated_songs: Optional list of low-rated songs
            
        Returns:
            JSON response string
        """
        cached_content = self._get_or_create_gemini_cache(
            top_artists, top_genres, favorited_songs, low_rated_songs
        )

        prompt = self._build_task_prompt(top_genres)

        # Set thinking budget
        thinking_budget = 5000

        response = self.genai_client.models.generate_content(
            model=cached_content.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                cached_content=cached_content.name,
                temperature=0.8,
                max_output_tokens=self.max_output_tokens,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget)
            )
        )

        if hasattr(response, 'usage_metadata'):
            metadata = response.usage_metadata
            thoughts = getattr(metadata, 'thoughtsTokenCount', 0)
            output = getattr(metadata, 'candidates_token_count', 0)
            logger.info("Tokens - Cached: %d, Input: %d, Output: %d, Thoughts: %d",
                       getattr(metadata, 'cached_content_token_count', 0),
                       getattr(metadata, 'prompt_token_count', 0),
                       output,
                       thoughts)

            # Warn if thinking budget was too low
            if thoughts >= thinking_budget * 0.95:
                logger.warning("Thinking budget nearly exhausted (%d/%d tokens)",
                             thoughts, thinking_budget)

        return response.text

    def _generate_with_openai(
        self,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None,
    ) -> str:
        """Generate playlists using OpenAI library.
        
        Args:
            top_artists: List of top artist names
            top_genres: List of top genres
            favorited_songs: List of favorited songs
            low_rated_songs: Optional list of low-rated songs
            
        Returns:
            JSON response string
        """
        cached_context = self._build_cached_context(
            top_artists, top_genres, favorited_songs, low_rated_songs
        )

        task_prompt = self._build_task_prompt(top_genres)
        full_prompt = f"{cached_context}\n\n{task_prompt}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.8,
            max_tokens=self.max_output_tokens,
            response_format={"type": "json_object"},
            timeout=120,
        )

        return response.choices[0].message.content.strip()

    def generate_all_playlists(
        self,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None,
    ) -> Tuple[Dict[str, List[Dict]], Optional[str]]:
        """Generate playlists using configured backend.
        
        Args:
            top_artists: List of top artist names
            top_genres: List of top genres
            favorited_songs: List of favorited songs
            low_rated_songs: Optional list of low-rated songs
        
        Returns:
            Tuple of (playlists_dict, error_reason)
            - playlists_dict: Dictionary of playlist names to song lists
            - error_reason: None if successful, or error code string like 'rate_limit', 'quota_exceeded', 'invalid_response', 'api_error'
        """

        # Check if library changed and invalidate cache if needed
        if self._should_invalidate_cache(favorited_songs):
            self._invalidate_cache()
        
        # Check memory cache first
        if self.response_cache is not None:
            logger.info("Using cached AI response (in-memory)")
            return self.response_cache, None
        
        # Check daily limit BEFORE checking call count
        if not self._can_call_ai_today():
            logger.error("Daily AI call limit reached. Program can restart but won't call AI again today.")
            return {}, "quota_exceeded"
        
        if self.call_count >= self.max_calls:
            logger.error("AI call limit reached (%d)", self.max_calls)
            return {}, "quota_exceeded"
        
        logger.info("Making AI API call (%d/%d)...", self.call_count + 1, self.max_calls)
        self.call_count += 1
        
        try:
            if self.backend == "gemini":
                content = self._generate_with_retry(
                    self._generate_with_gemini,
                    top_artists, top_genres, favorited_songs, low_rated_songs
                )
            else:
                content = self._generate_with_retry(
                    self._generate_with_openai,
                    top_artists, top_genres, favorited_songs, low_rated_songs
                )

            
            # Clean JSON
            content = re.sub(r'^```(?:json)?\s*', '', content, flags=re.MULTILINE)
            content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
            content = content.strip()
            
            json_start = content.find('{')
            json_end = content.rfind('}')
            if json_start != -1 and json_end != -1:
                content = content[json_start:json_end + 1]
            
            logger.info("AI response length: %d chars", len(content))
            
            if not content.endswith('}'):
                logger.error("Response incomplete - missing closing brace")
                return {}, "invalid_response"
            
            all_playlists = json.loads(content)
            
            if not isinstance(all_playlists, dict):
                logger.error("AI response is not a JSON object")
                return {}, "invalid_response"
            
            # Validate and clean
            for playlist_name, songs in list(all_playlists.items()):
                if not isinstance(songs, list):
                    logger.warning("Invalid format for %s", playlist_name)
                    all_playlists[playlist_name] = []
                    continue
                
                valid_songs = [
                    song for song in songs
                    if isinstance(song, dict) and "artist" in song and "title" in song
                ]
                all_playlists[playlist_name] = valid_songs
            
            self.response_cache = all_playlists
            
            # Record the AI call timestamp
            self._record_ai_call()
            
            total = sum(len(songs) for songs in all_playlists.values())
            logger.info("Generated %d playlists (%d songs)", len(all_playlists), total)
            return all_playlists, None
            
        except json.JSONDecodeError as e:
            logger.error("JSON parse error at line %d col %d: %s", e.lineno, e.colno, e.msg)
            return {}, "invalid_response"
        except Exception as e:
            error_msg = str(e).lower()
            error_type = type(e).__name__
            
            # Check if it's a rate limit error
            is_rate_limit = any(phrase in error_msg for phrase in [
                'rate limit', 'quota', 'too many requests', '429', 
                'resource_exhausted', 'rate_limit_exceeded'
            ]) or 'RateLimitError' in error_type
            
            if is_rate_limit:
                # Rollback call count for rate limit errors
                self.call_count -= 1
                logger.warning("Rate limit error detected - call count rolled back to %d", self.call_count)
                logger.warning("You can retry immediately as this attempt was not recorded")
                logger.error("AI request failed: %s", str(e)[:200])
                return {}, "rate_limit"
            
            # For non-rate-limit errors, keep the call counted
            logger.error("AI request failed (counted): %s", str(e)[:200])
            return {}, "api_error"
            
    def _generate_with_retry(self, generate_func, *args, **kwargs) -> str:
        """Retry AI generation with exponential backoff for rate limits.
        
        Args:
            generate_func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Generated content string
        """
        max_retries = 3
        base_delay = 10.0
        
        for attempt in range(max_retries):
            try:
                return generate_func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                error_type = type(e).__name__
                
                # Check if it's a rate limit error (works for both Gemini and OpenAI)
                is_rate_limit = any(phrase in error_msg for phrase in [
                    'rate limit', 'quota', 'too many requests', '429', 
                    'resource_exhausted', 'rate_limit_exceeded'
                ]) or 'RateLimitError' in error_type
                
                if attempt == max_retries - 1:
                    if is_rate_limit:
                        logger.warning("💡 Tip: Consider using a different AI provider or model with higher limits")
                    raise  # Last attempt, let it fail
                
                if is_rate_limit:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Rate limit hit [%s] (attempt %d/%d). Retrying in %.1fs...",
                        error_type, attempt + 1, max_retries, delay
                    )
                    time.sleep(delay)
                else:
                    # Not a rate limit error, fail immediately
                    logger.error("Non-rate-limit error: %s", str(e)[:200])
                    raise
        
        raise Exception("Max retries exceeded")
