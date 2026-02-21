"""SQLite cache for song ratings and data persistence"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


# Constants
LOW_RATING_MIN = 1
LOW_RATING_MAX = 2


class RatingsCache:
    """SQLite cache for song ratings to avoid repeated scans."""

    def __init__(self, db_path: Path):
        """Initialize ratings cache.
        
        Args:
            db_path: Path to SQLite database file
        """
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
        """Get the last full scan date.
        
        Returns:
            Last scan date string or None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM cache_metadata WHERE key = 'last_scan_date'"
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_last_scan_date(self, date: str) -> None:
        """Update the last full scan date.
        
        Args:
            date: Date string to store
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache_metadata (key, value)
                   VALUES ('last_scan_date', ?)""",
                (date,)
            )
            conn.commit()

    def update_rating(self, song_id: str, artist: str, title: str, rating: int) -> None:
        """Update or insert a song rating.
        
        Args:
            song_id: Unique song identifier
            artist: Artist name
            title: Song title
            rating: Rating value (0-5)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ratings
                   (song_id, artist, title, rating, last_updated)
                   VALUES (?, ?, ?, ?, ?)""",
                (song_id, artist, title, rating, datetime.now().isoformat())
            )
            conn.commit()

    def get_low_rated_songs(self) -> List[Dict]:
        """Get all songs rated 1-2 stars from cache.
        
        Returns:
            List of song dictionaries with id, artist, title, rating
        """
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
