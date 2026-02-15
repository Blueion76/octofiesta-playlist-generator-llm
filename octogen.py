#!/usr/bin/env python3
"""OctoGen - AI-Powered Music Discovery Engine for Navidrome

Docker Edition with Environment Variable Configuration + Built-in Scheduling
Refactored with modular architecture for maintainability.

Features:
- AI recommendations (Gemini, OpenAI, Groq, Ollama, etc.)
- Automatic downloads via Octo-Fiesta
- Star rating integration (excludes 1-2 star songs)
- Daily cache for performance
- Last.fm and ListenBrainz integration
- Async operations for speed
- Zero config files - pure environment variables
- Built-in cron scheduling
- Prometheus metrics (optional)
- Circuit breaker for resilience
- Web UI dashboard (optional)
"""

import sys
import os
import json
import logging
from logging.handlers import RotatingFileHandler

import hashlib
import secrets
import requests
import re
import time
import fcntl
import atexit
import sqlite3
import asyncio
import aiohttp
import difflib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter
from urllib.parse import urlencode

# Import from refactored modules
try:
    from octogen.utils.auth import subsonic_auth_params
    from octogen.utils.retry import retry_with_backoff
    from octogen.storage.cache import RatingsCache, LOW_RATING_MIN, LOW_RATING_MAX
    from octogen.api.navidrome import NavidromeAPI, OctoFiestaTrigger
    from octogen.api.lastfm import LastFMAPI
    from octogen.api.listenbrainz import ListenBrainzAPI
    from octogen.api.audiomuse import AudioMuseClient
    from octogen.ai.engine import AIRecommendationEngine
    from octogen.config import load_config_from_env
    from octogen.monitoring.metrics import setup_metrics, record_playlist_created, record_song_downloaded, record_run_complete
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import refactored modules: {e}", file=sys.stderr)
    print("Falling back to inline implementations", file=sys.stderr)
    MODULES_AVAILABLE = False

# Try to import croniter for scheduling support
try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False

try:
    from openai import OpenAI
except ImportError:
    if not MODULES_AVAILABLE:
        print("ERROR: pip install openai requests aiohttp croniter", file=sys.stderr)
        sys.exit(1)

# Optional: Native Gemini SDK
try:
    from google import genai
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False

# ============================================================================
# PATHS AND LOGGING - Configurable via environment
# ============================================================================

# Data directory from environment (defaults to /data in Docker)
BASE_DIR = Path(os.getenv("OCTOGEN_DATA_DIR", Path(__file__).parent.absolute()))
LOG_FILE = BASE_DIR / "octogen.log"
LOCK_FILE = BASE_DIR / "octogen.lock"
RATINGS_DB = BASE_DIR / "octogen_cache.db"
CACHE_FILE = BASE_DIR / "gemini_cache.json"

# Ensure data directory exists
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        RotatingFileHandler(
            LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB per file
            backupCount=5,           # Keep 5 old files
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# Constants
LOW_RATING_MIN = 1
LOW_RATING_MAX = 2
COOLDOWN_EXIT_DELAY_SECONDS = 60  # Sleep duration before exit in manual mode to prevent rapid restarts

# Default genres for Daily Mixes when library genres are insufficient
DEFAULT_DAILY_MIX_GENRES = ["rock", "pop", "electronic", "hip-hop", "indie", "jazz"]

# ============================================================================
# BANNER
# ============================================================================

def print_banner():
    """Print OctoGen banner"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   ██████╗  ██████╗████████╗ ██████╗  ██████╗ ███████╗███╗   ██╗   ║
║  ██╔═══██╗██╔════╝╚══██╔══╝██╔═══██╗██╔════╝ ██╔════╝████╗  ██║   ║
║  ██║   ██║██║        ██║   ██║   ██║██║  ███╗█████╗  ██╔██╗ ██║   ║
║  ██║   ██║██║        ██║   ██║   ██║██║   ██║██╔══╝  ██║╚██╗██║   ║
║  ╚██████╔╝╚██████╗   ██║   ╚██████╔╝╚██████╔╝███████╗██║ ╚████║   ║
║   ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ║
║                                                                   ║
║             AI-Powered Music Discovery for Navidrome              ║
║                         Docker Edition                            ║    
║                                                                   ║   
╚═══════════════════════════════════════════════════════════════════╝
    """
    print(banner)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def subsonic_auth_params(username: str, password: str) -> Dict[str, str]:
    """Generate Subsonic API authentication parameters."""
    salt = secrets.token_hex(6)
    token = hashlib.md5((password + salt).encode("utf-8")).hexdigest()
    return {
        "u": username,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "OctoGen",
        "f": "json",
    }

def retry_with_backoff(func, max_retries: int = 3, initial_delay: float = 1.0):
    """Retry function with exponential backoff."""
    def wrapper(*args, **kwargs):
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(
                    "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1, max_retries, str(e)[:100], delay
                )
                time.sleep(delay)
                delay *= 2
        return None
    return wrapper

def acquire_lock() -> object:
    """Prevent multiple instances from running."""
    try:
        lock = open(LOCK_FILE, "w")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.write(str(os.getpid()))
        lock.flush()

        def cleanup():
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink()
            except:
                pass

        atexit.register(cleanup)
        return lock
    except IOError:
        logger.error("Another instance is already running!")
        sys.exit(1)

def write_health_status(status: str, message: str = "") -> None:
    """Write health status for monitoring."""
    health_file = BASE_DIR / "health.json"
    try:
        with open(health_file, 'w') as f:
            json.dump({
                "status": status,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "pid": os.getpid()
            }, f, indent=2)
    except Exception as e:
        logger.warning("Could not write health status: %s", str(e))


# ============================================================================
# RATINGS CACHE DATABASE
# ============================================================================

class RatingsCache:
    """SQLite cache for song ratings to avoid repeated scans."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    song_id TEXT PRIMARY KEY,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rating
                ON ratings(rating)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_last_scan_date(self) -> Optional[str]:
        """Get the last full scan date."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM cache_metadata WHERE key = 'last_scan_date'"
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_last_scan_date(self, date: str) -> None:
        """Update the last full scan date."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache_metadata (key, value)
                   VALUES ('last_scan_date', ?)""",
                (date,)
            )
            conn.commit()

    def update_rating(self, song_id: str, artist: str, title: str, rating: int) -> None:
        """Update or insert a song rating."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ratings
                   (song_id, artist, title, rating, last_updated)
                   VALUES (?, ?, ?, ?, ?)""",
                (song_id, artist, title, rating, datetime.now().isoformat())
            )
            conn.commit()

    def get_low_rated_songs(self) -> List[Dict]:
        """Get all songs rated 1-2 stars from cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT song_id, artist, title, rating
                   FROM ratings
                   WHERE rating BETWEEN ? AND ?""",
                (LOW_RATING_MIN, LOW_RATING_MAX)
            )
            return [
                {"id": row[0], "artist": row[1], "title": row[2], "rating": row[3]}
                for row in cursor.fetchall()
            ]

    def clear_cache(self) -> None:
        """Clear all ratings from cache."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM ratings")
            conn.commit()

# ============================================================================
# API CLASSES
# ============================================================================

class LastFMAPI:
    """Fetches recommendations from Last.fm with retry logic."""

    def __init__(self, api_key: str, username: str):
        self.api_key = api_key
        self.username = username
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        self.session = requests.Session()
        logger.info("Last.fm initialized: %s", username)

    def _request(self, method: str, params: dict = None) -> Optional[dict]:
        """Make API request with retry logic."""
        request_params = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            "user": self.username,
        }
        if params:
            request_params.update(params)

        @retry_with_backoff
        def make_request():
            r = self.session.get(self.base_url, params=request_params, timeout=30)
            r.raise_for_status()
            return r.json()

        try:
            return make_request()
        except Exception as e:
            logger.error("Last.fm API error: %s", str(e)[:200])
            return None

    def get_recommended_tracks(self, limit: int = 50) -> List[Dict]:
        """Fetch recommended tracks."""
        logger.info("Fetching Last.fm recommendations...")

        top_artists_response = self._request(
            "user.getTopArtists", {"limit": 10, "period": "3month"}
        )
        if not top_artists_response or "topartists" not in top_artists_response:
            logger.warning("No top artists found")
            return []

        top_artists = [
            artist["name"]
            for artist in top_artists_response["topartists"].get("artist", [])
        ]

        recommendations: List[Dict] = []
        for artist in top_artists[:5]:
            similar_response = self._request(
                "artist.getSimilar", {"artist": artist, "limit": 10}
            )
            if not similar_response or "similarartists" not in similar_response:
                continue

            for similar in similar_response["similarartists"].get("artist", [])[:5]:
                tracks_response = self._request(
                    "artist.getTopTracks", {"artist": similar["name"], "limit": 2}
                )
                if not tracks_response or "toptracks" not in tracks_response:
                    continue

                for track in tracks_response["toptracks"].get("track", []):
                    recommendations.append({
                        "artist": track["artist"]["name"],
                        "title": track["name"]
                    })
                    if len(recommendations) >= limit:
                        break
            if len(recommendations) >= limit:
                break

        logger.info("Found %d Last.fm recommendations", len(recommendations))
        return recommendations[:limit]

class ListenBrainzAPI:
    """Fetches recommendations from ListenBrainz."""

    def __init__(self, username: str, token: str = None):
        self.username = username
        self.token = token
        self.base_url = "https://api.listenbrainz.org/1"
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})
        logger.info("ListenBrainz initialized: %s", username)

    def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make API request with error handling."""
        try:
            url = f"{self.base_url}/{endpoint}"
            r = self.session.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error("ListenBrainz API error: %s", str(e)[:200])
            return None

    def get_created_for_you_playlists(self, count: int = 25, offset: int = 0) -> List[Dict]:
        """
        Fetch metadata for 'Created For You' playlists.
        Returns list of playlist metadata (without tracks).
        """
        logger.info("Fetching 'Created For You' playlists...")
        
        response = self._request(
            f"user/{self.username}/playlists/createdfor",
            params={"count": count, "offset": offset}
        )
        
        if not response or "playlists" not in response:
            logger.warning("No 'Created For You' playlists found")
            return []
        
        playlists = response["playlists"]
        
        # DEBUG
        if playlists:
            logger.info("First playlist keys: %s", list(playlists[0].keys()))
        
        logger.info("Found %d 'Created For You' playlists", len(playlists))
        return playlists

    def get_playlist_tracks(self, playlist_mbid: str) -> List[Dict]:
        """
        Fetch tracks from a specific playlist by MBID.
        Returns list of tracks with artist and title.
        """
        logger.info("Fetching playlist tracks for: %s", playlist_mbid)
        
        response = self._request(f"playlist/{playlist_mbid}")
        
        if not response or "playlist" not in response:
            logger.warning("Playlist not found: %s", playlist_mbid)
            return []
        
        tracks = []
        playlist_data = response["playlist"]
        
        # Extract tracks from JSPF format
        for track in playlist_data.get("track", []):
            # Get artist and title from track metadata
            artist = track.get("creator", "Unknown")
            title = track.get("title", "Unknown")
            
            tracks.append({
                "artist": artist,
                "title": title,
                "mbid": track.get("identifier", [""])[0].split("/")[-1] if track.get("identifier") else None
            })
        
        logger.info("Found %d tracks in playlist", len(tracks))
        return tracks

    def get_recommendations(self, limit: int = 50) -> List[Dict]:
        """
        Fetch personalized recommendations using collaborative filtering.
        This is the original recommendation endpoint (different from playlists).
        """
        logger.info("Fetching ListenBrainz CF recommendations...")

        response = self._request(f"cf/recommendation/user/{self.username}/recording")
        if not response or "payload" not in response:
            logger.warning("No ListenBrainz recommendations found")
            return []

        recommendations: List[Dict] = []
        for rec in response["payload"].get("mbids", [])[:limit]:
            recording_response = self._request(
                "metadata/recording", {"recording_mbids": rec["recording_mbid"]}
            )
            if recording_response:
                for _mbid, data in recording_response.items():
                    artist = data.get("artist", {}).get("name", "Unknown")
                    title = data.get("recording", {}).get("name", "Unknown")
                    recommendations.append({"artist": artist, "title": title})

        logger.info("Found %d ListenBrainz CF recommendations", len(recommendations))
        return recommendations



class OctoFiestaTrigger:
    """Triggers Octo-Fiesta downloads via Subsonic endpoints."""

    def __init__(self, octo_url: str, username: str, password: str, dry_run: bool = False):
        self.octo_url = octo_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.dry_run = dry_run

    def _request(self, endpoint: str, extra_params: dict = None) -> Optional[dict]:
        """Make Subsonic API request."""
        params = subsonic_auth_params(self.username, self.password)
        if extra_params:
            params.update(extra_params)

        try:
            r = self.session.get(f"{self.octo_url}/rest/{endpoint}", params=params, timeout=30)
            r.raise_for_status()
            response = r.json().get("subsonic-response", {})
            if response.get("status") == "failed":
                return None
            return response
        except Exception:
            return None

    def search_and_trigger_download(self, artist: str, title: str) -> Tuple[bool, str]:
        """Search and trigger download."""
        if self.dry_run:
            logger.info("[DRY RUN] Would download: %s - %s", artist, title)
            return True, "dry-run"

        logger.debug("Searching: %s - %s", artist, title)
        response = self._request("search3", {"query": f"{artist} {title}", "songCount": 5})

        if not response:
            return False, "API error"

        songs = response.get("searchResult3", {}).get("song", [])
        if not songs:
            return False, "Not found"

        best_match = songs[0]
        song_id = best_match["id"]

        logger.debug("Triggering download (stream warmup)")
        stream_url = f"{self.octo_url}/rest/stream"
        params = subsonic_auth_params(self.username, self.password)
        params["id"] = song_id

        try:
            r = self.session.get(stream_url, params=params, stream=True, timeout=10)
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    break
            return True, song_id
        except Exception as e:
            return False, str(e)[:100]

class NavidromeAPI:
    """Navidrome/Subsonic API with star rating support and async operations."""
    
    # Version markers for detecting remixes, live versions, etc.
    VERSION_MARKERS = [
        'remix', 'mix', 'edit', 'version', 'acoustic', 'live', 'instrumental',
        'extended', 'radio edit', 'demo', 'remaster', 'cover', 'vip', 'bootleg',
        'mashup'
    ]
    
    # Search and matching thresholds
    MATCH_THRESHOLD = 0.75  # Minimum match score for library search (75%)
    SIMILARITY_THRESHOLD = 0.85  # Minimum similarity for near-duplicate detection (85%)
    LIBRARY_SEARCH_LIMIT = 30  # Max songs per search strategy in library search
    SIMILAR_SEARCH_LIMIT = 50  # Max songs for similar song detection

    def __init__(self, url: str, username: str, password: str,
                 ratings_cache: RatingsCache, config: dict):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.ratings_cache = ratings_cache

        # Configurable values
        self.album_batch_size = config.get("performance", {}).get("album_batch_size", 500)
        self.max_albums = config.get("performance", {}).get("max_albums_scan", 10000)
        self.scan_timeout = config.get("performance", {}).get("scan_timeout", 60)

    def _request(self, endpoint: str, extra_params: dict = None) -> Optional[dict]:
        """Make Subsonic API request."""
        params = subsonic_auth_params(self.username, self.password)
        if extra_params:
            params.update(extra_params)

        try:
            r = self.session.get(f"{self.url}/rest/{endpoint}", params=params, timeout=30)
            r.raise_for_status()
            response = r.json().get("subsonic-response", {})
            if response.get("status") == "failed":
                logger.error("Navidrome API failed: %s", response.get("error", {}).get("message"))
                return None
            return response
        except requests.exceptions.RequestException as e:
            logger.error("Navidrome request error: %s", str(e)[:200])
            return None
        except Exception as e:
            logger.error("Navidrome unexpected error: %s", str(e)[:200])
            return None

    def test_connection(self) -> bool:
        """Test Navidrome connection."""
        response = self._request("ping")
        if response:
            logger.info("✓ Connected to Navidrome: %s", self.url)
            return True
        logger.error("✗ Navidrome connection failed")
        return False

    def get_starred_songs(self) -> List[Dict]:
        """Get all starred songs."""
        response = self._request("getStarred2")
        if not response:
            logger.warning("Failed to fetch starred songs")
            return []

        songs: List[Dict] = []
        starred_data = response.get("starred2", {})
        for song in starred_data.get("song", []):
            songs.append({
                "id": song["id"],
                "title": song["title"],
                "artist": song["artist"],
                "album": song.get("album", ""),
                "genre": song.get("genre", "Unknown"),
            })

        return songs

    def get_song_rating(self, song_id: str) -> int:
        """Get rating for a song (0-5 stars)."""
        response = self._request("getSong", {"id": song_id})
        if not response:
            return 0
        song = response.get("song", {})
        return song.get("userRating", 0)

    def set_song_rating(self, song_id: str, rating: int) -> None:
        """Set rating for a song (1-5 stars, or 0 to remove)."""
        if rating < 0 or rating > 5:
            logger.warning("Invalid rating %d, must be 0-5", rating)
            return
        self._request("setRating", {"id": song_id, "rating": rating})

    async def _fetch_album_songs_async(self, session: aiohttp.ClientSession,
                                       album_id: str) -> List[Dict]:
        """Async fetch songs from an album."""
        params = subsonic_auth_params(self.username, self.password)
        params["id"] = album_id
        url = f"{self.url}/rest/getAlbum"

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                data = await response.json()
                result = data.get("subsonic-response", {})
                if result.get("status") == "ok":
                    return result.get("album", {}).get("song", [])
        except Exception:
            pass
        return []

    async def _scan_albums_async(self, album_ids: List[str]) -> List[Dict]:
        """Scan multiple albums in parallel for rated songs."""
        low_rated = []

        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_album_songs_async(session, album_id) for album_id in album_ids]
            results = await asyncio.gather(*tasks)

            for songs in results:
                for song in songs:
                    rating = song.get("userRating", 0)
                    song_id = song.get("id")

                    if song_id and rating > 0:
                        # Update cache
                        self.ratings_cache.update_rating(
                            song_id,
                            song.get("artist", "Unknown"),
                            song.get("title", "Unknown"),
                            rating
                        )

                        if LOW_RATING_MIN <= rating <= LOW_RATING_MAX:
                            low_rated.append({
                                "artist": song.get("artist", "Unknown"),
                                "title": song.get("title", "Unknown"),
                                "rating": rating,
                                "id": song_id
                            })

        return low_rated

    def get_low_rated_songs(self) -> List[Dict]:
        """Get all songs rated 1-2 stars with caching."""
        today = datetime.now().strftime("%Y-%m-%d")
        last_scan = self.ratings_cache.get_last_scan_date()

        # Use cache if scanned today
        if last_scan == today:
            logger.info("Using cached low-rated songs from today")
            return self.ratings_cache.get_low_rated_songs()

        logger.info("Performing full library scan for ratings (cached daily)")

        # Fetch all albums
        albums_to_check = self._fetch_all_albums()
        logger.info("Found %d albums to scan", len(albums_to_check))

        if not albums_to_check:
            return []

        # Async scan
        album_ids = [album.get("id") for album in albums_to_check if album.get("id")]
        low_rated = asyncio.run(self._scan_albums_async(album_ids))

        # Update cache metadata
        self.ratings_cache.set_last_scan_date(today)

        logger.info("Found %d low-rated songs (1-2 stars)", len(low_rated))
        return low_rated

    def _fetch_all_albums(self) -> List[Dict]:
        """Fetch all albums from library."""
        albums = []
        offset = 0

        while offset < self.max_albums:
            response = self._request("getAlbumList2", {
                "type": "alphabeticalByName",
                "size": self.album_batch_size,
                "offset": offset
            })

            if not response:
                break

            album_list = response.get("albumList2", {}).get("album", [])
            if not album_list:
                break

            albums.extend(album_list)
            offset += self.album_batch_size

        return albums

    def get_top_artists(self, limit: int = 50) -> List[str]:
        """Get top artists from starred songs."""
        songs = self.get_starred_songs()
        if not songs:
            return []

        artist_counts = Counter([s["artist"] for s in songs])
        return [artist for artist, _count in artist_counts.most_common(limit)]

    def get_top_genres(self, limit: int = 10) -> List[str]:
        """Get top genres from starred songs."""
        songs = self.get_starred_songs()
        if not songs:
            return ["pop", "rock", "indie", "electronic"]

        genres = [s["genre"] for s in songs if s.get("genre") and s["genre"] != "Unknown"]
        if not genres:
            return ["pop", "rock", "indie", "electronic"]

        genre_counts = Counter(genres)
        return [g for g, _count in genre_counts.most_common(limit)]

    def _strip_featured(self, text: str) -> str:
        """Remove featured artist variations."""
        text = re.sub(r'\s+feat\.?\s+.*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+ft\.?\s+.*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+featuring\s+.*$', '', text, flags=re.IGNORECASE)
        return text.strip()
    
    def _normalize_for_comparison(self, text: str, preserve_version: bool = False) -> str:
        """Normalize text for comparison."""
        text = self._strip_featured(text)
        if not preserve_version:
            # Remove parentheses and brackets content
            text = re.sub(r'\s*[\[\(].*?[\]\)]', '', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = ' '.join(text.split())
        return text.lower().strip()
    
    def _has_version_marker(self, text: str) -> Optional[str]:
        """Check if text contains version markers and return the marker found."""
        text_lower = text.lower()
        for marker in self.VERSION_MARKERS:
            # Use word boundary matching to avoid false positives
            pattern = r'\b' + re.escape(marker) + r'\b'
            if re.search(pattern, text_lower):
                return marker
        return None
    
    def _calculate_match_score(self, search_artist: str, search_title: str,
                              result_artist: str, result_title: str) -> float:
        """Calculate match score (0.0-1.0) using 50% artist + 50% title."""
        artist_ratio = difflib.SequenceMatcher(None, search_artist, result_artist).ratio()
        title_ratio = difflib.SequenceMatcher(None, search_title, result_title).ratio()
        return (artist_ratio * 0.5) + (title_ratio * 0.5)

    def search_song(self, artist: str, title: str) -> Optional[str]:
        """Search for a song with fuzzy matching and version detection."""
        
        # Normalize search terms
        search_artist_norm = self._normalize_for_comparison(artist, preserve_version=False)
        search_title_norm = self._normalize_for_comparison(title, preserve_version=False)
        search_version = self._has_version_marker(title)
        
        # Try multiple search strategies
        search_queries = [
            f'"{artist}" "{title}"',  # Exact artist and title
            f'"{title}"',  # Title only
            f'{artist} {title}',  # Concatenation
        ]
        
        all_songs = []
        for query in search_queries:
            response = self._request("search3", {"query": query, "songCount": self.LIBRARY_SEARCH_LIMIT})
            if response:
                songs = response.get("searchResult3", {}).get("song", [])
                all_songs.extend(songs)
        
        # Remove duplicates by ID
        seen_ids = set()
        unique_songs = []
        for song in all_songs:
            song_id = song.get("id")
            if song_id and song_id not in seen_ids:
                seen_ids.add(song_id)
                unique_songs.append(song)
        
        if not unique_songs:
            return None
        
        # Find best match
        best_match = None
        best_score = 0.0
        
        for song in unique_songs:
            result_artist = song.get("artist", "")
            result_title = song.get("title", "")
            
            # Normalize result
            result_artist_norm = self._normalize_for_comparison(result_artist, preserve_version=False)
            result_title_norm = self._normalize_for_comparison(result_title, preserve_version=False)
            result_version = self._has_version_marker(result_title)
            
            # Calculate match score
            score = self._calculate_match_score(search_artist_norm, search_title_norm,
                                              result_artist_norm, result_title_norm)
            
            # Check if this is a better match
            if score > best_score:
                best_score = score
                best_match = (song["id"], result_artist, result_title, result_version)
        
        if not best_match:
            return None
        
        song_id, match_artist, match_title, match_version = best_match
        
        # Decision logic based on MATCH_THRESHOLD
        if best_score >= self.MATCH_THRESHOLD:
            # Check version compatibility
            if search_version != match_version:
                # Different versions - return None to trigger download
                logger.info("Found different version: %s - %s (%.0f%% match) - search has '%s', library has '%s'",
                          match_artist, match_title, best_score * 100,
                          search_version or "original", match_version or "original")
                return None
            else:
                # Same version or both are originals
                logger.debug("Library match: %s - %s (%.0f%% match)",
                           match_artist, match_title, best_score * 100)
                return song_id
        
        # Score too low
        return None

    def check_for_similar_song(self, artist: str, title: str) -> Optional[str]:
        """Check for similar songs to prevent near-duplicates before downloading."""
        
        # Search by artist name
        response = self._request("search3", {"query": f'"{artist}"', "songCount": self.SIMILAR_SEARCH_LIMIT})
        
        if not response:
            return None
        
        songs = response.get("searchResult3", {}).get("song", [])
        
        if not songs:
            return None
        
        # Normalize search terms
        search_artist_norm = self._normalize_for_comparison(artist)
        search_title_norm = self._normalize_for_comparison(title)
        search_has_version = bool(self._has_version_marker(title))
        
        # Check each result for similarity
        for song in songs:
            result_artist = song.get("artist", "")
            result_title = song.get("title", "")
            
            # Check for version markers
            result_has_version = bool(self._has_version_marker(result_title))
            
            # Skip if version markers differ (don't match remix to original)
            if search_has_version != result_has_version:
                continue
            
            # Normalize result
            result_artist_norm = self._normalize_for_comparison(result_artist)
            result_title_norm = self._normalize_for_comparison(result_title)
            
            # Calculate match ratios
            artist_ratio = difflib.SequenceMatcher(None, search_artist_norm, result_artist_norm).ratio()
            title_ratio = difflib.SequenceMatcher(None, search_title_norm, result_title_norm).ratio()
            
            # If both are high similarity, consider it a near-duplicate
            if artist_ratio >= self.SIMILARITY_THRESHOLD and title_ratio >= self.SIMILARITY_THRESHOLD:
                logger.warning("Similar song found in library: %s - %s (artist: %.0f%%, title: %.0f%%)",
                             result_artist, result_title, artist_ratio * 100, title_ratio * 100)
                return song["id"]
        
        return None

    def trigger_scan(self) -> None:
        """Trigger a library scan."""
        self._request("startScan")

    def wait_for_scan(self, max_wait: int = None) -> bool:
        """Wait for library scan to complete."""
        if max_wait is None:
            max_wait = self.scan_timeout

        start_time = time.time()
        while time.time() - start_time < max_wait:
            time.sleep(3)
            response = self._request("getScanStatus")
            if response:
                scan_status = response.get("scanStatus", {})
                if not scan_status.get("scanning", False):
                    return True
        return False

    def create_playlist(self, name: str, song_ids: List[str]) -> bool:
        """Create or update a playlist."""
        if not song_ids:
            return False

        # Delete existing playlist
        response = self._request("getPlaylists")
        if response:
            playlists = response.get("playlists", {}).get("playlist", [])
            for pl in playlists:
                if pl.get("name") == name:
                    self._request("deletePlaylist", {"id": pl["id"]})
                    time.sleep(1)
                    break

        # Create playlist
        params = subsonic_auth_params(self.username, self.password)
        create_params = {"name": name, **params}
        create_url = f"{self.url}/rest/createPlaylist?{urlencode(create_params)}"

        try:
            r = self.session.get(create_url, timeout=30)
            response = r.json().get("subsonic-response", {})
            if response.get("status") != "ok":
                return False

            playlist_id = response.get("playlist", {}).get("id")
            if not playlist_id:
                return False

            # Add songs
            for song_id in song_ids:
                params = subsonic_auth_params(self.username, self.password)
                form_data = [("playlistId", playlist_id), ("songIdToAdd", song_id)]
                self.session.post(
                    f"{self.url}/rest/updatePlaylist",
                    params=params,
                    data=form_data,
                    timeout=30,
                )
                time.sleep(0.1)

            logger.info("Created playlist: %s (%d songs)", name, len(song_ids))
            return True

        except Exception as e:
            logger.error("Failed to create playlist %s: %s", name, str(e)[:200])
            return False

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
    ):
        self.api_key = api_key
        self.model = model
        self.backend = backend.lower()
        self.max_context_songs = max_context_songs
        self.max_output_tokens = max_output_tokens
        self.cache_file = CACHE_FILE
        self.call_tracker_file = BASE_DIR / "ai_last_call.json"
        self.library_hash_file = BASE_DIR / "library_hash.txt"
        
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
            if base_url:
                self.client = OpenAI(api_key=api_key, base_url=base_url)
                logger.info("✓ OpenAI-compatible API: %s", base_url)
            else:
                self.client = OpenAI(api_key=api_key)
                logger.info("✓ OpenAI API initialized")
    def _can_call_ai_today(self) -> bool:
        """Check if AI can be called today (once per day limit)."""
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
        """Generate hash of library for cache invalidation."""
        import hashlib
        
        # Hash based on song count and sample of song IDs
        # Using first 20 and last 20 songs to detect changes
        sample_size = min(20, len(favorited_songs))
        first_songs = [s.get("id", "") for s in favorited_songs[:sample_size]]
        last_songs = [s.get("id", "") for s in favorited_songs[-sample_size:]]
        
        hash_input = f"{len(favorited_songs)}:{','.join(first_songs)}:{','.join(last_songs)}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _should_invalidate_cache(self, favorited_songs: List[Dict]) -> bool:
        """Check if library changed significantly since last cache."""
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
        """Build the static context that will be cached."""
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
        """Get or create Gemini cached content with daily invalidation."""
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
        import random
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
        """Build the task-specific prompt."""
        import random

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
        """Generate playlists using Gemini SDK with caching."""
        from google.genai import types

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
        """Generate playlists using OpenAI library."""
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
        """Retry AI generation with exponential backoff for rate limits."""
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
        

# ============================================================================
# SERVICE TRACKER
# ============================================================================

class ServiceTracker:
    """Tracks execution status and outcomes for different services."""
    
    def __init__(self):
        self.services = {}
    
    def record_service(self, name: str, success: bool, **metadata):
        """Record service execution outcome with metadata.
        
        Args:
            name: Service name (e.g., 'ai_playlists', 'audiomuse', 'lastfm', 'listenbrainz')
            success: Whether the service executed successfully
            **metadata: Additional metadata like playlists created, songs added, error reason, etc.
        
        Note:
            Timestamp is recorded for each service for tracking and potential future use
            (e.g., per-service cooldowns, debugging, audit logs).
        """
        self.services[name] = {
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **metadata
        }
        logger.debug("Service tracker: Recorded %s - success=%s, metadata=%s", name, success, metadata)
    
    def get_summary(self) -> Dict:
        """Return summary of all service outcomes."""
        return {
            "services": self.services,
            "total_services": len(self.services),
            "successful_services": sum(1 for s in self.services.values() if s.get("success")),
            "failed_services": sum(1 for s in self.services.values() if not s.get("success"))
        }
    
    def should_skip_cooldown(self) -> bool:
        """Determine if cooldown should apply based on what succeeded.
        
        Returns True if we should skip the cooldown (allow immediate retry).
        This happens when only external services succeeded but AI failed.
        """
        ai_success = self.services.get("ai_playlists", {}).get("success", False)
        audiomuse_success = self.services.get("audiomuse", {}).get("success", False)
        
        # If primary services (AI or AudioMuse) succeeded, apply cooldown
        if ai_success or audiomuse_success:
            return False
        
        # If primary services failed but external services succeeded, we can skip cooldown
        external_success = (
            self.services.get("lastfm", {}).get("success", False) or
            self.services.get("listenbrainz", {}).get("success", False)
        )
        
        return external_success
    
    def get_primary_services_succeeded(self) -> bool:
        """Check if any primary service (AI or AudioMuse) succeeded."""
        ai_success = self.services.get("ai_playlists", {}).get("success", False)
        audiomuse_success = self.services.get("audiomuse", {}).get("success", False)
        return ai_success or audiomuse_success


# ============================================================================
# MAIN ENGINE
# ============================================================================

class OctoGenEngine:
    """Main orchestrator with environment variable configuration."""

    def __init__(self, dry_run: bool = False):
        # Load configuration from environment variables
        self.config = self._load_config_from_env()
        self._validate_env_config()

        self.dry_run = dry_run
        if dry_run:
            logger.info("=" * 70)
            logger.info("DRY RUN MODE - No downloads or playlist changes will be made")
            logger.info("=" * 70)

        # Initialize ratings cache
        self.ratings_cache = RatingsCache(RATINGS_DB)

        # Initialize APIs
        self.nd = NavidromeAPI(
            self.config["navidrome"]["url"],
            self.config["navidrome"]["username"],
            self.config["navidrome"]["password"],
            self.ratings_cache,
            self.config
        )

        if not self.nd.test_connection():
            logger.error("Cannot connect to Navidrome")
            sys.exit(1)

        self.octo = OctoFiestaTrigger(
            self.config["octofiesta"]["url"],
            self.config["navidrome"]["username"],
            self.config["navidrome"]["password"],
            dry_run=dry_run
        )

        # Initialize AI engine (optional if other services are configured)
        self.ai = None
        if self.config["ai"]["api_key"]:
            max_context = int(self.config.get("ai", {}).get("max_context_songs", 500))
            max_output = int(self.config.get("ai", {}).get("max_output_tokens", 65535))
            backend = self.config.get("ai", {}).get("backend", "gemini")

            self.ai = AIRecommendationEngine(
                api_key=self.config["ai"]["api_key"],
                model=self.config["ai"]["model"],
                backend=backend,
                base_url=self.config.get("ai", {}).get("base_url"),
                max_context_songs=max_context,
                max_output_tokens=max_output,
            )
            logger.info("✓ AI engine initialized")
        else:
            logger.info("ℹ️  AI engine not configured (using alternative music sources)")


        # Optional services
        self.lastfm: Optional[LastFMAPI] = None
        if self.config.get("lastfm", {}).get("enabled", False):
            self.lastfm = LastFMAPI(
                self.config["lastfm"]["api_key"],
                self.config["lastfm"]["username"],
            )

        self.listenbrainz: Optional[ListenBrainzAPI] = None
        if self.config.get("listenbrainz", {}).get("enabled", False):
            self.listenbrainz = ListenBrainzAPI(
                self.config["listenbrainz"]["username"],
                self.config["listenbrainz"].get("token"),
            )

        # Initialize AudioMuse client if enabled
        self.audiomuse_client = None
        if self.config.get("audiomuse", {}).get("enabled", False):
            audiomuse_url = self.config["audiomuse"]["url"]
            audiomuse_client = AudioMuseClient(
                base_url=audiomuse_url,
                ai_provider=self.config["audiomuse"]["ai_provider"],
                ai_model=self.config["audiomuse"]["ai_model"],
                api_key=self.config["audiomuse"]["ai_api_key"] or None
            )
            if audiomuse_client.check_health():
                logger.info("✅ AudioMuse-AI connected at %s", audiomuse_url)
                self.audiomuse_client = audiomuse_client
            else:
                logger.warning("⚠️ AudioMuse-AI not accessible at %s, falling back to LLM-only mode", audiomuse_url)
                self.audiomuse_client = None

        # Stats
        self.stats = {
            "playlists_created": 0,
            "songs_found": 0,
            "songs_downloaded": 0,
            "songs_failed": 0,
            "songs_skipped_low_rating": 0,
            "songs_skipped_duplicate": 0,
            "duplicates_prevented": 0,
            "ai_calls": 0,
        }

        # Track processed songs to avoid duplicates
        self.processed_songs: Set[Tuple[str, str]] = set()

        # Initialize service tracker
        self.service_tracker = ServiceTracker()

        # Configurable delays
        self.download_delay = self.config.get("performance", {}).get("download_delay_seconds", 10)
        self.post_scan_delay = self.config.get("performance", {}).get("post_scan_delay_seconds", 3)

    def _load_config_from_env(self) -> dict:
        """Load all configuration from environment variables"""
        logger.info("Loading configuration from environment variables...")

        # Check required variables (except AI_API_KEY which is now optional)
        required_vars = [
            "NAVIDROME_URL",
            "NAVIDROME_USER",
            "NAVIDROME_PASSWORD",
            "OCTOFIESTA_URL"
        ]

        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            logger.error("❌ Missing required environment variables: %s", ", ".join(missing))
            logger.error("")
            logger.error("Required variables:")
            logger.error("  NAVIDROME_URL       - Navidrome server URL")
            logger.error("  NAVIDROME_USER      - Navidrome username")
            logger.error("  NAVIDROME_PASSWORD  - Navidrome password")
            logger.error("  OCTOFIESTA_URL      - Octo-Fiesta server URL")
            logger.error("")
            logger.error("See ENV_VARS.md for complete reference")
            sys.exit(1)

        config = {
            "navidrome": {
                "url": os.getenv("NAVIDROME_URL"),
                "username": os.getenv("NAVIDROME_USER"),
                "password": os.getenv("NAVIDROME_PASSWORD")
            },
            "octofiesta": {
                "url": os.getenv("OCTOFIESTA_URL")
            },
            "ai": {
                "api_key": os.getenv("AI_API_KEY", ""),
                "model": os.getenv("AI_MODEL", "gemini-2.5-flash"),
                "backend": os.getenv("AI_BACKEND", "gemini"),
                "base_url": os.getenv("AI_BASE_URL"),
                "max_context_songs": self._get_env_int("AI_MAX_CONTEXT_SONGS", 500),
                "max_output_tokens": self._get_env_int("AI_MAX_OUTPUT_TOKENS", 65535)
            },
            "performance": {
                "album_batch_size": self._get_env_int("PERF_ALBUM_BATCH_SIZE", 500),
                "max_albums_scan": self._get_env_int("PERF_MAX_ALBUMS_SCAN", 10000),
                "scan_timeout": self._get_env_int("PERF_SCAN_TIMEOUT", 60),
                "download_delay_seconds": self._get_env_int("PERF_DOWNLOAD_DELAY", 6),
                "post_scan_delay_seconds": self._get_env_int("PERF_POST_SCAN_DELAY", 2)
            },
            "lastfm": {
                "enabled": self._get_env_bool("LASTFM_ENABLED", False),
                "api_key": os.getenv("LASTFM_API_KEY", ""),
                "username": os.getenv("LASTFM_USERNAME", "")
            },
            "listenbrainz": {
                "enabled": self._get_env_bool("LISTENBRAINZ_ENABLED", False),
                "username": os.getenv("LISTENBRAINZ_USERNAME", ""),
                "token": os.getenv("LISTENBRAINZ_TOKEN", "")
            },
            "audiomuse": {
                "enabled": self._get_env_bool("AUDIOMUSE_ENABLED", False),
                "url": os.getenv("AUDIOMUSE_URL", "http://localhost:8000"),
                "ai_provider": os.getenv("AUDIOMUSE_AI_PROVIDER", "gemini"),
                "ai_model": os.getenv("AUDIOMUSE_AI_MODEL", "gemini-2.5-flash"),
                "ai_api_key": os.getenv("AUDIOMUSE_AI_API_KEY", ""),
                "songs_per_mix": self._get_env_int("AUDIOMUSE_SONGS_PER_MIX", 25),
                "llm_songs_per_mix": self._get_env_int("LLM_SONGS_PER_MIX", 5)
            }
        }

        # Log configuration (without secrets)
        logger.info("✓ Navidrome: %s", config['navidrome']['url'])
        logger.info("✓ Octo-Fiesta: %s", config['octofiesta']['url'])
        if config['lastfm']['enabled']:
            logger.info("✓ Last.fm enabled: %s", config['lastfm']['username'])
        if config['listenbrainz']['enabled']:
            logger.info("✓ ListenBrainz enabled: %s", config['listenbrainz']['username'])
        if config['audiomuse']['enabled']:
            logger.info("✓ AudioMuse-AI enabled: %s", config['audiomuse']['url'])

        return config

    def _get_env_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean from environment variable"""
        value = os.getenv(key, str(default)).lower()
        return value in ('true', '1', 'yes', 'on')

    def _get_env_int(self, key: str, default: int) -> int:
        """Get integer from environment variable"""
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default

    def _validate_env_config(self) -> None:
        """Validate environment configuration"""
        errors = []
        
        # Check if at least one music source is configured
        has_ai = bool(self.config["ai"]["api_key"])
        has_audiomuse = self.config.get("audiomuse", {}).get("enabled", False)
        has_lastfm = self.config.get("lastfm", {}).get("enabled", False)
        has_listenbrainz = self.config.get("listenbrainz", {}).get("enabled", False)
        
        if not (has_ai or has_audiomuse or has_lastfm or has_listenbrainz):
            logger.error("=" * 70)
            logger.error("❌ No music source configured!")
            logger.error("❌ OctoGen requires at least one of:")
            logger.error("   1. AI_API_KEY (for LLM-based recommendations)")
            logger.error("   2. AUDIOMUSE_ENABLED=true (for AudioMuse-AI sonic analysis)")
            logger.error("   3. LASTFM_ENABLED=true (for Last.fm recommendations)")
            logger.error("   4. LISTENBRAINZ_ENABLED=true (for ListenBrainz recommendations)")
            logger.error("=" * 70)
            sys.exit(1)
        
        # Log available music sources
        sources = []
        if has_ai:
            sources.append("LLM")
        if has_audiomuse:
            sources.append("AudioMuse-AI")
        if has_lastfm:
            sources.append("Last.fm")
        if has_listenbrainz:
            sources.append("ListenBrainz")
        logger.info("✓ Music sources: %s", ", ".join(sources))
        
        # Validate URLs
        for name, url in [
            ("Navidrome", self.config["navidrome"]["url"]),
            ("Octo-Fiesta", self.config["octofiesta"]["url"])
        ]:
            if not url:
                errors.append(f"{name} URL is empty")
            elif not url.startswith(("http://", "https://")):
                errors.append(f"Invalid {name} URL: {url} (must start with http:// or https://)")
            elif url.endswith("/"):
                logger.warning("%s URL ends with '/'. This will be stripped automatically.", name)
        
        # Validate AI API key only if AI is being used
        if has_ai:
            if self.config["ai"]["api_key"] in ["your-api-key-here", "changeme", "INSERT_KEY_HERE"]:
                errors.append("AI_API_KEY appears to be a placeholder - please set a real API key")
            elif len(self.config["ai"]["api_key"]) < 20:
                errors.append("AI_API_KEY seems too short - verify it's a valid key")
        
        # Validate AI model for backend (only if AI is configured)
        if has_ai:
            backend = self.config["ai"]["backend"]
            model = self.config["ai"]["model"]
            
            if backend == "gemini" and not model.startswith("gemini"):
                logger.warning("Backend is 'gemini' but model is '%s' - this may cause errors", model)
            elif backend == "openai" and model.startswith("gemini"):
                logger.warning("Backend is 'openai' but model is '%s' - this may cause errors", model)
        
        # Validate optional services
        if self.config.get("lastfm", {}).get("enabled", False):
            if not self.config["lastfm"].get("api_key"):
                errors.append("Last.fm is enabled but LASTFM_API_KEY is empty")
            if not self.config["lastfm"].get("username"):
                errors.append("Last.fm is enabled but LASTFM_USERNAME is empty")
        
        if self.config.get("listenbrainz", {}).get("enabled", False):
            if not self.config["listenbrainz"].get("username"):
                errors.append("ListenBrainz is enabled but LISTENBRAINZ_USERNAME is empty")
        
        # Validate performance settings
        perf = self.config.get("performance", {})
        if perf.get("download_delay_seconds", 10) < 1:
            logger.warning("PERF_DOWNLOAD_DELAY is very low (%ds) - may cause issues", 
                          perf["download_delay_seconds"])
        
        # Report errors
        if errors:
            logger.error("=" * 70)
            logger.error("CONFIGURATION ERRORS FOUND:")
            logger.error("=" * 70)
            for error in errors:
                logger.error("  ❌ %s", error)
            logger.error("=" * 70)
            logger.error("Please fix the above errors and try again.")
            logger.error("See your environment variables or docker-compose.yml")
            sys.exit(1)
        
        logger.info("✅ Configuration validated successfully")

    def _check_run_cooldown(self) -> bool:
        """Check if enough time has passed since last run with smart service-based cooldown.
        
        Returns True if we should run, False if still in cooldown.
        """
        run_tracker_file = BASE_DIR / "octogen_last_run.json"
        
        # Determine cooldown periods
        schedule_cron = os.getenv("SCHEDULE_CRON", "").strip()
        
        if schedule_cron and schedule_cron.lower() not in ("manual", "false", "no", "off", "disabled"):
            # Use 90% of detected cron interval for full cooldown
            detected_interval = calculate_cron_interval(schedule_cron)
            full_cooldown_hours = detected_interval * 0.9
            logger.info("🕐 Cooldown period: %.1f hours (90%% of cron interval)", full_cooldown_hours)
        else:
            # Manual mode - use environment variable for full cooldown
            full_cooldown_hours = float(os.getenv("MIN_RUN_INTERVAL_HOURS", "6"))
            logger.info("🕐 Cooldown period: %.1f hours (manual mode)", full_cooldown_hours)
        
        # Check last run time
        if not run_tracker_file.exists():
            logger.info("✅ First run ever - no cooldown")
            return True  # First run ever
        
        try:
            with open(run_tracker_file, 'r') as f:
                data = json.load(f)
                last_run_str = data.get('last_run_timestamp')
                services = data.get('services', {})
                
                if not last_run_str:
                    logger.info("✅ No last run timestamp - allowing run")
                    return True
                
                last_run = datetime.fromisoformat(last_run_str)
                now = datetime.now(timezone.utc)
                
                # Ensure last_run is timezone-aware for comparison
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                
                hours_since_last = (now - last_run).total_seconds() / 3600
                
                # Always apply full cooldown to respect schedule
                # This prevents constant re-runs when only Last.fm/ListenBrainz succeed
                cooldown_to_apply = full_cooldown_hours
                
                if hours_since_last < cooldown_to_apply:
                    logger.info("=" * 70)
                    logger.info("⏭️  OctoGen ran %.1f hours ago (cooldown: %.1f hours)", 
                                 hours_since_last, cooldown_to_apply)
                    logger.info("⏭️  Skipping to prevent duplicate run")
                    logger.info("⏭️  Last run: %s", last_run.strftime("%Y-%m-%d %H:%M:%S"))
                    logger.info("⏭️  Next run allowed after: %s", 
                                 (last_run + timedelta(hours=cooldown_to_apply)).strftime("%Y-%m-%d %H:%M:%S"))
                    
                    # Show what services succeeded/failed last time
                    if services:
                        logger.info("⏭️  Last run services:")
                        for service_name, service_data in services.items():
                            status = "✅" if service_data.get("success") else "❌"
                            reason = f" ({service_data.get('reason')})" if not service_data.get("success") else ""
                            logger.info("⏭️    %s %s%s", status, service_name, reason)
                    
                    logger.info("=" * 70)
                    return False
                
                logger.info("✅ Cooldown passed (%.1f hours since last run)", hours_since_last)
                
                # Show what services succeeded/failed last time for context
                if services:
                    logger.info("ℹ️  Last run services:")
                    for service_name, service_data in services.items():
                        status = "✅" if service_data.get("success") else "❌"
                        reason = f" ({service_data.get('reason')})" if not service_data.get("success") else ""
                        logger.info("   %s %s%s", status, service_name, reason)
                
                return True
                
        except Exception as e:
            logger.warning("Could not read run tracker: %s", str(e))
            return True  # Allow run if we can't read tracker

    def _record_successful_run(self) -> None:
        """Record that a successful run completed with service tracking data."""
        run_tracker_file = BASE_DIR / "octogen_last_run.json"
        
        try:
            # Use single timestamp to ensure consistency
            now = datetime.now(timezone.utc)
            
            # Prepare service tracker data
            services_data = {}
            for service_name, service_info in self.service_tracker.services.items():
                services_data[service_name] = service_info
            
            # Calculate next scheduled run if SCHEDULE_CRON is set
            next_scheduled_run = None
            schedule_cron = os.getenv("SCHEDULE_CRON", "").strip()
            
            if schedule_cron and schedule_cron.lower() not in ("manual", "false", "no", "off", "disabled"):
                try:
                    # Import croniter if available
                    if CRONITER_AVAILABLE:
                        from croniter import croniter
                        cron = croniter(schedule_cron, now)
                        next_run_time = cron.get_next(datetime)
                        next_scheduled_run = next_run_time.isoformat()
                        logger.debug(f"Next scheduled run: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception as e:
                    logger.warning(f"Could not calculate next scheduled run: {e}")
            
            with open(run_tracker_file, 'w') as f:
                json.dump({
                    'last_run_timestamp': now.isoformat(),
                    'last_run_date': now.strftime("%Y-%m-%d"),
                    'last_run_formatted': now.strftime("%Y-%m-%d %H:%M:%S"),
                    'next_scheduled_run': next_scheduled_run,  # ✅ Added this!
                    'services': services_data
                }, f, indent=2)
            logger.info("✓ Recorded successful run timestamp with service tracking")
        except Exception as e:
            logger.error("Could not write run tracker: %s", str(e))

    def _is_duplicate(self, artist: str, title: str) -> bool:
        """Check if song was already processed."""
        key = (artist.lower().strip(), title.lower().strip())
        if key in self.processed_songs:
            return True
        self.processed_songs.add(key)
        return False

    def _check_and_skip_low_rating(self, song_id: str, artist: str, title: str) -> bool:
        """Check rating and return True if should skip."""
        rating = self.nd.get_song_rating(song_id)
        if LOW_RATING_MIN <= rating <= LOW_RATING_MAX:
            logger.debug("Skipping low-rated: %s - %s (%d stars)", artist, title, rating)
            self.stats["songs_skipped_low_rating"] += 1
            return True
        return False

    def _process_single_recommendation(self, rec: Dict) -> Optional[str]:
        """Process a single recommendation and return song ID if successful."""
        artist = (rec.get("artist") or "").strip()
        title = (rec.get("title") or "").strip()

        if not artist or not title:
            return None

        # Priority 1: Check for duplicates (already processed)
        if self._is_duplicate(artist, title):
            logger.debug("Skipping duplicate: %s - %s", artist, title)
            self.stats["songs_skipped_duplicate"] += 1
            return None

        # Priority 2: Search library thoroughly with fuzzy matching
        logger.debug("Checking library for: %s - %s", artist, title)
        song_id = self.nd.search_song(artist, title)

        if song_id:
            if self._check_and_skip_low_rating(song_id, artist, title):
                return None
            logger.info("Using library version: %s - %s", artist, title)
            self.stats["songs_found"] += 1
            return song_id

        # Priority 3: Check for similar songs to prevent near-duplicates
        logger.debug("Checking for similar songs: %s - %s", artist, title)
        similar_song_id = self.nd.check_for_similar_song(artist, title)
        
        if similar_song_id:
            if self._check_and_skip_low_rating(similar_song_id, artist, title):
                return None
            logger.info("Using similar song from library: %s - %s", artist, title)
            self.stats["songs_found"] += 1
            self.stats["duplicates_prevented"] += 1
            return similar_song_id

        # Priority 4: Download only if definitely not in library
        logger.info("Not in library, downloading: %s - %s", artist, title)
        
        if self.dry_run:
            return None

        success, _result = self.octo.search_and_trigger_download(artist, title)

        if not success:
            self.stats["songs_failed"] += 1
            return None

        # Wait and rescan
        time.sleep(self.download_delay)
        self.nd.trigger_scan()
        self.nd.wait_for_scan()
        time.sleep(self.post_scan_delay)

        song_id = self.nd.search_song(artist, title)

        if song_id:
            if self._check_and_skip_low_rating(song_id, artist, title):
                return None
            self.stats["songs_downloaded"] += 1
            return song_id
        else:
            self.stats["songs_failed"] += 1
            return None

    def _process_recommendations(
        self,
        playlist_name: str,
        recommendations: List[Dict],
        max_songs: int = 100,
    ) -> List[str]:
        """Process recommendations with batched scanning."""
        song_ids: List[str] = []
        needs_download = []
        total = min(len(recommendations), max_songs)
        
        logger.info("Processing playlist '%s': %d songs to check", playlist_name, total)
        
        # Phase 1: Check library and collect songs that need downloading
        for idx, rec in enumerate(recommendations[:max_songs], 1):
            artist = (rec.get("artist") or "").strip()
            title = (rec.get("title") or "").strip()
            
            if not artist or not title:
                continue
            
            # Check for duplicates
            if self._is_duplicate(artist, title):
                logger.debug("Skipping duplicate: %s - %s", artist, title)
                self.stats["songs_skipped_duplicate"] += 1
                continue
            
            # Progress logging
            if idx % 10 == 0 or idx == 1 or idx == total:
                logger.info("  [%s] Checking library: %d/%d", playlist_name, idx, total)
            
            # Search in library first
            song_id = self.nd.search_song(artist, title)
            if song_id:
                if not self._check_and_skip_low_rating(song_id, artist, title):
                    song_ids.append(song_id)
                    self.stats["songs_found"] += 1
            else:
                # Mark for download
                needs_download.append((artist, title))
        
        # Phase 2: Batch download all missing songs
        if needs_download and not self.dry_run:
            logger.info("  [%s] Downloading %d missing songs in batch...", playlist_name, len(needs_download))
            
            downloaded_count = 0
            for idx, (artist, title) in enumerate(needs_download, 1):
                if idx % 5 == 0 or idx == 1 or idx == len(needs_download):
                    logger.info("  [%s] Download progress: %d/%d", playlist_name, idx, len(needs_download))
                
                success, _result = self.octo.search_and_trigger_download(artist, title)
                if success:
                    downloaded_count += 1
            
            if downloaded_count > 0:
                # Single scan for all downloads
                logger.info("  [%s] Waiting for downloads to settle...", playlist_name)
                wait_time = self.download_delay * min(downloaded_count, 5)  # Scale wait time, max 5x
                time.sleep(wait_time)
                
                logger.info("  [%s] Triggering library scan...", playlist_name)
                self.nd.trigger_scan()
                self.nd.wait_for_scan()
                time.sleep(self.post_scan_delay)
                
                # Phase 3: Re-search for downloaded songs
                logger.info("  [%s] Checking for downloaded songs...", playlist_name)
                for artist, title in needs_download:
                    song_id = self.nd.search_song(artist, title)
                    if song_id:
                        if not self._check_and_skip_low_rating(song_id, artist, title):
                            song_ids.append(song_id)
                            self.stats["songs_downloaded"] += 1
                    else:
                        self.stats["songs_failed"] += 1
            else:
                logger.warning("  [%s] All %d download attempts failed", playlist_name, len(needs_download))
                self.stats["songs_failed"] += len(needs_download)
        
        elif needs_download and self.dry_run:
            logger.info("  [%s] [DRY RUN] Would download %d songs", playlist_name, len(needs_download))
        
        logger.info("  [%s] Complete: %d/%d songs added to playlist", 
                    playlist_name, len(song_ids), total)
        
        return song_ids



    def create_playlist(self, name: str, recommendations: List[Dict],
                       max_songs: int = 100) -> None:
        """Create a playlist from recommendations."""
        logger.info("Creating playlist: %s", name)

        if self.dry_run:
            logger.info("[DRY RUN] Would process %d recommendations", len(recommendations))
            return

        song_ids = self._process_recommendations(name, recommendations, max_songs)

        if song_ids and self.nd.create_playlist(name, song_ids):
            self.stats["playlists_created"] += 1

    def _generate_hybrid_daily_mix(
        self,
        mix_number: int,
        genre_focus: str,
        characteristics: str,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Generate a daily mix using both AudioMuse-AI and LLM
        
        Args:
            mix_number: Mix number (1-6)
            genre_focus: Main genre focus
            characteristics: Additional characteristics
            top_artists: Top artists from library
            top_genres: Top genres from library
            favorited_songs: Favorited songs for LLM context
            low_rated_songs: Low rated songs to avoid
        
        Returns:
            List of song dicts: [{"artist": "...", "title": "..."}]
        """
        songs = []
        
        # Get configuration
        audiomuse_songs_count = self.config["audiomuse"]["songs_per_mix"]
        llm_songs_count = self.config["audiomuse"]["llm_songs_per_mix"]
        
        # Get songs from AudioMuse-AI if enabled
        audiomuse_actual_count = 0
        if self.audiomuse_client:
            logger.debug(f"Requesting {audiomuse_songs_count} songs from AudioMuse-AI for Daily Mix {mix_number}")
            audiomuse_request = f"{characteristics} {genre_focus} music"
            logger.debug(f"AudioMuse request: '{audiomuse_request}'")
            audiomuse_songs = self.audiomuse_client.generate_playlist(
                user_request=audiomuse_request,
                num_songs=audiomuse_songs_count
            )
            
            # Convert AudioMuse format to Octogen format
            for song in audiomuse_songs:
                songs.append({"artist": song.get('artist', ''), "title": song.get('title', '')})
            
            audiomuse_actual_count = len(songs)
            logger.info(f"📻 Daily Mix {mix_number}: Got {audiomuse_actual_count} songs from AudioMuse-AI")
            if audiomuse_actual_count < audiomuse_songs_count:
                logger.debug(f"AudioMuse returned fewer songs than requested ({audiomuse_actual_count}/{audiomuse_songs_count})")
        
        # Get additional songs from LLM
        # If AudioMuse returned fewer songs, request more from LLM to reach target
        num_llm_songs = llm_songs_count if self.audiomuse_client else 30
        if self.audiomuse_client and audiomuse_actual_count < audiomuse_songs_count:
            # Request extra LLM songs to compensate
            shortfall = audiomuse_songs_count - audiomuse_actual_count
            num_llm_songs = llm_songs_count + shortfall
            logger.info(f"🔄 AudioMuse returned {audiomuse_actual_count}/{audiomuse_songs_count} songs, requesting {num_llm_songs} from LLM")
        
        logger.debug(f"Requesting {num_llm_songs} songs from LLM for Daily Mix {mix_number}")
        # We'll use the AI engine to generate just the LLM portion
        llm_songs = self._generate_llm_songs_for_daily_mix(
            mix_number=mix_number,
            genre_focus=genre_focus,
            characteristics=characteristics,
            num_songs=num_llm_songs,
            top_artists=top_artists,
            top_genres=top_genres,
            favorited_songs=favorited_songs,
            low_rated_songs=low_rated_songs
        )
        
        songs.extend(llm_songs)
        
        logger.info(f"🤖 Daily Mix {mix_number}: Got {len(llm_songs)} songs from LLM")
        logger.info(f"🎵 Daily Mix {mix_number}: Total {len(songs)} songs (AudioMuse: {audiomuse_actual_count}, LLM: {len(llm_songs)})")
        
        return songs[:30]  # Ensure we return exactly 30 songs

    def _generate_llm_songs_for_daily_mix(
        self,
        mix_number: int,
        genre_focus: str,
        characteristics: str,
        num_songs: int,
        top_artists: List[str],
        top_genres: List[str],
        favorited_songs: List[Dict],
        low_rated_songs: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Generate LLM songs for a specific daily mix
        
        Returns:
            List of song dicts: [{"artist": "...", "title": "..."}]
        """
        # Build a focused prompt for this specific daily mix
        artist_list = ", ".join(top_artists[:10])
        genre_list = ", ".join(top_genres[:6])
        
        # Sample of favorited songs for context
        favorited_sample = [
            f"{s.get('artist','')} - {s.get('title','')}"
            for s in favorited_songs[:50]  # Smaller sample for individual mix
        ]
        favorited_context = "\n".join(favorited_sample[:20])  # Limit to 20 for focused prompt
        
        negative_context = ""
        if low_rated_songs:
            negative_sample = [
                f"{s.get('artist','')} - {s.get('title','')}"
                for s in low_rated_songs[:20]
            ]
            negative_context = f"\n\nSONGS TO AVOID (rated {LOW_RATING_MIN}-{LOW_RATING_MAX} stars):\n" + "\n".join(negative_sample)
        
        prompt = f"""You are a music curator creating a {genre_focus} playlist.

User's music taste:
- Top artists: {artist_list}
- Top genres: {genre_list}

Sample of favorited songs:
{favorited_context}
{negative_context}

Generate {num_songs} {characteristics} {genre_focus} songs. Mix library favorites with new discoveries.

Return ONLY valid JSON array:
[
  {{"artist": "Artist Name", "title": "Song Title"}},
  {{"artist": "Artist Name", "title": "Song Title"}}
]

CRITICAL RULES:
- Both "artist" and "title" required
- Double quotes for ALL strings
- No trailing commas
- NEVER recommend avoided songs
- No markdown, just raw JSON array
- ESCAPE ALL BACKSLASHES: Use \\\\ not \\
"""
        
        try:
            if self.ai.backend == "gemini":
                if not GEMINI_SDK_AVAILABLE:
                    logger.error("Gemini backend required but not available")
                    return []
                
                from google.genai import types
                response = self.ai.genai_client.models.generate_content(
                    model=self.ai.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=1.0,
                        max_output_tokens=4096
                    )
                )
                content = response.text
            else:
                # OpenAI-compatible API
                response = self.ai.client.chat.completions.create(
                    model=self.ai.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=1.0,
                    max_tokens=4096
                )
                content = response.choices[0].message.content
            
            # Clean JSON
            content = re.sub(r'^```(?:json)?\s*', '', content, flags=re.MULTILINE)
            content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
            content = content.strip()
            
            # Extract JSON array
            json_start = content.find('[')
            json_end = content.rfind(']')
            if json_start != -1 and json_end != -1:
                content = content[json_start:json_end + 1]
            
            songs = json.loads(content)
            
            if not isinstance(songs, list):
                logger.error("LLM response is not a JSON array")
                return []
            
            # Validate songs
            valid_songs = [
                song for song in songs
                if isinstance(song, dict) and "artist" in song and "title" in song
            ]
            
            return valid_songs[:num_songs]
            
        except Exception as e:
            logger.error(f"Failed to generate LLM songs for Daily Mix {mix_number}: {e}")
            return []


    def run(self) -> None:
        """Run the main discovery engine."""
        start_time = datetime.now()

        write_health_status("starting", "Initializing OctoGen")
        
        logger.info("=" * 70)
        logger.info("OCTOGEN - Starting: %s", start_time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("=" * 70)
    
        try:

            write_health_status("running", "Analyzing music library")
            # Analyze library
            logger.info("Analyzing music library...")
            logger.debug("Fetching starred songs from Navidrome")
            favorited_songs = self.nd.get_starred_songs()
    
            if not favorited_songs:
                logger.warning("No starred songs found - library analysis limited")
                logger.debug("Continuing with alternative music sources")
    
            # Generate AI playlists (only if AI is configured)
            all_playlists = {}
            if self.ai and favorited_songs:
                logger.debug("AI engine is configured, proceeding with AI generation")
                # Continue with normal AI generation
                top_artists = self.nd.get_top_artists(100)
                top_genres = self.nd.get_top_genres(20)
                low_rated_songs = self.nd.get_low_rated_songs()
    
                logger.info("Library: %d favorited songs", len(favorited_songs))
                logger.info("Top artists: %s", ", ".join(top_artists[:5]))
                logger.info("Top genres: %s", ", ".join(top_genres[:5]))
                logger.info("Songs to avoid: %d (rated %d-%d stars)",
                           len(low_rated_songs), LOW_RATING_MIN, LOW_RATING_MAX)
                logger.debug(f"Library analysis complete: {len(top_artists)} artists, {len(top_genres)} genres")
    
                # Generate AI playlists
                logger.info("=" * 70)
                logger.info("AI CALL LIMIT: %d maximum", self.ai.max_calls)
                logger.info("=" * 70)
    
                all_playlists, ai_error = self.ai.generate_all_playlists(
                    top_artists,
                    top_genres,
                    favorited_songs,
                    low_rated_songs
                )
    
                self.stats["ai_calls"] = self.ai.call_count
                logger.debug(f"AI generation complete, made {self.ai.call_count} API calls")
                
                # Track AI service outcome
                if ai_error:
                    self.service_tracker.record_service(
                        "ai_playlists",
                        success=False,
                        reason=ai_error,
                        api_calls=self.ai.call_count
                    )
                    logger.warning("AI service failed: %s", ai_error)
                else:
                    playlist_count = len(all_playlists)
                    song_count = sum(len(songs) for songs in all_playlists.values())
                    self.service_tracker.record_service(
                        "ai_playlists",
                        success=True,
                        playlists=playlist_count,
                        songs=song_count,
                        api_calls=self.ai.call_count
                    )
                    logger.info("AI service succeeded: %d playlists, %d songs", playlist_count, song_count)
            elif not self.ai:
                logger.info("=" * 70)
                logger.info("AI not configured - using alternative music sources only")
                logger.info("=" * 70)
                logger.debug("Setting up library data for alternative sources")
                # Set required variables for alternative sources
                top_artists = self.nd.get_top_artists(100) if favorited_songs else []
                top_genres = self.nd.get_top_genres(20) if favorited_songs else []
                low_rated_songs = self.nd.get_low_rated_songs() if favorited_songs else []
            else:
                logger.info("=" * 70)
                logger.info("No starred songs - skipping AI generation")
                logger.info("=" * 70)
                logger.debug("No library data available for analysis")
                top_artists = []
                top_genres = []
                low_rated_songs = []
    
            # Check if we have any music sources available
            if not all_playlists and not self.audiomuse_client and not self.lastfm and not self.listenbrainz:
                logger.error("=" * 70)
                logger.error("❌ No playlists generated and no alternative services configured")
                logger.error("❌ Nothing to process - exiting with error")
                logger.error("=" * 70)
                logger.debug("Available sources check: AI=%s, AudioMuse=%s, Last.fm=%s, ListenBrainz=%s",
                           bool(all_playlists), bool(self.audiomuse_client), bool(self.lastfm), bool(self.listenbrainz))
                write_health_status("unhealthy", "No music sources available")
                sys.exit(1)
    
                if all_playlists:
                    # Handle hybrid playlists if AudioMuse is enabled
                    if self.audiomuse_client:
                        logger.info("=" * 70)
                        logger.info("GENERATING HYBRID PLAYLISTS (AudioMuse + LLM)")
                        logger.info("=" * 70)
                        
                        playlists_before_audiomuse = self.stats["playlists_created"]
                        
                        # Define all hybrid playlist configurations (everything except Discovery)
                        hybrid_playlist_configs = [
                            # Daily Mixes
                            {"name": "Daily Mix 1", "genre": top_genres[0] if len(top_genres) > 0 else DEFAULT_DAILY_MIX_GENRES[0], "characteristics": "energetic", "num": 1},
                            {"name": "Daily Mix 2", "genre": top_genres[1] if len(top_genres) > 1 else DEFAULT_DAILY_MIX_GENRES[1], "characteristics": "catchy upbeat", "num": 2},
                            {"name": "Daily Mix 3", "genre": top_genres[2] if len(top_genres) > 2 else DEFAULT_DAILY_MIX_GENRES[2], "characteristics": "danceable rhythmic", "num": 3},
                            {"name": "Daily Mix 4", "genre": top_genres[3] if len(top_genres) > 3 else DEFAULT_DAILY_MIX_GENRES[3], "characteristics": "rhythmic bass-heavy", "num": 4},
                            {"name": "Daily Mix 5", "genre": top_genres[4] if len(top_genres) > 4 else DEFAULT_DAILY_MIX_GENRES[4], "characteristics": "alternative atmospheric", "num": 5},
                            {"name": "Daily Mix 6", "genre": top_genres[5] if len(top_genres) > 5 else DEFAULT_DAILY_MIX_GENRES[5], "characteristics": "smooth melodic", "num": 6},
                            # Mood/Activity playlists
                            {"name": "Chill Vibes", "genre": "ambient", "characteristics": "relaxing calm peaceful", "num": 8},
                            {"name": "Workout Energy", "genre": "high-energy", "characteristics": "upbeat motivating intense", "num": 9},
                            {"name": "Focus Flow", "genre": "instrumental", "characteristics": "ambient atmospheric concentration", "num": 10},
                            {"name": "Drive Time", "genre": "upbeat", "characteristics": "driving energetic feel-good", "num": 11}
                        ]
                        
                        # Generate and create hybrid playlists
                        for mix_config in hybrid_playlist_configs:
                            hybrid_songs = self._generate_hybrid_daily_mix(
                                mix_number=mix_config["num"],
                                genre_focus=mix_config["genre"],
                                characteristics=mix_config["characteristics"],
                                top_artists=top_artists,
                                top_genres=top_genres,
                                favorited_songs=favorited_songs,
                                low_rated_songs=low_rated_songs
                            )
                            
                            if hybrid_songs:
                                self.create_playlist(mix_config["name"], hybrid_songs, max_songs=30)
                        
                        # Track AudioMuse service
                        audiomuse_playlists = self.stats["playlists_created"] - playlists_before_audiomuse
                        self.service_tracker.record_service(
                            "audiomuse",
                            success=True,
                            playlists=audiomuse_playlists
                        )
                        logger.info("AudioMuse-AI service succeeded: %d playlists", audiomuse_playlists)
                        
                        # Create Discovery from AI response (LLM-only for new discoveries)
                        if "Discovery" in all_playlists:
                            discovery_songs = all_playlists["Discovery"]
                            if isinstance(discovery_songs, list) and discovery_songs:
                                logger.info("=" * 70)
                                logger.info("DISCOVERY (LLM-only for new discoveries)")
                                logger.info("=" * 70)
                                self.create_playlist("Discovery", discovery_songs, max_songs=50)
                    else:
                        # Original behavior: use all AI-generated playlists
                        for playlist_name, songs in all_playlists.items():
                            if isinstance(songs, list) and songs:
                                self.create_playlist(playlist_name, songs, max_songs=100)

            
            # External services (run regardless of starred songs)
            if self.lastfm:
                logger.info("=" * 70)
                logger.info("LAST.FM RECOMMENDATIONS")
                logger.info("=" * 70)
                try:
                    playlists_before = self.stats["playlists_created"]
                    recs = self.lastfm.get_recommended_tracks(50)
                    if recs:
                        self.create_playlist("Last.fm Recommended", recs, 50)
                    playlists_created = self.stats["playlists_created"] - playlists_before
                    
                    self.service_tracker.record_service(
                        "lastfm",
                        success=True,
                        playlists=playlists_created,
                        songs=len(recs) if recs else 0
                    )
                    logger.info("Last.fm service succeeded: %d playlists, %d songs", playlists_created, len(recs) if recs else 0)
                except Exception as e:
                    self.service_tracker.record_service(
                        "lastfm",
                        success=False,
                        reason=str(e)[:100]
                    )
                    logger.warning("Last.fm service failed: %s", e)
    
            if self.listenbrainz:
                logger.info("Creating ListenBrainz 'Created For You' playlists...")
                try:
                    playlists_before = self.stats["playlists_created"]
                    lb_playlists = self.listenbrainz.get_created_for_you_playlists()
                    
                    for lb_playlist in lb_playlists:
                        # The data is nested inside a "playlist" key
                        playlist_data = lb_playlist.get("playlist", {})
                        playlist_name = playlist_data.get("title", "Unknown")
                        
                        # Get the identifier from the nested structure
                        playlist_mbid = None
                        if "identifier" in playlist_data:
                            identifier = playlist_data["identifier"]
                            # identifier might be a string or a list
                            if isinstance(identifier, str):
                                playlist_mbid = identifier.split("/")[-1]
                            elif isinstance(identifier, list) and len(identifier) > 0:
                                playlist_mbid = identifier[0].split("/")[-1]
                        
                        if not playlist_mbid:
                            logger.error("Cannot find playlist ID for: %s", playlist_name)
                            continue
                        
                        # Determine if this is current week or last week
                        renamed_playlist = None
                        should_process = True
                        
                        if "Weekly Exploration" in playlist_name and "week of" in playlist_name:
                            try:
                                # Extract the date string
                                date_part = playlist_name.split("week of ")[1].split()[0]  # Gets "2026-02-09"
                                playlist_date = datetime.strptime(date_part, "%Y-%m-%d")
                                
                                # Calculate start of current week (Monday)
                                today = datetime.now()
                                start_of_this_week = today - timedelta(days=today.weekday())
                                start_of_last_week = start_of_this_week - timedelta(days=7)
                                
                                # Compare dates (ignoring time)
                                playlist_week_start = playlist_date.replace(hour=0, minute=0, second=0, microsecond=0)
                                this_week_start = start_of_this_week.replace(hour=0, minute=0, second=0, microsecond=0)
                                last_week_start = start_of_last_week.replace(hour=0, minute=0, second=0, microsecond=0)
                                
                                if playlist_week_start == this_week_start:
                                    renamed_playlist = "LB: Weekly Exploration"
                                elif playlist_week_start == last_week_start:
                                    renamed_playlist = "LB: Last Week's Exploration"
                                else:
                                    # Older than 2 weeks - skip
                                    logger.info("Skipping old Weekly Exploration: %s (keeping only last 2 weeks)", playlist_name)
                                    should_process = False
                            except Exception as e:
                                logger.warning("Could not parse date from playlist: %s", playlist_name)
                                renamed_playlist = f"LB: {playlist_name}"
                        else:
                            # Non-weekly playlists (Daily Jams, etc.)
                            renamed_playlist = f"LB: {playlist_name}"
                        
                        if not should_process:
                            continue
                        
                        logger.info("Processing: %s -> %s (MBID: %s)", playlist_name, renamed_playlist, playlist_mbid)
                        tracks = self.listenbrainz.get_playlist_tracks(playlist_mbid)
                        
                        # Process songs with download support (limit to 50)
                        found_ids = []
                        for track in tracks[:50]:
                            # Use the same processing as AI recommendations (includes download)
                            song_id = self._process_single_recommendation(track)
                            if song_id:
                                found_ids.append(song_id)
                        
                        if found_ids:
                            self.nd.create_playlist(renamed_playlist, found_ids)
                    
                    playlists_created = self.stats["playlists_created"] - playlists_before
                    
                    self.service_tracker.record_service(
                        "listenbrainz",
                        success=True,
                        playlists=playlists_created
                    )
                    logger.info("ListenBrainz service succeeded: %d playlists", playlists_created)
                except Exception as e:
                    self.service_tracker.record_service(
                        "listenbrainz",
                        success=False,
                        reason=str(e)[:100]
                    )
                    logger.warning("ListenBrainz service failed: %s", e)
    
            # Time-Period Playlist Generation (NEW FEATURE)
            try:
                from octogen.scheduler.timeofday import (
                    should_regenerate_period_playlist,
                    get_current_period,
                    get_period_display_name,
                    get_time_context,
                    record_period_playlist_generation,
                    get_period_playlist_size
                )
                
                should_generate, reason = should_regenerate_period_playlist(BASE_DIR)
                
                if should_generate:
                    logger.info("=" * 70)
                    logger.info("TIME-OF-DAY PLAYLIST GENERATION")
                    logger.info("=" * 70)
                    
                    current_period = get_current_period()
                    playlist_name = get_period_display_name(current_period)
                    time_context = get_time_context(current_period)
                    playlist_size = get_period_playlist_size()
                    
                    logger.info(f"Period: {time_context.get('description')}")
                    logger.info(f"Mood: {time_context.get('mood')}")
                    logger.info(f"Playlist: {playlist_name}")
                    logger.info(f"Reason: {reason}")
                    
                    # Delete old period playlists first
                    try:
                        all_playlists_in_navidrome = self.nd.get_all_playlists()
                        period_patterns = ["Morning Mix", "Afternoon Flow", "Evening Chill", "Night Vibes"]
                        
                        for nd_playlist in all_playlists_in_navidrome:
                            nd_playlist_name = nd_playlist.get("name", "")
                            # Delete if it's a time-period playlist but not the current one
                            if any(pattern in nd_playlist_name for pattern in period_patterns) and nd_playlist_name != playlist_name:
                                playlist_id = nd_playlist.get("id")
                                if playlist_id:
                                    logger.info(f"🗑️  Deleting old period playlist: {nd_playlist_name}")
                                    self.nd.delete_playlist(playlist_id)
                    except Exception as e:
                        logger.warning(f"Could not delete old period playlists: {e}")
                    
                    # Generate the time-period playlist
                    # NEW REQUIREMENT: Use AudioMuse for 25 songs, LLM for 5 songs
                    period_songs = []
                    
                    # Get 25 songs from AudioMuse if enabled
                    if self.audiomuse_client:
                        logger.info("🎵 Generating 25 songs via AudioMuse-AI...")
                        try:
                            if favorited_songs:
                                # Use random seed from favorited songs
                                seed_song = favorited_songs[len(favorited_songs) // 2]
                                # Build a natural language request for AudioMuse
                                mood = time_context.get("mood", "")
                                request_text = f"{mood} music similar to {seed_song.get('title', '')} by {seed_song.get('artist', '')}"
                                audiomuse_songs = self.audiomuse_client.generate_playlist(
                                    user_request=request_text,
                                    num_songs=25
                                )
                                
                                if audiomuse_songs:
                                    period_songs.extend(audiomuse_songs[:25])
                                    logger.info(f"✓ Got {len(audiomuse_songs[:25])} songs from AudioMuse")
                        except Exception as e:
                            logger.warning(f"AudioMuse generation failed: {e}")
                    
                    # Get 5 songs from LLM
                    if self.ai and favorited_songs:
                        logger.info("🤖 Generating 5 songs via LLM...")
                        try:
                            # Build a special prompt for time-period playlist
                            llm_prompt = f"""Generate exactly 5 new song recommendations for a {playlist_name}.

Time context: {time_context.get('description')}
Mood: {time_context.get('mood')}
Energy level: {time_context.get('energy')}

{time_context.get('guidance')}

Return ONLY valid JSON:
{{
  "songs": [
    {{"artist": "Artist Name", "title": "Song Title"}},
    {{"artist": "Artist Name", "title": "Song Title"}}
  ]
}}

CRITICAL RULES:
- Exactly 5 songs
- Both "artist" and "title" required
- Double quotes for ALL strings
- No trailing commas
- No markdown, just raw JSON
"""
                            
                            # Use simplified AI call for just 5 songs
                            if self.ai.backend == "gemini" and hasattr(self.ai, 'genai_client'):
                                from google.genai import types
                                response = self.ai.genai_client.models.generate_content(
                                    model=self.ai.model,
                                    contents=llm_prompt,
                                    config=types.GenerateContentConfig(
                                        temperature=0.9,
                                        max_output_tokens=1000,
                                        response_mime_type="application/json"
                                    )
                                )
                                llm_response = response.text
                            else:
                                # OpenAI-compatible
                                response = self.ai.client.chat.completions.create(
                                    model=self.ai.model,
                                    messages=[{"role": "user", "content": llm_prompt}],
                                    temperature=0.9,
                                    max_tokens=1000,
                                    response_format={"type": "json_object"}
                                )
                                llm_response = response.choices[0].message.content
                            
                            # Parse response
                            import json
                            llm_data = json.loads(llm_response)
                            llm_songs = llm_data.get("songs", [])
                            
                            if llm_songs:
                                period_songs.extend(llm_songs[:5])
                                logger.info(f"✓ Got {len(llm_songs[:5])} songs from LLM")
                        except Exception as e:
                            logger.warning(f"LLM generation failed: {e}")
                    
                    # Create the playlist if we have songs
                    if period_songs:
                        logger.info(f"Creating {playlist_name} with {len(period_songs)} songs...")
                        self.create_playlist(playlist_name, period_songs, max_songs=playlist_size)
                        
                        # Record generation
                        record_period_playlist_generation(current_period, playlist_name, BASE_DIR)
                        
                        # Track in service summary
                        self.service_tracker.record_service(
                            "timeofday_playlist",
                            success=True,
                            playlists=1,
                            songs=len(period_songs),
                            period=current_period
                        )
                        logger.info(f"✅ Time-of-day playlist created: {playlist_name}")
                    else:
                        logger.warning("No songs generated for time-period playlist")
                        self.service_tracker.record_service(
                            "timeofday_playlist",
                            success=False,
                            reason="No songs generated"
                        )
                else:
                    logger.info(f"⏭️  Skipping time-period playlist: {reason}")
                    
            except Exception as e:
                logger.warning(f"Time-period playlist generation failed: {e}")
                if hasattr(self, 'service_tracker'):
                    self.service_tracker.record_service(
                        "timeofday_playlist",
                        success=False,
                        reason=str(e)[:100]
                    )
    
            # Service Execution Summary
            logger.info("=" * 70)
            logger.info("SERVICE EXECUTION SUMMARY")
            logger.info("=" * 70)
            
            for service_name, service_data in self.service_tracker.services.items():
                if service_data.get("success"):
                    playlists = service_data.get("playlists", 0)
                    songs = service_data.get("songs", 0)
                    api_calls = service_data.get("api_calls", "")
                    
                    service_display = {
                        "ai_playlists": "AI Playlists",
                        "audiomuse": "AudioMuse-AI",
                        "lastfm": "Last.fm",
                        "listenbrainz": "ListenBrainz",
                        "timeofday_playlist": "Time-of-Day Playlist"
                    }.get(service_name, service_name)
                    
                    if api_calls:
                        logger.info("✅ %s: %d playlists created (%d API calls)", service_display, playlists, api_calls)
                    elif songs:
                        logger.info("✅ %s: %d playlists created (%d songs)", service_display, playlists, songs)
                    else:
                        logger.info("✅ %s: %d playlists created", service_display, playlists)
                else:
                    reason = service_data.get("reason", "unknown")
                    service_display = {
                        "ai_playlists": "AI Playlists",
                        "audiomuse": "AudioMuse-AI",
                        "lastfm": "Last.fm",
                        "listenbrainz": "ListenBrainz",
                        "timeofday_playlist": "Time-of-Day Playlist"
                    }.get(service_name, service_name)
                    
                    logger.warning("❌ %s: FAILED (reason: %s)", service_display, reason)
            
            logger.info("=" * 70)
            
            # Summary
            elapsed = datetime.now() - start_time
            logger.info("=" * 70)
            logger.info("COMPLETED")
            write_health_status("healthy", f"Last run completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 70)
            logger.info("Total time: %dm %ds", elapsed.seconds // 60, elapsed.seconds % 60)
            if self.ai:
                logger.info("AI API calls: %d / %d", self.stats["ai_calls"], self.ai.max_calls)
            else:
                logger.info("AI: Not configured")
            logger.info("Playlists created: %d", self.stats["playlists_created"])
            logger.info("Songs in library: %d", self.stats["songs_found"])
            logger.info("Songs downloaded: %d", self.stats["songs_downloaded"])
            logger.info("Near-duplicates avoided: %d", self.stats["duplicates_prevented"])
            logger.info("Songs skipped (low rating): %d", self.stats["songs_skipped_low_rating"])
            logger.info("Songs skipped (duplicate): %d", self.stats["songs_skipped_duplicate"])
            logger.info("Songs failed: %d", self.stats["songs_failed"])
            logger.info("=" * 70)
            
            # Record successful run
            self._record_successful_run()
    
        except Exception as e:
           write_health_status("unhealthy", f"Error: {str(e)[:200]}")
           logger.error("Fatal error: %s", e, exc_info=True)
           sys.exit(1)


# ============================================================================
# SCHEDULING SUPPORT
# ============================================================================

def calculate_next_run(cron_expression: str) -> datetime:
    """Calculate next run time from cron expression."""
    if not CRONITER_AVAILABLE:
        logger.error("croniter not installed. Run: pip install croniter")
        sys.exit(1)

    try:
        cron = croniter(cron_expression, datetime.now())
        next_run = cron.get_next(datetime)
        return next_run
    except Exception as e:
        logger.error("Invalid cron expression '%s': %s", cron_expression, e)
        sys.exit(1)

def wait_until(target_time: datetime) -> None:
    """Wait until target time, logging countdown."""
    while True:
        now = datetime.now()
        if now >= target_time:
            break

        remaining = (target_time - now).total_seconds()
        if remaining <= 0:
            break

        # Log countdown at intervals
        if remaining > 3600:  # More than 1 hour
            logger.info("⏰ Next run in %.1f hours (%s)", 
                       remaining / 3600, target_time.strftime("%Y-%m-%d %H:%M:%S"))
            time.sleep(min(1800, remaining))  # Check every 30 min
        elif remaining > 60:  # More than 1 minute
            logger.info("⏰ Next run in %.1f minutes", remaining / 60)
            time.sleep(min(30, remaining))  # Check every 30 sec
        else:
            logger.info("⏰ Next run in %.0f seconds", remaining)
            time.sleep(min(10, remaining))  # Check every 10 sec

def calculate_cron_interval(cron_expression: str) -> float:
    """Calculate shortest interval (in hours) between cron runs.
    
    Returns the minimum time between consecutive executions.
    For example: '0 */6 * * *' returns 6.0 hours
    """
    if not CRONITER_AVAILABLE:
        return 6.0  # Default fallback
    
    try:
        from croniter import croniter
        cron = croniter(cron_expression, datetime.now(timezone.utc))
        
        # Get next 10 run times to find shortest interval
        runs = [cron.get_next(datetime) for _ in range(10)]
        intervals = [(runs[i+1] - runs[i]).total_seconds() / 3600 
                     for i in range(len(runs)-1)]
        
        min_interval = min(intervals)
        logger.info("📊 Detected cron interval: %.1f hours", min_interval)
        return min_interval
        
    except Exception as e:
        logger.warning("Could not parse cron expression '%s': %s", cron_expression, e)
        return 6.0  # Default fallback

def run_with_schedule(dry_run: bool = False):
    """Run engine with optional cron scheduling."""
    schedule_cron = os.getenv("SCHEDULE_CRON", "").strip()

    # Check if scheduling is disabled
    if not schedule_cron or schedule_cron.lower() in ("manual", "false", "no", "off", "disabled"):
        logger.info("🔧 Running in manual mode (no schedule)")
        engine = OctoGenEngine(dry_run=dry_run)
        
        # Check cooldown before running in manual mode
        if not engine._check_run_cooldown():
            write_health_status("skipped", "Cooldown active - skipping run")
            logger.info("💤 Sleeping %ds before exit to prevent rapid restarts", COOLDOWN_EXIT_DELAY_SECONDS)
            time.sleep(COOLDOWN_EXIT_DELAY_SECONDS)
            sys.exit(0)  # Clean exit - not an error
        
        engine.run()
        return

    # Validate croniter is available
    if not CRONITER_AVAILABLE:
        logger.error("❌ SCHEDULE_CRON is set but croniter is not installed")
        logger.error("Run: pip install croniter")
        logger.error("Or unset SCHEDULE_CRON for manual mode")
        sys.exit(1)

    # Scheduled mode
    print("")  # Blank line after banner
    logger.info("═" * 70)
    logger.info("🕐 OCTOGEN SCHEDULER")
    logger.info("═" * 70)
    logger.info("Schedule: %s", schedule_cron)
    logger.info("Timezone: %s", os.getenv("TZ", "UTC (default)"))
    logger.info("═" * 70)

    run_count = 0

    while True:
        try:
            # Calculate next run time
            next_run = calculate_next_run(schedule_cron)
            logger.info("📅 Next scheduled run: %s", next_run.strftime("%Y-%m-%d %H:%M:%S"))
            write_health_status("scheduled", f"Waiting for next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

            # Wait until next run
            wait_until(next_run)

            # Execute
            run_count += 1
            logger.info("═" * 70)
            logger.info("🚀 SCHEDULED RUN #%d - %s", run_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logger.info("═" * 70)

            engine = OctoGenEngine(dry_run=dry_run)
            
            # Check cooldown before running in scheduled mode
            if not engine._check_run_cooldown():
                logger.info("⏭️ Cooldown active, waiting for next scheduled run")
                write_health_status("scheduled", "Cooldown active - waiting for next schedule")
                continue  # Continue to scheduler loop, don't exit
            
            engine.run()

            logger.info("✅ Scheduled run #%d completed successfully", run_count)

        except KeyboardInterrupt:
            logger.info("⚠️  Scheduler interrupted by user")
            break
        except Exception as e:
            logger.error("❌ Scheduled run failed: %s", e, exc_info=True)
            # Continue scheduling despite errors
            logger.info("🔄 Will retry on next scheduled run")
            time.sleep(60)  # Wait 1 minute before recalculating


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main() -> None:
    """Main entry point."""
    import argparse
    
    # Initialize metrics if available and enabled
    if MODULES_AVAILABLE:
        try:
            metrics_enabled = os.getenv("METRICS_ENABLED", "true").lower() == "true"
            metrics_port = int(os.getenv("METRICS_PORT", "9090"))
            if metrics_enabled:
                setup_metrics(enabled=True, port=metrics_port)
                logger.info(f"Prometheus metrics enabled on port {metrics_port}")
        except Exception as e:
            logger.warning(f"Failed to initialize metrics: {e}")
    
    # Start web UI if enabled
    web_enabled = os.getenv("WEB_ENABLED", "true").lower() not in ("false", "no", "off", "disabled")
    if web_enabled and MODULES_AVAILABLE:
        try:
            from octogen.web.app import start_web_server
            
            web_port = int(os.getenv("WEB_PORT", "5000"))
            
            # Start web server in background thread
            web_thread = start_web_server(port=web_port, data_dir=BASE_DIR, threaded=True)
            
            if web_thread:
                logger.info(f"🌐 Web UI started on port {web_port}")
                logger.info(f"🌐 Access dashboard at http://localhost:{web_port}")
            
        except Exception as e:
            logger.warning(f"Failed to start web UI: {e}")
            logger.warning("Continuing without web UI...")

    print_banner()

    parser = argparse.ArgumentParser(
        description="OctoGen - AI-Powered Music Discovery for Navidrome",
        epilog="Configure via environment variables - see ENV_VARS.md"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making downloads or playlist changes"
    )

    args = parser.parse_args()

    lock = acquire_lock()

    try:
        engine = OctoGenEngine(dry_run=args.dry_run)
        engine.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error("Startup failed: %s", e, exc_info=True)
        sys.exit(1)
