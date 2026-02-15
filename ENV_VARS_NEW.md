# New Environment Variables (v2.0)

This document describes the new environment variables added in the v2.0 refactoring.

## Monitoring and Metrics

### METRICS_ENABLED
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable Prometheus metrics collection and HTTP server
- **Example**: `METRICS_ENABLED=true`

### METRICS_PORT
- **Type**: Integer
- **Default**: `9090`
- **Range**: 1024-65535
- **Description**: Port for Prometheus metrics HTTP server
- **Example**: `METRICS_PORT=9090`

## Circuit Breaker

### CIRCUIT_BREAKER_THRESHOLD
- **Type**: Integer
- **Default**: `5`
- **Range**: 1+
- **Description**: Number of failures before opening circuit
- **Example**: `CIRCUIT_BREAKER_THRESHOLD=5`

### CIRCUIT_BREAKER_TIMEOUT
- **Type**: Integer
- **Default**: `60`
- **Range**: 10+
- **Description**: Seconds to wait before attempting recovery
- **Example**: `CIRCUIT_BREAKER_TIMEOUT=60`

## Web UI

### WEB_UI_ENABLED
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enable Flask web UI dashboard
- **Example**: `WEB_UI_ENABLED=true`

### WEB_UI_PORT
- **Type**: Integer
- **Default**: `5000`
- **Range**: 1024-65535
- **Description**: Port for web UI HTTP server
- **Example**: `WEB_UI_PORT=5000`

## Batch Processing

### DOWNLOAD_BATCH_SIZE
- **Type**: Integer
- **Default**: `5`
- **Range**: 1-50
- **Description**: Number of songs to download per batch
- **Example**: `DOWNLOAD_BATCH_SIZE=10`

### DOWNLOAD_CONCURRENCY
- **Type**: Integer
- **Default**: `3`
- **Range**: 1-20
- **Description**: Maximum concurrent downloads
- **Example**: `DOWNLOAD_CONCURRENCY=5`

## Logging

### LOG_FORMAT
- **Type**: String
- **Default**: `text`
- **Options**: `text`, `json`
- **Description**: Log output format (text or structured JSON)
- **Example**: `LOG_FORMAT=json`

### SHOW_PROGRESS
- **Type**: Boolean
- **Default**: `true`
- **Description**: Show progress indicators in terminal
- **Example**: `SHOW_PROGRESS=false`

## Playlist Templates

### PLAYLIST_TEMPLATES_FILE
- **Type**: String
- **Default**: `/config/playlist_templates.yaml`
- **Description**: Path to playlist templates YAML file
- **Example**: `PLAYLIST_TEMPLATES_FILE=/custom/templates.yaml`

## Docker Secrets Support

All sensitive environment variables now support Docker secrets:

- `NAVIDROME_PASSWORD` → `/run/secrets/navidrome_password`
- `AI_API_KEY` → `/run/secrets/ai_api_key`
- `LASTFM_API_KEY` → `/run/secrets/lastfm_api_key`
- `LISTENBRAINZ_TOKEN` → `/run/secrets/listenbrainz_token`
- `AUDIOMUSE_AI_API_KEY` → `/run/secrets/audiomuse_ai_api_key`

The system automatically checks `/run/secrets/` first, then falls back to environment variables.

## Example docker-compose.yml with New Features

```yaml
version: '3.8'

services:
  octogen:
    image: blueion76/octogen:latest
    container_name: octogen
    restart: unless-stopped
    
    environment:
      # Required (unchanged)
      NAVIDROME_URL: "http://navidrome:4533"
      NAVIDROME_USER: "admin"
      OCTOFIESTA_URL: "http://octofiesta:8080"
      
      # AI Configuration (unchanged)
      AI_API_KEY: "your-gemini-api-key"
      AI_MODEL: "gemini-2.5-flash"
      AI_BACKEND: "gemini"
      
      # NEW: Monitoring
      METRICS_ENABLED: "true"
      METRICS_PORT: "9090"
      
      # NEW: Web UI
      WEB_UI_ENABLED: "true"
      WEB_UI_PORT: "5000"
      
      # NEW: Circuit Breaker
      CIRCUIT_BREAKER_THRESHOLD: "5"
      CIRCUIT_BREAKER_TIMEOUT: "60"
      
      # NEW: Batch Processing
      DOWNLOAD_BATCH_SIZE: "10"
      DOWNLOAD_CONCURRENCY: "5"
      
      # NEW: Logging
      LOG_FORMAT: "json"
      SHOW_PROGRESS: "false"
      
      # Scheduling (unchanged)
      SCHEDULE_ENABLED: "true"
      SCHEDULE_CRON: "0 3 * * *"
    
    # NEW: Expose metrics and web UI ports
    ports:
      - "9090:9090"  # Prometheus metrics
      - "5000:5000"  # Web UI dashboard
    
    # NEW: Config volume for templates
    volumes:
      - ./data:/data
      - ./config:/config
    
    # NEW: Docker secrets (optional)
    secrets:
      - navidrome_password
      - ai_api_key

# NEW: Define secrets
secrets:
  navidrome_password:
    file: ./secrets/navidrome_password.txt
  ai_api_key:
    file: ./secrets/ai_api_key.txt
```

## Backward Compatibility

All new environment variables are **optional** and have sensible defaults. Existing configurations continue to work without any changes.

## Configuration Validation

The new Pydantic-based validation provides helpful error messages:

```
Configuration validation failed: URL must start with http:// or https://
Configuration validation failed: API key appears to be a placeholder
Configuration validation failed: Field cannot be empty
Configuration validation failed: Log level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Health Checks

The existing health check continues to work. Add additional checks:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:9090/metrics", "||", "exit", "1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## Metrics Available

When `METRICS_ENABLED=true`, the following metrics are exposed at `http://localhost:9090/metrics`:

- `octogen_playlists_created_total{source}` - Counter
- `octogen_songs_downloaded_total` - Counter
- `octogen_api_calls_total{service,status}` - Counter
- `octogen_api_latency_seconds{service}` - Histogram
- `octogen_ai_tokens_used` - Gauge
- `octogen_last_run_timestamp` - Gauge
- `octogen_last_run_duration_seconds` - Gauge

## Web UI Endpoints

When `WEB_UI_ENABLED=true`, the following endpoints are available:

- `GET /` - Dashboard home page
- `GET /api/status` - Current status JSON
- `GET /api/stats` - Statistics JSON
- `GET /api/health` - Health check JSON

## Migration Checklist

For users migrating from v1.x to v2.0:

- [ ] Review new environment variables
- [ ] Decide which new features to enable
- [ ] Update docker-compose.yml to expose new ports (optional)
- [ ] Create playlist templates YAML file (optional)
- [ ] Set up Docker secrets (optional)
- [ ] Configure monitoring/alerting for metrics (optional)
- [ ] Test with `--dry-run` first
- [ ] Pull new image: `docker pull blueion76/octogen:latest`
- [ ] Restart container

No configuration changes are **required** - all new features are opt-in!
