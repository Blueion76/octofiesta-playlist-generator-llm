"""Last.fm API client for music recommendations"""

import logging
import requests
from typing import List, Dict, Optional

from octogen.utils.retry import retry_with_backoff


logger = logging.getLogger(__name__)


class LastFMAPI:
    """Fetches recommendations from Last.fm with retry logic."""

    def __init__(self, api_key: str, username: str):
        """Initialize Last.fm API client.
        
        Args:
            api_key: Last.fm API key
            username: Last.fm username
        """
        self.api_key = api_key
        self.username = username
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        self.session = requests.Session()
        logger.info("Last.fm initialized: %s", username)

    def _request(self, method: str, params: dict = None) -> Optional[dict]:
        """Make API request with retry logic.
        
        Args:
            method: Last.fm API method
            params: Additional parameters
            
        Returns:
            JSON response or None on error
        """
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
        """Fetch recommended tracks.
        
        Args:
            limit: Maximum number of recommendations
            
        Returns:
            List of track dictionaries with artist and title
        """
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
