"""Time-of-day playlist scheduling and management"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def get_timezone() -> ZoneInfo:
    """Get configured timezone from TZ environment variable.

    Returns:
        ZoneInfo object for configured timezone (defaults to UTC)
    """
    tz_name = os.getenv("TZ", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"Invalid TZ={tz_name}, falling back to UTC")
        return ZoneInfo("UTC")


def get_current_period() -> str:
    """Determine current time period based on environment configuration.

    Returns:
        Period name: "morning", "afternoon", "evening", or "night"
    """
    # Get current hour in local timezone
    tz = get_timezone()
    now = datetime.now(tz)
    hour = now.hour

    # Get period boundaries from environment (defaults match requirements)
    morning_start = int(os.getenv("TIMEOFDAY_MORNING_START", "4"))
    morning_end = int(os.getenv("TIMEOFDAY_MORNING_END", "10"))
    afternoon_start = int(os.getenv("TIMEOFDAY_AFTERNOON_START", "10"))
    afternoon_end = int(os.getenv("TIMEOFDAY_AFTERNOON_END", "16"))
    evening_start = int(os.getenv("TIMEOFDAY_EVENING_START", "16"))
    evening_end = int(os.getenv("TIMEOFDAY_EVENING_END", "22"))
    night_start = int(os.getenv("TIMEOFDAY_NIGHT_START", "22"))
    night_end = int(os.getenv("TIMEOFDAY_NIGHT_END", "4"))

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
    morning_start = int(os.getenv("TIMEOFDAY_MORNING_START", "4"))
    morning_end = int(os.getenv("TIMEOFDAY_MORNING_END", "10"))
    afternoon_start = int(os.getenv("TIMEOFDAY_AFTERNOON_START", "10"))
    afternoon_end = int(os.getenv("TIMEOFDAY_AFTERNOON_END", "16"))
    evening_start = int(os.getenv("TIMEOFDAY_EVENING_START", "16"))
    evening_end = int(os.getenv("TIMEOFDAY_EVENING_END", "22"))
    night_start = int(os.getenv("TIMEOFDAY_NIGHT_START", "22"))
    night_end = int(os.getenv("TIMEOFDAY_NIGHT_END", "4"))

    period_names = {
        "morning": f"Morning Mix",
        "afternoon": f"Afternoon Flow",
        "evening": f"Evening Chill",
        "night": f"Night Vibes"
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
            "description": "Morning Mix",
            "mood": "upbeat, energetic, positive vibes",
            "energy": "high",
            "guidance": "Focus on uplifting, motivational music to start the day. "
                       "Prefer upbeat tempos, major keys, and positive lyrics."
        },
        "afternoon": {
            "period": "afternoon",
            "description": "Afternoon Flow",
            "mood": "balanced, productive, moderate energy",
            "energy": "medium",
            "guidance": "Select balanced tracks for productivity and focus. "
                       "Mix of energy levels, avoid extremes in either direction."
        },
        "evening": {
            "period": "evening",
            "description": "Evening Chill",
            "mood": "chill, relaxing, wind-down music",
            "energy": "low-medium",
            "guidance": "Choose relaxing, soothing tracks for unwinding. "
                       "Slower tempos, softer dynamics, calming atmospheres."
        },
        "night": {
            "period": "night",
            "description": "Night Vibes",
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


# ============================================================================
# Time-Gating Functions for Designated Generation Times
# ============================================================================

def _parse_iso_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO timestamp string to datetime object.

    Args:
        timestamp_str: ISO format timestamp string

    Returns:
        Timezone-aware datetime object
    """
    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))


def get_period_target_hour(period: str) -> int:
    """Get the target generation hour for a given period from env vars.

    Args:
        period: Period name (morning, afternoon, evening, night)

    Returns:
        Target hour (24-hour format) when this period playlist should generate
    """
    defaults = {
        "morning": 4,
        "afternoon": 10,
        "evening": 16,
        "night": 22
    }
    env_vars = {
        "morning": "TIMEOFDAY_MORNING_START",
        "afternoon": "TIMEOFDAY_AFTERNOON_START",
        "evening": "TIMEOFDAY_EVENING_START",
        "night": "TIMEOFDAY_NIGHT_START"
    }
    key = period.lower()
    env_var = env_vars.get(key)
    default = defaults.get(key, 6)

    try:
        value = int(os.getenv(env_var, str(default)))
        return value
    except Exception:
        logger.warning(f"Invalid {env_var}, falling back to default {default}")
        return default


def is_within_generation_window(target_hour: int, tolerance_minutes: int = 30) -> bool:
    """Check if current time is within generation window of target hour.

    Args:
        target_hour: Target hour for generation (0-23) in LOCAL timezone
        tolerance_minutes: Minutes before/after target hour to allow (default: 30)

    Returns:
        True if current time is within the generation window
    """
    # Use local timezone for time checks
    tz = get_timezone()
    now = datetime.now(tz)
    current_hour = now.hour
    current_minute = now.minute

    # Convert to total minutes since midnight for easier comparison
    current_minutes = current_hour * 60 + current_minute
    target_minutes = target_hour * 60

    # Calculate difference (handling midnight wraparound)
    diff = abs(current_minutes - target_minutes)

    # Handle wraparound case (e.g., 23:50 to 00:10)
    if diff > 720:  # More than 12 hours means we wrapped
        diff = 1440 - diff  # 1440 = 24 hours in minutes

    return diff <= tolerance_minutes


def should_generate_period_playlist_now(period: Optional[str] = None, data_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Check if period playlist should be generated at current time.

    This implements time-gating logic:
    - Only generate at designated hour (with ±30 min tolerance)
    - Track last generation to prevent duplicates
    - Respect timezone settings

    Args:
        period: Optional period override, otherwise uses current period
        data_dir: Data directory path

    Returns:
        Tuple of (should_generate, reason)
    """
    if data_dir is None:
        data_dir = Path(os.getenv("OCTOGEN_DATA_DIR", Path.cwd()))

    # Check if feature is enabled
    enabled = os.getenv("TIMEOFDAY_ENABLED", "true").lower() in ("true", "yes", "1", "on")
    if not enabled:
        return False, "Time-of-day playlists disabled"

    if period is None:
        period = get_current_period()

    # Get target hour for this period
    target_hour = get_period_target_hour(period)

    # Check if we're within the generation window
    if not is_within_generation_window(target_hour):
        tz = get_timezone()
        now = datetime.now(tz)
        tz_name = now.strftime("%Z")  # Shows CST, EST, PST, etc.
        return False, f"Not at designated generation time (current: {now.hour}:{now.minute:02d} {tz_name}, target: {target_hour}:00 ±30min)"

    # Check if we already generated recently (within this window)
    tracker_file = data_dir / "octogen_timeofday_last.json"

    if tracker_file.exists():
        try:
            with open(tracker_file, 'r') as f:
                data = json.load(f)

            last_period = data.get("last_period")
            last_generated_str = data.get("last_generated")

            if last_generated_str:
                last_generated = _parse_iso_timestamp(last_generated_str)
                now = datetime.now(timezone.utc)

                # Don't regenerate if we generated for this period within the last hour
                time_since_last = (now - last_generated).total_seconds() / 3600  # hours

                if last_period == period and time_since_last < 1.0:
                    return False, f"Already generated {period} playlist {time_since_last:.1f} hours ago"

        except Exception as e:
            logger.warning(f"Error reading time-of-day tracker: {e}")

    # All checks passed
    return True, f"At designated generation time for {period} playlist (target: {target_hour}:00)"


def is_scheduled_mode() -> bool:
    """Check if OctoGen is running in scheduled mode.

    Returns:
        True if SCHEDULE_CRON is set and not disabled
    """
    schedule_cron = os.getenv("SCHEDULE_CRON", "").strip()

    if not schedule_cron:
        return False

    if schedule_cron.lower() in ("manual", "false", "no", "off", "disabled"):
        return False

    return True


def should_generate_regular_playlists(data_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Check if regular playlists (Daily Mix, etc.) should be generated now.

    Regular playlists should ONLY run when:
    1. In scheduled mode (SCHEDULE_CRON is set)
    2. At the designated cron time
    3. Haven't generated within cooldown period

    Args:
        data_dir: Data directory path

    Returns:
        Tuple of (should_generate, reason)
    """
    if data_dir is None:
        data_dir = Path(os.getenv("OCTOGEN_DATA_DIR", Path.cwd()))

    tracker_file = data_dir / "octogen_regular_last.json"

    # First check for recent generation to prevent duplicates (applies to both modes)
    if tracker_file.exists():
        try:
            with open(tracker_file, 'r') as f:
                data = json.load(f)

            last_generated_str = data.get("last_generated")

            if last_generated_str:
                last_generated = _parse_iso_timestamp(last_generated_str)
                now = datetime.now(timezone.utc)

                # Don't regenerate if we generated within the last hour
                time_since_last = (now - last_generated).total_seconds() / 3600  # hours

                if time_since_last < 1.0:
                    return False, f"Already generated regular playlists {time_since_last:.1f} hours ago"

        except Exception as e:
            logger.warning(f"Error reading regular playlist tracker: {e}")

    # Check if we're in scheduled mode
    if not is_scheduled_mode():
        return True, "Running in manual mode - proceeding with generation"

    # In scheduled mode, we should generate (scheduler already handles timing)
    return True, "At scheduled generation time for regular playlists"


def record_regular_playlist_generation(data_dir: Optional[Path] = None) -> None:
    """Record that regular playlists were generated.

    Args:
        data_dir: Data directory path
    """
    if data_dir is None:
        data_dir = Path(os.getenv("OCTOGEN_DATA_DIR", Path.cwd()))

    tracker_file = data_dir / "octogen_regular_last.json"

    try:
        now = datetime.now(timezone.utc)

        data = {
            "last_generated": now.isoformat(),
            "type": "regular_playlists"
        }

        with open(tracker_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"✓ Recorded regular playlist generation")

    except Exception as e:
        logger.error(f"Error recording regular playlist generation: {e}")
