"""Time-of-day playlist scheduling and management"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def get_current_period() -> str:
    """Determine current time period based on environment configuration.
    
    Returns:
        Period name: "morning", "afternoon", "evening", or "night"
    """
    # Get current hour in UTC (or local time if TZ is set)
    now = datetime.now()
    hour = now.hour
    
    # Get period boundaries from environment (defaults match requirements)
    morning_start = int(os.getenv("TIMEOFDAY_MORNING_START", "6"))
    morning_end = int(os.getenv("TIMEOFDAY_MORNING_END", "12"))
    afternoon_start = int(os.getenv("TIMEOFDAY_AFTERNOON_START", "12"))
    afternoon_end = int(os.getenv("TIMEOFDAY_AFTERNOON_END", "18"))
    evening_start = int(os.getenv("TIMEOFDAY_EVENING_START", "18"))
    evening_end = int(os.getenv("TIMEOFDAY_EVENING_END", "24"))
    night_start = int(os.getenv("TIMEOFDAY_NIGHT_START", "0"))
    night_end = int(os.getenv("TIMEOFDAY_NIGHT_END", "6"))
    
    # Determine period
    if morning_start <= hour < morning_end:
        return "morning"
    elif afternoon_start <= hour < afternoon_end:
        return "afternoon"
    elif evening_start <= hour < evening_end:
        return "evening"
    else:  # night_start <= hour < night_end
        return "night"


def get_period_display_name(period: str) -> str:
    """Get display name for time period.
    
    Args:
        period: Period name (morning, afternoon, evening, night)
        
    Returns:
        Display name with time range
    """
    morning_start = int(os.getenv("TIMEOFDAY_MORNING_START", "6"))
    morning_end = int(os.getenv("TIMEOFDAY_MORNING_END", "12"))
    afternoon_start = int(os.getenv("TIMEOFDAY_AFTERNOON_START", "12"))
    afternoon_end = int(os.getenv("TIMEOFDAY_AFTERNOON_END", "18"))
    evening_start = int(os.getenv("TIMEOFDAY_EVENING_START", "18"))
    evening_end = int(os.getenv("TIMEOFDAY_EVENING_END", "24"))
    night_start = int(os.getenv("TIMEOFDAY_NIGHT_START", "0"))
    night_end = int(os.getenv("TIMEOFDAY_NIGHT_END", "6"))
    
    period_names = {
        "morning": f"Morning Mix ({morning_start} AM - {morning_end} PM)",
        "afternoon": f"Afternoon Flow ({afternoon_start} PM - {afternoon_end} PM)",
        "evening": f"Evening Chill ({evening_start} PM - {evening_end} PM)",
        "night": f"Night Vibes ({night_start} AM - {night_end} AM)"
    }
    
    return period_names.get(period, f"{period.capitalize()} Playlist")


def get_time_context(period: Optional[str] = None) -> Dict[str, str]:
    """Get time-of-day context for AI prompts.
    
    Args:
        period: Optional period override, otherwise uses current period
        
    Returns:
        Dict with period, description, and mood guidance
    """
    if period is None:
        period = get_current_period()
    
    contexts = {
        "morning": {
            "period": "morning",
            "description": "Morning (6 AM - 12 PM)",
            "mood": "upbeat, energetic, positive vibes",
            "energy": "high",
            "guidance": "Focus on uplifting, motivational music to start the day. "
                       "Prefer upbeat tempos, major keys, and positive lyrics."
        },
        "afternoon": {
            "period": "afternoon",
            "description": "Afternoon (12 PM - 6 PM)",
            "mood": "balanced, productive, moderate energy",
            "energy": "medium",
            "guidance": "Select balanced tracks for productivity and focus. "
                       "Mix of energy levels, avoid extremes in either direction."
        },
        "evening": {
            "period": "evening",
            "description": "Evening (6 PM - 12 AM)",
            "mood": "chill, relaxing, wind-down music",
            "energy": "low-medium",
            "guidance": "Choose relaxing, soothing tracks for unwinding. "
                       "Slower tempos, softer dynamics, calming atmospheres."
        },
        "night": {
            "period": "night",
            "description": "Night (12 AM - 6 AM)",
            "mood": "ambient, calm, sleep-friendly",
            "energy": "low",
            "guidance": "Select very calm, ambient music suitable for sleep or late-night relaxation. "
                       "Minimal vocals, slow tempos, peaceful instrumentals."
        }
    }
    
    return contexts.get(period, contexts["afternoon"])


def should_regenerate_period_playlist(data_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Check if time period playlist should be regenerated.
    
    Args:
        data_dir: Data directory path
        
    Returns:
        Tuple of (should_regenerate, reason)
    """
    if data_dir is None:
        data_dir = Path(os.getenv("OCTOGEN_DATA_DIR", Path.cwd()))
    
    # Check if feature is enabled
    enabled = os.getenv("TIMEOFDAY_ENABLED", "true").lower() in ("true", "yes", "1", "on")
    if not enabled:
        return False, "Time-of-day playlists disabled"
    
    tracker_file = data_dir / "octogen_timeofday_last.json"
    current_period = get_current_period()
    
    # First run or no tracker file
    if not tracker_file.exists():
        return True, f"First time generating {current_period} playlist"
    
    try:
        with open(tracker_file, 'r') as f:
            data = json.load(f)
            last_period = data.get("last_period")
            last_generated = data.get("last_generated")
            
            # Check if period changed
            if last_period != current_period:
                return True, f"Time period changed from {last_period} to {current_period}"
            
            # Check if refresh on period change is enabled
            refresh_enabled = os.getenv("TIMEOFDAY_REFRESH_ON_PERIOD_CHANGE", "true").lower() in ("true", "yes", "1", "on")
            if not refresh_enabled:
                return False, f"Already generated for {current_period} period"
            
            # Don't regenerate if already done for this period
            return False, f"Already generated for {current_period} period"
            
    except Exception as e:
        logger.warning(f"Error reading time-of-day tracker: {e}")
        return True, "Error reading tracker, regenerating"


def record_period_playlist_generation(period: Optional[str] = None, playlist_name: str = "", data_dir: Optional[Path] = None) -> None:
    """Record that a time period playlist was generated.
    
    Args:
        period: Time period (or current if None)
        playlist_name: Name of the generated playlist
        data_dir: Data directory path
    """
    if data_dir is None:
        data_dir = Path(os.getenv("OCTOGEN_DATA_DIR", Path.cwd()))
    
    if period is None:
        period = get_current_period()
    
    tracker_file = data_dir / "octogen_timeofday_last.json"
    
    try:
        now = datetime.now(timezone.utc)
        
        data = {
            "last_period": period,
            "last_generated": now.isoformat(),
            "playlist_name": playlist_name or get_period_display_name(period)
        }
        
        with open(tracker_file, 'w') as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"✓ Recorded time-of-day playlist generation: {period}")
        
    except Exception as e:
        logger.error(f"Error recording time-of-day playlist generation: {e}")


def get_period_playlist_size() -> int:
    """Get configured playlist size for time-of-day playlists.
    
    Returns:
        Number of songs per time-period playlist
    """
    return int(os.getenv("TIMEOFDAY_PLAYLIST_SIZE", "30"))
