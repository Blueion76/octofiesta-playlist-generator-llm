#!/usr/bin/env python3
"""Backwards compatibility shim - forwards to new modular structure

This file provides backwards compatibility for existing deployments that
may be calling octogen.py directly. All functionality has been moved to
the octogen package modules.

For new deployments, use: python -m octogen.main
"""

import sys
import os

# Set up logging before importing main (to configure early)
from octogen.utils.logging_config import setup_logging
setup_logging()

# Import and run main from the modular structure
from octogen.main import main

if __name__ == "__main__":
    # Call main() and let it handle exit codes
    main()
