"""Flask web application for OctoGen dashboard"""

import logging
import os
from flask import Flask, render_template, jsonify
from pathlib import Path


logger = logging.getLogger(__name__)


def create_app(config: dict = None):
    """Create and configure Flask app.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    
    if config:
        app.config.update(config)
    
    # Set template folder
    template_dir = Path(__file__).parent / 'templates'
    app.template_folder = str(template_dir)
    
    @app.route('/')
    def index():
        """Dashboard home page"""
        return render_template('dashboard.html')
    
    @app.route('/api/status')
    def api_status():
        """Get current status"""
        # This would be populated by the main engine
        return jsonify({
            'status': 'running',
            'last_run': None,
            'next_run': None
        })
    
    @app.route('/api/stats')
    def api_stats():
        """Get statistics"""
        return jsonify({
            'playlists_created': 0,
            'songs_downloaded': 0,
            'songs_failed': 0
        })
    
    @app.route('/api/health')
    def api_health():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'services': {
                'navidrome': 'unknown',
                'octofiesta': 'unknown'
            }
        })
    
    return app


def start_web_server(port: int = 5000, **kwargs):
    """Start the web server in the current thread.
    
    Args:
        port: Port to listen on
        **kwargs: Additional configuration for Flask app
    """
    app = create_app(kwargs)
    logger.info(f"Starting web UI on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
