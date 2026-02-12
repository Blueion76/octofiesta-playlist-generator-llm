#!/usr/bin/env python3
"""OctoGen - AI-Powered Music Discovery Engine for Navidrome

Docker Edition with Environment Variable Configuration + Built-in Scheduling

Features:
- AI recommendations (Gemini, OpenAI, Groq, Ollama, etc.)
- Automatic downloads via Octo-Fiesta
- Star rating integration (excludes 1-2 star songs)
- Daily cache for performance
- Last.fm and ListenBrainz integration
- Async operations for speed
- Zero config files - pure environment variables
- Built-in cron scheduling
"""

import sys
import os
import json
import logging
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter
from urllib.parse import urlencode

# Try to import croniter for scheduling support
try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False

try:
    from openai import OpenAI
except ImportError:
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
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Constants
LOW_RATING_MIN = 1
LOW_RATING_MAX = 2

# ============================================================================
# BANNER
# ============================================================================

def print_banner():
    """Print OctoGen banner"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ██████╗  ██████╗████████╗ ██████╗  ██████╗ ███████╗███╗   ██╗   ║
║  ██╔═══██╗██╔════╝╚══██╔══╝██╔═══██╗██╔════╝ ██╔════╝████╗  ██║   ║
║  ██║   ██║██║        ██║   ██║   ██║██║  ███╗█████╗  ██╔██╗ ██║   ║
║  ██║   ██║██║        ██║   ██║   ██║██║   ██║██╔══╝  ██║╚██╗██║   ║
║  ╚██████╔╝╚██████╗   ██║   ╚██████╔╝╚██████╔╝███████╗██║ ╚████║   ║
║   ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ║
║                                                           ║
║         AI-Powered Music Discovery for Navidrome         ║
║                     Docker Edition                       ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
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



class OctoFiestarrTrigger:
    """Triggers octo-fiestarr downloads via Subsonic endpoints."""

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

    def search_song(self, artist: str, title: str) -> Optional[str]:
        """Search for a song and return its ID."""
        response = self._request("search3", {"query": f'"{title}"', "songCount": 20})

        if not response:
            return None

        songs = response.get("searchResult3", {}).get("song", [])

        artist_lower = artist.lower().strip()
        title_lower = title.lower().strip()

        for song in songs:
            song_artist = song.get("artist", "").lower().strip()
            song_title = song.get("title", "").lower().strip()

            if (artist_lower in song_artist or song_artist in artist_lower) and (
                title_lower in song_title or song_title in title_lower
            ):
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

1. "Discovery Weekly" (50 songs): 45 new discoveries + 5 library
{chr(10).join(genre_instructions)}
8. "Chill Vibes" (30 songs): 25 library + 5 new relaxing
9. "Workout Energy" (30 songs): 25 library + 5 new high-energy
10. "Focus Flow" (30 songs): 25 library + 5 new ambient/instrumental
11. "Drive Time" (30 songs): 25 library + 5 new upbeat

Return ONLY valid JSON:
{{
  "Discovery Weekly": [
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
    ) -> Dict[str, List[Dict]]:
        """Generate playlists using configured backend."""
        if self.response_cache is not None:
            logger.info("Using cached AI response")
            return self.response_cache

        if self.call_count >= self.max_calls:
            logger.error("AI call limit reached (%d)", self.max_calls)
            return {}

        logger.info("Making AI API call (%d/%d)...", self.call_count + 1, self.max_calls)
        self.call_count += 1

        try:
            if self.backend == "gemini":
                content = self._generate_with_gemini(
                    top_artists, top_genres, favorited_songs, low_rated_songs
                )
            else:
                content = self._generate_with_openai(
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
                return {}

            all_playlists = json.loads(content)

            if not isinstance(all_playlists, dict):
                logger.error("AI response is not a JSON object")
                return {}

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

            total = sum(len(songs) for songs in all_playlists.values())
            logger.info("Generated %d playlists (%d songs)", len(all_playlists), total)
            return all_playlists

        except json.JSONDecodeError as e:
            logger.error("JSON parse error at line %d col %d: %s", e.lineno, e.colno, e.msg)
            return {}
        except Exception as e:
            logger.error("AI request failed: %s", str(e)[:200])
            return {}

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

        self.octo = OctoFiestarrTrigger(
            self.config["octofiestarr"]["url"],
            self.config["navidrome"]["username"],
            self.config["navidrome"]["password"],
            dry_run=dry_run
        )

        # Initialize AI engine
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

        # Stats
        self.stats = {
            "playlists_created": 0,
            "songs_found": 0,
            "songs_downloaded": 0,
            "songs_failed": 0,
            "songs_skipped_low_rating": 0,
            "songs_skipped_duplicate": 0,
            "ai_calls": 0,
        }

        # Track processed songs to avoid duplicates
        self.processed_songs: Set[Tuple[str, str]] = set()

        # Configurable delays
        self.download_delay = self.config.get("performance", {}).get("download_delay_seconds", 10)
        self.post_scan_delay = self.config.get("performance", {}).get("post_scan_delay_seconds", 3)

    def _load_config_from_env(self) -> dict:
        """Load all configuration from environment variables"""
        logger.info("Loading configuration from environment variables...")

        # Check required variables
        required_vars = [
            "NAVIDROME_URL",
            "NAVIDROME_USER",
            "NAVIDROME_PASSWORD",
            "OCTOFIESTA_URL",
            "AI_API_KEY"
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
            logger.error("  AI_API_KEY          - Gemini/OpenAI API key")
            logger.error("")
            logger.error("See ENV_VARS.md for complete reference")
            sys.exit(1)

        config = {
            "navidrome": {
                "url": os.getenv("NAVIDROME_URL"),
                "username": os.getenv("NAVIDROME_USER"),
                "password": os.getenv("NAVIDROME_PASSWORD")
            },
            "octofiestarr": {
                "url": os.getenv("OCTOFIESTA_URL")
            },
            "ai": {
                "api_key": os.getenv("AI_API_KEY"),
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
            }
        }

        # Log configuration (without secrets)
        logger.info("✓ Navidrome: %s", config['navidrome']['url'])
        logger.info("✓ Octo-Fiesta: %s", config['octofiestarr']['url'])
        if config['lastfm']['enabled']:
            logger.info("✓ Last.fm enabled: %s", config['lastfm']['username'])
        if config['listenbrainz']['enabled']:
            logger.info("✓ ListenBrainz enabled: %s", config['listenbrainz']['username'])

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
        logger.info("✅ Configuration loaded from environment variables")

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

        # Check for duplicates
        if self._is_duplicate(artist, title):
            logger.debug("Skipping duplicate: %s - %s", artist, title)
            self.stats["songs_skipped_duplicate"] += 1
            return None

        # Search library
        song_id = self.nd.search_song(artist, title)

        if song_id:
            if self._check_and_skip_low_rating(song_id, artist, title):
                return None
            self.stats["songs_found"] += 1
            return song_id

        # Download if not found
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
        """Process recommendations and return song IDs."""
        song_ids: List[str] = []

        for rec in recommendations[:max_songs]:
            song_id = self._process_single_recommendation(rec)
            if song_id:
                song_ids.append(song_id)

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

    def run(self) -> None:
        """Run the main discovery engine."""
        start_time = datetime.now()

        logger.info("=" * 70)
        logger.info("OCTOGEN - Starting: %s", start_time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("=" * 70)

        try:
            # Analyze library
            logger.info("Analyzing music library...")
            favorited_songs = self.nd.get_starred_songs()
            top_artists = self.nd.get_top_artists(100)
            top_genres = self.nd.get_top_genres(20)
            low_rated_songs = self.nd.get_low_rated_songs()

            logger.info("Library: %d favorited songs", len(favorited_songs))
            logger.info("Top artists: %s", ", ".join(top_artists[:5]))
            logger.info("Top genres: %s", ", ".join(top_genres[:5]))
            logger.info("Songs to avoid: %d (rated %d-%d stars)",
                       len(low_rated_songs), LOW_RATING_MIN, LOW_RATING_MAX)

            # Generate AI playlists
            logger.info("=" * 70)
            logger.info("AI CALL LIMIT: %d maximum", self.ai.max_calls)
            logger.info("=" * 70)

            all_playlists = self.ai.generate_all_playlists(
                top_artists,
                top_genres,
                favorited_songs,
                low_rated_songs
            )

            self.stats["ai_calls"] = self.ai.call_count

            if all_playlists:
                for playlist_name, songs in all_playlists.items():
                    if isinstance(songs, list) and songs:
                        self.create_playlist(playlist_name, songs, max_songs=100)

            # External services
            if self.lastfm:
                logger.info("=" * 70)
                logger.info("LAST.FM RECOMMENDATIONS")
                logger.info("=" * 70)
                recs = self.lastfm.get_recommended_tracks(50)
                if recs:
                    self.create_playlist("Last.fm Recommended", recs, 50)

            if self.listenbrainz:
                logger.info("Creating ListenBrainz 'Created For You' playlists...")
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
                    # NO IMPORT HERE - datetime is already imported at top of file
                    
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





            # Summary
            elapsed = datetime.now() - start_time
            logger.info("=" * 70)
            logger.info("COMPLETED")
            logger.info("=" * 70)
            logger.info("Total time: %dm %ds", elapsed.seconds // 60, elapsed.seconds % 60)
            logger.info("AI API calls: %d / %d", self.stats["ai_calls"], self.ai.max_calls)
            logger.info("Playlists created: %d", self.stats["playlists_created"])
            logger.info("Songs in library: %d", self.stats["songs_found"])
            logger.info("Songs downloaded: %d", self.stats["songs_downloaded"])
            logger.info("Songs skipped (low rating): %d", self.stats["songs_skipped_low_rating"])
            logger.info("Songs skipped (duplicate): %d", self.stats["songs_skipped_duplicate"])
            logger.info("Songs failed: %d", self.stats["songs_failed"])
            logger.info("=" * 70)

        except Exception as e:
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

def run_with_schedule(dry_run: bool = False):
    """Run engine with optional cron scheduling."""
    schedule_cron = os.getenv("SCHEDULE_CRON", "").strip()

    # Check if scheduling is disabled
    if not schedule_cron or schedule_cron.lower() in ("manual", "false", "no", "off", "disabled"):
        logger.info("🔧 Running in manual mode (no schedule)")
        engine = OctoGenEngine(dry_run=dry_run)
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

            # Wait until next run
            wait_until(next_run)

            # Execute
            run_count += 1
            logger.info("═" * 70)
            logger.info("🚀 SCHEDULED RUN #%d - %s", run_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logger.info("═" * 70)

            engine = OctoGenEngine(dry_run=dry_run)
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
