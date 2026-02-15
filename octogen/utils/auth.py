"""Subsonic authentication utilities"""

import hashlib
import secrets
from typing import Dict


def subsonic_auth_params(username: str, password: str) -> Dict[str, str]:
    """Generate Subsonic authentication parameters.
    
    Args:
        username: Subsonic username
        password: Subsonic password
        
    Returns:
        Dictionary with authentication parameters
    """
    salt = secrets.token_hex(6)
    token = hashlib.md5(f"{password}{salt}".encode()).hexdigest()
    return {
        "u": username,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "OctoGen",
        "f": "json",
    }
