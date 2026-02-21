"""Flask web application for OctoGen dashboard"""

import logging
import os
import threading
from flask import Flask, render_template, jsonify
from pathlib import Path

try:
    from flasgger import Swagger
    FLASGGER_AVAILABLE = True
except ImportError:
    FLASGGER_AVAILABLE = False

logger = logging.getLogger(__name__)

# Global reference for accessing health/stats from main app
_app_context = {}


def set_app_context(data_dir: Path = None, **kwargs):
    """Set application context for API endpoints.
    
    Args:
        data_dir: Data directory path
        **kwargs: Additional context data
    """
    global _app_context
    _app_context['data_dir'] = data_dir
    _app_context.update(kwargs)


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
    
    # Initialize Swagger if available
    if FLASGGER_AVAILABLE:
        swagger_config = {
            "headers": [],
            "specs": [
                {
                    "endpoint": 'apispec',
                    "route": '/apispec.json',
                    "rule_filter": lambda rule: True,
                    "model_filter": lambda tag: True,
                }
            ],
            "static_url_path": "/flasgger_static",
            "swagger_ui": True,
            "specs_route": "/apidocs/"
        }
        swagger = Swagger(app, config=swagger_config)
        logger.info("✓ Swagger documentation enabled at /apidocs/")
    
    @app.route('/')
    def index():
        """Dashboard home page"""
        return render_template('dashboard.html')
    
    @app.route('/api/health')
    def api_health():
        """Health check endpoint
        ---
        tags:
          - Health
        responses:
          200:
            description: Overall health status
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: healthy
                services:
                  type: object
        """
        try:
            from octogen.web.health import get_all_services
            services = get_all_services()
            
            # Determine overall status
            all_healthy = all(s.get('healthy', False) for s in services.values() 
                            if s.get('status') not in ('disabled', 'configured'))
            overall_status = 'healthy' if all_healthy else 'degraded'
            
            return jsonify({
                'status': overall_status,
                'services': services
            })
        except Exception as e:
            logger.error(f"Error in health endpoint: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    @app.route('/api/services')
    def api_services():
        """Get all service statuses
        ---
        tags:
          - Services
        responses:
          200:
            description: Detailed service status information
            schema:
              type: object
        """
        try:
            from octogen.web.health import get_all_services
            services = get_all_services()
            return jsonify(services)
        except Exception as e:
            logger.error(f"Error in services endpoint: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/stats')
    def api_stats():
        """Get system statistics
        ---
        tags:
          - Statistics
        responses:
          200:
            description: System statistics
            schema:
              type: object
              properties:
                cache_size:
                  type: integer
                songs_rated:
                  type: integer
                low_rated_count:
                  type: integer
                last_run:
                  type: string
                next_run:
                  type: string
                playlists_created:
                  type: integer
        """
        try:
            from octogen.web.health import get_system_stats
            data_dir = _app_context.get('data_dir')
            stats = get_system_stats(data_dir)
            return jsonify(stats)
        except Exception as e:
            logger.error(f"Error in stats endpoint: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/status')
    def api_status():
        """Get current run status
        ---
        tags:
          - Status
        responses:
          200:
            description: Current execution status
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: running
                last_run:
                  type: string
                next_run:
                  type: string
        """
        try:
            from octogen.web.health import get_system_stats
            data_dir = _app_context.get('data_dir')
            stats = get_system_stats(data_dir)
            
            return jsonify({
                'status': 'running',
                'last_run': stats.get('last_run'),
                'next_run': stats.get('next_run')
            })
        except Exception as e:
            logger.error(f"Error in status endpoint: {e}")
            return jsonify({'error': str(e)}), 500
    
    return app


def start_web_server(port: int = 5000, data_dir: Path = None, threaded: bool = True):
    """Start the web server.
    
    Args:
        port: Port to listen on
        data_dir: Data directory for accessing stats
        threaded: If True, start in background thread; if False, run in current thread
        
    Returns:
        Thread object if threaded=True, None otherwise
    """
    # Set app context
    set_app_context(data_dir=data_dir)
    
    app = create_app()
    logger.info(f"🌐 Starting web UI on port {port}")
    logger.info(f"🌐 Dashboard: http://localhost:{port}")
    if FLASGGER_AVAILABLE:
        logger.info(f"🌐 API Docs: http://localhost:{port}/apidocs/")
    
    if threaded:
        # Start in background thread
        thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
            daemon=True
        )
        thread.start()
        return thread
    else:
        # Run in current thread (blocking)
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        return None
