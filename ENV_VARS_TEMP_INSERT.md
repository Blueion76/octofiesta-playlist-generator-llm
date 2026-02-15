
## 📊 Monitoring and Metrics (Optional)

### METRICS_ENABLED
**Description**: Enable Prometheus metrics collection and HTTP server  
**Default**: `true`  
**Options**: `true`, `false`  
**Example**:
```bash
METRICS_ENABLED=true
```
**Notes**:
- Exposes metrics on port 9090 (configurable via METRICS_PORT)
- Provides counters, histograms, and gauges for monitoring
- Metrics include: playlists created, songs downloaded, API calls, latency, tokens used
- Access metrics at `http://localhost:9090/metrics`

---

### METRICS_PORT
**Description**: Port for Prometheus metrics HTTP server  
**Default**: `9090`  
**Range**: 1024-65535  
**Example**:
```bash
METRICS_PORT=9090
```
**Notes**:
- Only applies when METRICS_ENABLED=true
- Ensure port is not in use by another service
- Must be exposed in Docker: `-p 9090:9090`

---

### CIRCUIT_BREAKER_THRESHOLD
**Description**: Number of failures before opening circuit breaker  
**Default**: `5`  
**Range**: 1+  
**Example**:
```bash
CIRCUIT_BREAKER_THRESHOLD=5
```
**Notes**:
- Circuit breaker prevents cascading failures to external APIs
- After threshold failures, circuit opens and requests fail fast
- Helps protect external services from overload

---

### CIRCUIT_BREAKER_TIMEOUT
**Description**: Seconds to wait before attempting recovery  
**Default**: `60`  
**Range**: 10+  
**Example**:
```bash
CIRCUIT_BREAKER_TIMEOUT=60
```
**Notes**:
- After timeout, circuit enters half-open state and tries one request
- If successful, circuit closes; if failed, reopens for another timeout period

---

## 🌐 Web UI Dashboard (Optional)

### WEB_UI_ENABLED
**Description**: Enable Flask web UI dashboard  
**Default**: `false`  
**Options**: `true`, `false`  
**Example**:
```bash
WEB_UI_ENABLED=true
```
**Notes**:
- Provides web-based monitoring dashboard
- Shows real-time status, statistics, and service health
- Auto-refreshes every 30 seconds
- Access at `http://localhost:5000` (or configured port)

---

### WEB_UI_PORT
**Description**: Port for web UI HTTP server  
**Default**: `5000`  
**Range**: 1024-65535  
**Example**:
```bash
WEB_UI_PORT=5000
```
**Notes**:
- Only applies when WEB_UI_ENABLED=true
- Must be exposed in Docker: `-p 5000:5000`
- Dashboard shows: status, stats, health checks, playlists

---

## ⚡ Batch Processing (Optional)

### DOWNLOAD_BATCH_SIZE
**Description**: Number of songs to download per batch  
**Default**: `5`  
**Range**: 1-50  
**Example**:
```bash
DOWNLOAD_BATCH_SIZE=10
```
**Notes**:
- Larger batches may be faster but use more memory
- Smaller batches provide better progress visibility
- Recommended: 5-10 for most use cases

---

### DOWNLOAD_CONCURRENCY
**Description**: Maximum concurrent downloads  
**Default**: `3`  
**Range**: 1-20  
**Example**:
```bash
DOWNLOAD_CONCURRENCY=5
```
**Notes**:
- Higher concurrency speeds up downloads but increases load
- Too high may cause timeouts or rate limiting
- Recommended: 3-5 for most use cases

---

## 📝 Logging Configuration (Optional)

### LOG_FORMAT
**Description**: Log output format  
**Default**: `text`  
**Options**: `text`, `json`  
**Example**:
```bash
LOG_FORMAT=json
```
**Notes**:
- `text`: Human-readable format (default)
- `json`: Structured JSON for log aggregation systems
- JSON format includes: timestamp, level, logger, message, context

---

### SHOW_PROGRESS
**Description**: Show progress indicators in terminal  
**Default**: `true`  
**Options**: `true`, `false`  
**Example**:
```bash
SHOW_PROGRESS=false
```
**Notes**:
- Displays progress bars and spinners for long operations
- Automatically disabled in non-TTY environments (Docker logs)
- Set to `false` if progress indicators cause issues

---

## 📋 Playlist Templates (Optional)

### PLAYLIST_TEMPLATES_FILE
**Description**: Path to playlist templates YAML file  
**Default**: `/config/playlist_templates.yaml`  
**Example**:
```bash
PLAYLIST_TEMPLATES_FILE=/custom/templates.yaml
```
**Notes**:
- Allows customization of playlist generation
- Default templates included: Morning Motivation, Focus Deep Work, Evening Wind Down, Workout Intensity
- Create custom templates with mood filters, genres, and characteristics
- Mount config directory: `-v ./config:/config`

---

