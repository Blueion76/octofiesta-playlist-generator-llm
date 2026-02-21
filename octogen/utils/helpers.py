"""Helper utility functions for OctoGen"""

import os
import sys
import fcntl
import atexit
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def print_banner():
    banner = r"""
    
  ░██████                 ░██                 ░██████                        
 ░██   ░██                ░██                ░██   ░██                       
░██     ░██  ░███████  ░████████  ░███████  ░██         ░███████  ░████████  
░██     ░██ ░██    ░██    ░██    ░██    ░██ ░██  █████ ░██    ░██ ░██    ░██ 
░██     ░██ ░██           ░██    ░██    ░██ ░██     ██ ░█████████ ░██    ░██ 
 ░██   ░██  ░██    ░██    ░██    ░██    ░██  ░██  ░███ ░██        ░██    ░██ 
  ░██████    ░███████      ░████  ░███████    ░█████░█  ░███████  ░██    ░██ 


    """
    print(banner)


def acquire_lock(lock_file: Path) -> object:
    """Prevent multiple instances from running.
    
    Args:
        lock_file: Path to lock file
        
    Returns:
        Lock file object
        
    Raises:
        SystemExit: If another instance is already running
    """
    try:
        lock = open(lock_file, "w")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.write(str(os.getpid()))
        lock.flush()

        def cleanup():
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
                if lock_file.exists():
                    lock_file.unlink()
            except:
                pass

        atexit.register(cleanup)
        return lock
    except IOError:
        logger.error("Another instance is already running!")
        sys.exit(1)


# Constants
LOW_RATING_MIN = 1
LOW_RATING_MAX = 2
COOLDOWN_EXIT_DELAY_SECONDS = 60  # Sleep duration before exit in manual mode to prevent rapid restarts

# Default genres for Daily Mixes when library genres are insufficient
DEFAULT_DAILY_MIX_GENRES = ["rock", "pop", "electronic", "hip-hop", "indie", "jazz"]
