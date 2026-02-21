"""ListenBrainz API client for music recommendations"""

import logging
import requests
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


class ListenBrainzAPI:
    """Fetches recommendations from ListenBrainz."""

    def __init__(self, username: str, token: str = None):
        """Initialize ListenBrainz API client.
        
        Args:
            username: ListenBrainz username
            token: Optional authentication token
        """
        self.username = username
        self.token = token
        self.base_url = "https://api.listenbrainz.org/1"
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})
        logger.info("ListenBrainz initialized: %s", username)

    def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make API request with error handling.
        
        Args:
            endpoint: API endpoint path
            params: Optional query parameters
            
        Returns:
            JSON response or None on error
        """
        try:
            url = f"{self.base_url}/{endpoint}"
            r = self.session.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error("ListenBrainz API error: %s", str(e)[:200])
            return None

    def get_created_for_you_playlists(self, count: int = 25, offset: int = 0) -> List[Dict]:
        """Fetch metadata for 'Created For You' playlists.
        
        Args:
            count: Number of playlists to fetch
            offset: Pagination offset
            
        Returns:
            List of playlist metadata (without tracks)
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

        # Validate: the ListenBrainz API returns JSPF format where each item is
        # {"playlist": {"title": ..., "identifier": ..., "track": [...], ...}}
        # The old filter checked for top-level 'id' and 'name' keys which don't
        # exist in JSPF format, causing ALL playlists to be silently dropped.
        playlists = [
            p for p in playlists
            if p.get("playlist", {}).get("title") and p.get("playlist", {}).get("identifier")
        ]
        
        # DEBUG
        if playlists:
            logger.info("First playlist keys: %s", list(playlists[0].keys()))
        
        logger.info("Found %d 'Created For You' playlists", len(playlists))
        return playlists

    def get_playlist_tracks(self, playlist_mbid: str) -> List[Dict]:
        """Fetch tracks from a specific playlist by MBID.
        
        Args:
            playlist_mbid: MusicBrainz ID of the playlist
            
        Returns:
            List of tracks with artist and title
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
            
            identifier = track.get("identifier")
            mbid = None
            if identifier:
                if isinstance(identifier, list) and identifier:
                    mbid = identifier[0].split("/")[-1]
                elif isinstance(identifier, str):
                    mbid = identifier.split("/")[-1]
            
            tracks.append({
                "artist": artist,
                "title": title,
                "mbid": mbid
            })
        
        logger.info("Found %d tracks in playlist", len(tracks))
        return tracks

    def get_recommendations(self, limit: int = 50) -> List[Dict]:
        """Fetch personalized recommendations using collaborative filtering.
    
        This is the original recommendation endpoint (different from playlists).
    
        Args:
            limit: Maximum number of recommendations
    
        Returns:
            List of track recommendations
        """
        logger.info("Fetching ListenBrainz CF recommendations...")
    
        response = self._request(f"cf/recommendation/user/{self.username}/recording")
        if not response or "payload" not in response:
            logger.warning("No ListenBrainz recommendations found")
            return []
    
        mbids = [rec["recording_mbid"] for rec in response["payload"].get("mbids", [])[:limit]]
        recommendations: List[Dict] = []
    
        if mbids:
            # Batch request: comma-separated MBIDs
            metadata_response = self._request(
                "metadata/recording", {"recording_mbids": ",".join(mbids)}
            )
            if metadata_response:
                for mbid in mbids:
                    data = metadata_response.get(mbid, {})
                    artist = data.get("artist", {}).get("name", "Unknown")
                    title = data.get("recording", {}).get("name", "Unknown")
                    recommendations.append({"artist": artist, "title": title})
            else:
                logger.warning("Failed to fetch metadata for recommended recordings.")
    
        logger.info("Found %d ListenBrainz CF recommendations", len(recommendations))
        return recommendations
