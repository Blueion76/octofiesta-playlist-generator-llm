# OctoGen Architecture

## Overview

OctoGen has been refactored from a monolithic 2900-line script into a modular, maintainable architecture while preserving full backward compatibility.

## Directory Structure

```
octogen/
├── __init__.py               # Package initialization
├── config.py                 # Configuration loading and validation
├── api/                      # External API clients
│   ├── __init__.py
│   ├── navidrome.py         # Navidrome/Subsonic API + OctoFiesta trigger
│   ├── lastfm.py            # Last.fm API client
│   ├── listenbrainz.py      # ListenBrainz API client
│   └── audiomuse.py         # AudioMuse-AI client
├── ai/                       # AI recommendation engine
│   ├── __init__.py
│   └── engine.py            # AIRecommendationEngine with multi-backend support
├── playlist/                 # Playlist management
│   ├── __init__.py
│   └── templates.py         # Playlist template management
├── storage/                  # Data persistence
│   ├── __init__.py
│   └── cache.py             # RatingsCache (SQLite)
├── scheduler/                # Cron scheduling
│   ├── __init__.py
│   └── cron.py              # Scheduling utilities
├── monitoring/               # Observability
│   ├── __init__.py
│   ├── metrics.py           # Prometheus metrics
│   └── circuit_breaker.py  # Circuit breaker pattern
├── web/                      # Web UI
│   ├── __init__.py
│   ├── app.py               # Flask application
│   └── templates/
│       └── dashboard.html   # Web dashboard
├── models/                   # Data models
│   ├── __init__.py
│   └── config_models.py     # Pydantic validation models
└── utils/                    # Utilities
    ├── __init__.py
    ├── auth.py              # Subsonic authentication
    ├── secrets.py           # Docker secrets support
    ├── retry.py             # Retry with backoff
    ├── batch.py             # Batch processing
    └── logging_config.py    # Structured logging
```

## Key Components

### 1. Configuration Management (`config.py`)

- Loads configuration from environment variables
- Supports Docker secrets for sensitive data
- Validates configuration using Pydantic models
- Provides sensible defaults

### 2. API Clients (`api/`)

#### NavidromeAPI (`navidrome.py`)
- Navidrome/Subsonic API wrapper
- Async operations for performance
- Fuzzy song matching with version detection
- Duplicate detection
- Playlist management
- Star rating integration

#### OctoFiestaTrigger (`navidrome.py`)
- Triggers Octo-Fiesta downloads
- Dry-run support

#### LastFMAPI (`lastfm.py`)
- Last.fm recommendations
- Retry logic with backoff

#### ListenBrainzAPI (`listenbrainz.py`)
- ListenBrainz recommendations
- Playlist fetching

#### AudioMuseClient (`audiomuse.py`)
- AudioMuse-AI integration
- Sonic analysis-based playlists

### 3. AI Engine (`ai/engine.py`)

- Multi-backend support (Gemini, OpenAI, Groq, Ollama, etc.)
- Prompt caching for efficiency
- Rate limit handling with exponential backoff
- Daily call limiting
- Library change detection
- JSON validation

### 4. Monitoring (`monitoring/`)

#### Prometheus Metrics (`metrics.py`)
- Counters: playlists created, songs downloaded, API calls
- Histograms: API latency
- Gauges: AI tokens, last run stats
- HTTP server on port 9090 (configurable)

#### Circuit Breaker (`circuit_breaker.py`)
- Prevents cascading failures
- States: CLOSED, OPEN, HALF_OPEN
- Configurable thresholds and timeouts
- Auto-recovery

### 5. Web UI (`web/`)

- Flask-based dashboard
- Real-time status monitoring
- Service health checks
- Statistics display
- Auto-refresh every 30 seconds
- Runs on port 5000 (configurable)

### 6. Storage (`storage/cache.py`)

- SQLite-based ratings cache
- Daily scan caching
- Low-rated song filtering

### 7. Utilities (`utils/`)

- **auth.py**: Subsonic MD5 token authentication
- **secrets.py**: Docker secrets support
- **retry.py**: Exponential backoff retry logic
- **batch.py**: Async batch processing
- **logging_config.py**: Structured logging (JSON/text)

### 8. Playlist Templates (`playlist/templates.py`)

- YAML-based template definitions
- Mood filters and characteristics
- Time-of-day support
- AI prompt generation

### 9. Scheduler (`scheduler/cron.py`)

- Cron expression support via croniter
- Wait and run loop
- Interval calculation

## Backward Compatibility

The original `octogen.py` has been updated to:

1. Import classes from new modules when available
2. Fall back to inline implementations if modules not found
3. Maintain identical command-line interface
4. Preserve all environment variable names
5. Keep same behavior by default

This means existing Docker containers and configurations continue to work without any changes.

## New Features

### Optional Features (Opt-in)

All new features are disabled by default and can be enabled via environment variables:

- **Prometheus Metrics**: `METRICS_ENABLED=true` (default: true)
- **Web UI**: `WEB_UI_ENABLED=true` (default: false)
- **Circuit Breaker**: Enabled by default, configurable thresholds
- **Playlist Templates**: Optional YAML file
- **Docker Secrets**: Automatic detection
- **Structured Logging**: `LOG_FORMAT=json` (default: text)
- **Batch Processing**: Configurable batch size and concurrency

### Configuration Validation

Pydantic models validate:
- URL formats
- API key presence (not placeholders)
- Numeric ranges
- Required fields
- Cron expressions

## Data Flow

1. **Startup**
   - Load configuration from environment/secrets
   - Validate configuration with Pydantic
   - Initialize metrics server (if enabled)
   - Start web UI (if enabled)
   - Acquire file lock

2. **Main Loop**
   - Connect to Navidrome
   - Scan library for ratings (with caching)
   - Generate AI recommendations (with circuit breaker)
   - Fetch recommendations from Last.fm/ListenBrainz (optional)
   - Process recommendations in batches
   - Check for existing songs (fuzzy matching)
   - Trigger downloads via Octo-Fiesta
   - Create playlists
   - Wait for library scan
   - Record metrics

3. **Scheduling** (optional)
   - Calculate next run from cron expression
   - Wait until scheduled time
   - Execute main loop
   - Repeat

## Error Handling

### Circuit Breaker
- Tracks failures per service
- Opens circuit after threshold (default: 5 failures)
- Attempts recovery after timeout (default: 60s)
- Transitions through CLOSED → OPEN → HALF_OPEN → CLOSED

### Retry Logic
- Exponential backoff (1s, 2s, 4s)
- Configurable max retries (default: 3)
- Catches specific exception types

### Rate Limiting
- Detects rate limit errors
- Rolls back call counter
- Waits with exponential backoff
- Suggests alternative providers

## Performance Optimizations

1. **Async Operations**
   - Parallel album scanning
   - Concurrent downloads (configurable)
   - Batch processing with backpressure

2. **Caching**
   - Daily ratings cache (SQLite)
   - AI prompt caching (Gemini)
   - Library hash for change detection
   - In-memory response caching

3. **Configurable Limits**
   - Album batch size (default: 500)
   - Max albums scan (default: 10000)
   - Download batch size (default: 5)
   - Download concurrency (default: 3)
   - Context songs (default: 500)

## Security

### Docker Secrets
- Reads secrets from `/run/secrets/`
- Falls back to environment variables
- Supports all sensitive configuration

### Validation
- URL format checking
- API key validation (not placeholders)
- Non-empty required fields
- Numeric range validation

### Isolation
- Circuit breaker prevents cascading failures
- File locking prevents concurrent runs
- Health checks for service monitoring

## Extensibility

### Adding New Music Sources
1. Create new API client in `api/`
2. Implement client class with standard interface
3. Add configuration in `models/config_models.py`
4. Integrate in main engine

### Adding New AI Backends
1. Add backend in `ai/engine.py`
2. Implement `_generate_with_<backend>()` method
3. Update configuration validation
4. Test with existing prompts

### Adding New Metrics
1. Define metric in `monitoring/metrics.py`
2. Initialize in `init_metrics()`
3. Record at appropriate points in code
4. Document in README

## Testing

### Module Tests
```bash
# Test imports
python3 -c "import octogen; print('OK')"

# Test specific modules
python3 -c "from octogen.config import load_config_from_env; print('OK')"
python3 -c "from octogen.monitoring.metrics import setup_metrics; print('OK')"
```

### Integration Tests
```bash
# Dry run
python3 octogen.py --dry-run

# With metrics
METRICS_ENABLED=true python3 octogen.py --dry-run

# With web UI
WEB_UI_ENABLED=true python3 octogen.py
```

### Docker Build
```bash
docker build -t octogen:test .
docker run --rm octogen:test python3 -c "import octogen; print('OK')"
```

## Migration Guide

### For Existing Users
No changes required! Your existing configuration continues to work.

### To Enable New Features

1. **Prometheus Metrics**
   ```bash
   METRICS_ENABLED=true
   METRICS_PORT=9090  # optional, this is default
   ```
   Access at: `http://localhost:9090/metrics`

2. **Web UI**
   ```bash
   WEB_UI_ENABLED=true
   WEB_UI_PORT=5000  # optional, this is default
   ```
   Access at: `http://localhost:5000`

3. **Docker Secrets**
   ```yaml
   # docker-compose.yml
   services:
     octogen:
       secrets:
         - navidrome_password
         - ai_api_key
   secrets:
     navidrome_password:
       file: ./secrets/navidrome_password.txt
     ai_api_key:
       file: ./secrets/ai_api_key.txt
   ```

4. **Playlist Templates**
   ```bash
   PLAYLIST_TEMPLATES_FILE=/config/playlist_templates.yaml
   ```
   Create `/config/playlist_templates.yaml` with your templates

5. **Structured Logging**
   ```bash
   LOG_FORMAT=json
   ```

6. **Batch Processing**
   ```bash
   DOWNLOAD_BATCH_SIZE=10
   DOWNLOAD_CONCURRENCY=5
   ```

## Future Enhancements

Potential areas for expansion:
- GraphQL API
- WebSocket support for real-time updates
- Database backend (PostgreSQL)
- Multi-user support
- Recommendation algorithms
- Plugin system
- Mobile app integration

## Contributing

When adding new features:
1. Maintain backward compatibility
2. Add Pydantic validation for new config
3. Add metrics for new operations
4. Update documentation
5. Add type hints
6. Follow existing code style
7. Test with --dry-run
