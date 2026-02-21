"""Prometheus metrics for monitoring OctoGen"""

import logging
import os
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from typing import Optional


logger = logging.getLogger(__name__)


# Metrics instances (initialized once)
_metrics_initialized = False
_metrics_server_started = False

# Counters
playlists_created_total = None
songs_downloaded_total = None
api_calls_total = None

# Histograms
api_latency_seconds = None

# Gauges
ai_tokens_used = None
last_run_timestamp = None
last_run_duration_seconds = None


def init_metrics() -> None:
    """Initialize Prometheus metrics.
    
    This should be called once at application startup.
    """
    global _metrics_initialized
    global playlists_created_total, songs_downloaded_total, api_calls_total
    global api_latency_seconds, ai_tokens_used
    global last_run_timestamp, last_run_duration_seconds
    
    if _metrics_initialized:
        return
    
    logger.info("Initializing Prometheus metrics")
    
    # Counters
    playlists_created_total = Counter(
        'octogen_playlists_created_total',
        'Total number of playlists created',
        ['source']
    )
    
    songs_downloaded_total = Counter(
        'octogen_songs_downloaded_total',
        'Total number of songs downloaded'
    )
    
    api_calls_total = Counter(
        'octogen_api_calls_total',
        'Total number of API calls',
        ['service', 'status']
    )
    
    # Histograms
    api_latency_seconds = Histogram(
        'octogen_api_latency_seconds',
        'API call latency in seconds',
        ['service'],
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
    )
    
    # Gauges
    ai_tokens_used = Gauge(
        'octogen_ai_tokens_used',
        'Number of AI tokens used in last run'
    )
    
    last_run_timestamp = Gauge(
        'octogen_last_run_timestamp',
        'Timestamp of last successful run'
    )
    
    last_run_duration_seconds = Gauge(
        'octogen_last_run_duration_seconds',
        'Duration of last run in seconds'
    )
    
    _metrics_initialized = True
    logger.info("Prometheus metrics initialized")


def start_metrics_server(port: int = 9090) -> bool:
    """Start Prometheus metrics HTTP server.
    
    Args:
        port: Port to listen on (default: 9090)
        
    Returns:
        True if server started successfully
    """
    global _metrics_server_started
    
    if _metrics_server_started:
        logger.warning("Metrics server already started")
        return True
    
    try:
        start_http_server(port)
        _metrics_server_started = True
        logger.info(f"Prometheus metrics server started on port {port}")
        return True
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        return False


def setup_metrics(enabled: bool = True, port: int = 9090) -> bool:
    """Setup and optionally start metrics server.
    
    Args:
        enabled: Whether to start the metrics server
        port: Port for metrics server
        
    Returns:
        True if setup succeeded
    """
    if not enabled:
        logger.info("Metrics collection disabled")
        return False
    
    init_metrics()
    
    if enabled:
        return start_metrics_server(port)
    
    return True


# Convenience functions for recording metrics
def record_playlist_created(source: str = "ai") -> None:
    """Record playlist creation"""
    if playlists_created_total:
        playlists_created_total.labels(source=source).inc()


def record_song_downloaded() -> None:
    """Record song download"""
    if songs_downloaded_total:
        songs_downloaded_total.inc()


def record_api_call(service: str, status: str, duration: Optional[float] = None) -> None:
    """Record API call.
    
    Args:
        service: Name of the service (navidrome, lastfm, etc)
        status: Status of call (success, error)
        duration: Optional duration in seconds
    """
    if api_calls_total:
        api_calls_total.labels(service=service, status=status).inc()
    
    if duration and api_latency_seconds:
        api_latency_seconds.labels(service=service).observe(duration)


def record_ai_tokens(tokens: int) -> None:
    """Record AI tokens used"""
    if ai_tokens_used:
        ai_tokens_used.set(tokens)


def record_run_complete(duration: float) -> None:
    """Record run completion.
    
    Args:
        duration: Run duration in seconds
    """
    import time
    if last_run_timestamp:
        last_run_timestamp.set(time.time())
    if last_run_duration_seconds:
        last_run_duration_seconds.set(duration)
