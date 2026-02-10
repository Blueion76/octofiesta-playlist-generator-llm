# 📋 Environment Variables Reference

Complete reference for all OctoGen environment variables.

---

## 🔴 Required Variables

These variables **must** be set for OctoGen to work.

### NAVIDROME_URL
**Description**: URL of your Navidrome server  
**Format**: `http://hostname:port` or `https://hostname:port`  
**Examples**:
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_URL=http://navidrome:4533
NAVIDROME_URL=https://music.example.com
```
**Notes**:
- Do not include trailing slash
- If in Docker, can use service name: `http://navidrome:4533`
- If accessing host from container: `http://host.docker.internal:4533`

---

### NAVIDROME_USER
**Description**: Navidrome username  
**Format**: String  
**Example**:
```bash
NAVIDROME_USER=admin
```

---

### NAVIDROME_PASSWORD
**Description**: Navidrome password  
**Format**: String  
**Example**:
```bash
NAVIDROME_PASSWORD=your_secure_password
```
**Notes**:
- Password is sent securely via Subsonic API (MD5 token with salt)
- Not stored in plain text in logs

---

### OCTOFIESTA_URL
**Description**: URL of your Octo-Fiesta server  
**Format**: `http://hostname:port`  
**Examples**:
```bash
OCTOFIESTA_URL=http://192.168.1.100:5274
OCTOFIESTA_URL=http://octo-fiesta:5274
```
**Notes**:
- Required for automatic downloading of missing tracks
- Uses same Navidrome credentials

---

### AI_API_KEY
**Description**: API key for your AI provider  
**Format**: String (provider-specific)  
**Examples**:
```bash
# Gemini
AI_API_KEY=AIzaSyABC123xyz...

# Groq
AI_API_KEY=gsk_abc123xyz...

# OpenAI
AI_API_KEY=sk-abc123xyz...

# Ollama (local)
AI_API_KEY=ollama
```
**Get Keys**:
- **Gemini**: https://aistudio.google.com/apikey (free tier)
- **Groq**: https://console.groq.com (free tier)
- **OpenAI**: https://platform.openai.com/api-keys
- **Ollama**: Use `ollama` as the key

---

## 🟡 AI Configuration (Optional)

### AI_MODEL
**Description**: AI model to use for recommendations  
**Default**: `gemini-2.5-flash`  
**Examples**:
```bash
# Gemini
AI_MODEL=gemini-2.5-flash
AI_MODEL=gemini-2.0-flash-exp

# Groq
AI_MODEL=llama-3.3-70b-versatile
AI_MODEL=mixtral-8x7b-32768

# OpenAI
AI_MODEL=gpt-4o
AI_MODEL=gpt-4o-mini

# Ollama
AI_MODEL=llama3.2
AI_MODEL=mixtral
```

---

### AI_BACKEND
**Description**: AI backend to use  
**Default**: `gemini`  
**Options**: `gemini`, `openai`  
**Examples**:
```bash
# For Gemini (native SDK with caching)
AI_BACKEND=gemini

# For OpenAI, Groq, Ollama, OpenRouter (OpenAI-compatible)
AI_BACKEND=openai
```
**Notes**:
- `gemini`: Uses native Gemini SDK with context caching (more efficient)
- `openai`: Uses OpenAI library (compatible with many providers)

---

### AI_BASE_URL
**Description**: Custom API endpoint URL  
**Default**: None (uses provider default)  
**Examples**:
```bash
# Groq
AI_BASE_URL=https://api.groq.com/openai/v1

# Ollama
AI_BASE_URL=http://host.docker.internal:11434/v1

# OpenRouter
AI_BASE_URL=https://openrouter.ai/api/v1

# Custom OpenAI-compatible
AI_BASE_URL=https://api.custom.com/v1
```
**Notes**:
- Only used when `AI_BACKEND=openai`
- Leave empty for official OpenAI API

---

### AI_MAX_CONTEXT_SONGS
**Description**: Maximum number of songs to send to AI for context  
**Default**: `500`  
**Range**: `100` to `1000`  
**Example**:
```bash
AI_MAX_CONTEXT_SONGS=500
```
**Notes**:
- Higher = more accurate but more expensive
- Lower = cheaper but less personalized

---

### AI_MAX_OUTPUT_TOKENS
**Description**: Maximum tokens AI can generate in response  
**Default**: `65535`  
**Range**: `10000` to `65535`  
**Example**:
```bash
AI_MAX_OUTPUT_TOKENS=65535
```
**Notes**:
- 11 playlists × 30-50 songs requires ~40,000-50,000 tokens
- Don't set below 40,000

---

## 🟢 Last.fm Integration (Optional)

### LASTFM_ENABLED
**Description**: Enable Last.fm recommendations  
**Default**: `false`  
**Options**: `true`, `false`  
**Example**:
```bash
LASTFM_ENABLED=true
```

---

### LASTFM_API_KEY
**Description**: Last.fm API key  
**Format**: String  
**Example**:
```bash
LASTFM_API_KEY=abc123xyz456...
```
**Get Key**: https://www.last.fm/api/account/create

---

### LASTFM_USERNAME
**Description**: Your Last.fm username  
**Format**: String  
**Example**:
```bash
LASTFM_USERNAME=your_username
```

---

## 🟢 ListenBrainz Integration (Optional)

### LISTENBRAINZ_ENABLED
**Description**: Enable ListenBrainz recommendations  
**Default**: `false`  
**Options**: `true`, `false`  
**Example**:
```bash
LISTENBRAINZ_ENABLED=true
```

---

### LISTENBRAINZ_USERNAME
**Description**: Your ListenBrainz username  
**Format**: String  
**Example**:
```bash
LISTENBRAINZ_USERNAME=your_username
```

---

### LISTENBRAINZ_TOKEN
**Description**: ListenBrainz user token  
**Format**: String  
**Example**:
```bash
LISTENBRAINZ_TOKEN=abc123-xyz456-...
```
**Get Token**: https://listenbrainz.org/profile/ → User token

---

## ⚙️ Performance Tuning (Optional)

### PERF_ALBUM_BATCH_SIZE
**Description**: Number of albums to fetch per API request  
**Default**: `500`  
**Range**: `100` to `1000`  
**Example**:
```bash
PERF_ALBUM_BATCH_SIZE=500
```
**Notes**:
- Higher = fewer API calls but more memory
- Lower = more API calls but less memory

---

### PERF_MAX_ALBUMS_SCAN
**Description**: Maximum albums to scan for ratings  
**Default**: `10000`  
**Range**: `1000` to `50000`  
**Example**:
```bash
PERF_MAX_ALBUMS_SCAN=10000
```
**Notes**:
- Prevents timeouts on huge libraries
- Increase if you have large library

---

### PERF_SCAN_TIMEOUT
**Description**: Timeout for Navidrome library scan (seconds)  
**Default**: `60`  
**Range**: `30` to `300`  
**Example**:
```bash
PERF_SCAN_TIMEOUT=60
```

---

### PERF_DOWNLOAD_DELAY
**Description**: Delay between downloads (seconds)  
**Default**: `6`  
**Range**: `1` to `30`  
**Example**:
```bash
PERF_DOWNLOAD_DELAY=6
```
**Notes**:
- Prevents overwhelming Octo-Fiesta
- Decrease for faster processing
- Increase if downloads fail

---

### PERF_POST_SCAN_DELAY
**Description**: Delay after Navidrome scan completes (seconds)  
**Default**: `2`  
**Range**: `1` to `10`  
**Example**:
```bash
PERF_POST_SCAN_DELAY=2
```
**Notes**:
- Ensures scan is fully complete before searching
- Increase if newly downloaded songs not found

---

## 🔧 System Configuration (Optional)

### LOG_LEVEL
**Description**: Logging verbosity level  
**Default**: `INFO`  
**Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`  
**Example**:
```bash
LOG_LEVEL=INFO
```
**When to use**:
- `DEBUG`: Troubleshooting, see all details
- `INFO`: Normal operation (recommended)
- `WARNING`: Only warnings and errors
- `ERROR`: Only errors

---

### OCTOGEN_DATA_DIR
**Description**: Directory for data storage (inside container)  
**Default**: `/data`  
**Example**:
```bash
OCTOGEN_DATA_DIR=/data
```
**Notes**:
- Usually don't need to change this
- Mount external volume to this path

---

## 📝 Complete Examples

### Minimal Configuration (Gemini)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:5274
AI_API_KEY=AIzaSyABC123...
```

### With Groq (Fast & Free)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:5274

AI_BACKEND=openai
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
AI_API_KEY=gsk_abc123...
```

### With Ollama (Local)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:5274

AI_BACKEND=openai
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama
```

### Full Featured
```bash
# Navidrome
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123

# Octo-Fiesta
OCTOFIESTA_URL=http://192.168.1.100:5274

# AI (Gemini)
AI_API_KEY=AIzaSyABC123...
AI_MODEL=gemini-2.5-flash
AI_BACKEND=gemini
AI_MAX_CONTEXT_SONGS=500
AI_MAX_OUTPUT_TOKENS=65535

# Last.fm
LASTFM_ENABLED=true
LASTFM_API_KEY=your_lastfm_key
LASTFM_USERNAME=your_username

# ListenBrainz
LISTENBRAINZ_ENABLED=true
LISTENBRAINZ_USERNAME=your_listenbrainz_username
LISTENBRAINZ_TOKEN=your_token

# Performance
PERF_ALBUM_BATCH_SIZE=500
PERF_MAX_ALBUMS_SCAN=10000
PERF_SCAN_TIMEOUT=60
PERF_DOWNLOAD_DELAY=6
PERF_POST_SCAN_DELAY=2

# System
LOG_LEVEL=INFO
```

---

## 🔗 Related Documentation

- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Main Documentation**: [README.md](README.md)
- **GitHub Setup**: [GITHUB_WEB_UI_SETUP.md](GITHUB_WEB_UI_SETUP.md)

---

## 💡 Tips

### Docker Compose
Use `.env` file with docker-compose:
```yaml
services:
  octogen:
    image: blueion76/octogen:latest
    env_file:
      - .env
```

### Docker Run
Pass environment file:
```bash
docker run --env-file .env blueion76/octogen:latest
```

### Docker Secrets
For production, use Docker secrets:
```bash
echo "your_password" | docker secret create navidrome_password -
```

### Environment Priority
If same variable set multiple ways:
1. Command line (`-e VAR=value`)
2. Environment file (`--env-file .env`)
3. Default value in code

---

**All variables are documented with examples!** 📚
