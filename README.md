# 🎵 OctoGen - AI-Powered Music Discovery for Navidrome

[![Docker Hub](https://img.shields.io/docker/pulls/blueion76/octogen?logo=docker)](https://hub.docker.com/r/blueion76/octogen)

**OctoGen** automatically generates personalized music playlists for your Navidrome server using AI. It creates 11 curated playlists with over 350 songs, seamlessly integrating with [Octo-Fiesta](https://github.com/V1ck3s/octo-fiesta) to download missing tracks.

Built with AI assistance. Contributions and pull requests welcome!

---

## ✨ Features

### 🤖 AI-Powered Recommendations
- **Multiple AI providers**: Gemini, OpenAI, Groq, Ollama, OpenRouter
- **Smart context caching**: Efficient, low-cost API usage
- **Variety seed**: Different recommendations every day

### 🎵 Generated Playlists
- **Discovery Weekly** (50 songs) - New music discoveries
- **Daily Mix 1-6** (30 songs each) - Genre-based mixes
- **Chill Vibes** (30 songs) - Relaxing tracks
- **Workout Energy** (30 songs) - High-energy music
- **Focus Flow** (30 songs) - Ambient/instrumental
- **Drive Time** (30 songs) - Upbeat driving music

**Total: 11 playlists, 350+ songs automatically curated!**

### 🎛️ Hybrid Mode (AudioMuse-AI Integration)

OctoGen can optionally integrate with **AudioMuse-AI** for enhanced sonic analysis:

- **Default Mode**: 30 songs from LLM (current behavior)
- **Hybrid Mode**: 25 songs from AudioMuse-AI + 5 songs from LLM

Enable hybrid mode by setting:
```bash
AUDIOMUSE_ENABLED=true
AUDIOMUSE_URL=http://localhost:8000
```

This combines:
- **AudioMuse-AI**: Sonic similarity, mood analysis, audio feature matching
- **LLM**: Creative variety, metadata-based recommendations

See [AudioMuse-AI Setup](#-audiomuse-ai-setup-optional) below.

### 🎯 Smart Features
- **Star rating filtering**: Excludes 1-2 star rated songs
- **Duplicate detection**: No repeated tracks across playlists
- **Automatic downloads**: Missing songs fetched via Octo-Fiesta
- **Daily cache**: Efficient library scanning
- **Async operations**: Fast, parallel processing
- **Last.fm & ListenBrainz**: Optional integration
- **Built-in scheduling**: No external cron needed! 🕐

---

## 🚀 Quick Start

### Prerequisites
- **Navidrome** server running
- **Octo-Fiesta** configured for downloads
- **AI API key** (Gemini recommended - free tier available)

### 1. Get Gemini API Key (Free)
Visit: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### 2. Create Configuration

```bash
# Create .env file
cat > .env << 'EOF'
# Required
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=your_password
OCTOFIESTA_URL=http://192.168.1.100:8080
AI_API_KEY=your_llm_api_key

# Optional
AI_MODEL=gemini-2.5-flash
AI_BACKEND=gemini
LOG_LEVEL=INFO

# Scheduling 
SCHEDULE_CRON=0 6 * * *
TZ=America/Chicago
EOF
```

### 3. Run with Docker

```bash
# Pull the image
docker pull blueion76/octogen:latest

# Run OctoGen with automatic scheduling
docker run -d \
  --name octogen \
  -v octogen-data:/data \
  --env-file .env \
  --restart unless-stopped \
  blueion76/octogen:latest

# Check logs (see countdown to next run!)
docker logs -f octogen
```

### 4. Check Your Navidrome
Open Navidrome and find your new playlists! 🎉

**Playlists update automatically at 6 AM daily!**

---

## 🐳 Docker Compose (Recommended)

```yaml
version: '3.8'

services:
  octogen:
    image: blueion76/octogen:latest
    container_name: octogen
    restart: unless-stopped
    volumes:
      - octogen-data:/data
    environment:
      # Required
      NAVIDROME_URL: http://navidrome:4533
      NAVIDROME_USER: admin
      NAVIDROME_PASSWORD: ${NAVIDROME_PASSWORD}
      OCTOFIESTA_URL: http://octofiesta:8080
      AI_API_KEY: ${GEMINI_API_KEY}

      # Scheduling 
      SCHEDULE_CRON: "0 6 * * *"  # Daily at 6 AM
      TZ: America/Chicago

      # Optional
      AI_MODEL: gemini-2.5-flash
      AI_BACKEND: gemini
      LOG_LEVEL: INFO

volumes:
  octogen-data:
```

Run:
```bash
docker-compose up -d
docker-compose logs -f octogen
```

---

## 🎨 AudioMuse-AI Setup (Optional)

To enable hybrid playlist generation with sonic analysis:

### 1. Install AudioMuse-AI

Follow the [AudioMuse-AI documentation](https://github.com/NeptuneHub/AudioMuse-AI) to deploy:

```yaml
# docker-compose.yml excerpt
services:
  audiomuse-flask:
    image: ghcr.io/neptunehub/audiomuse-ai:latest
    ports:
      - "8000:8000"
    environment:
      SERVICE_TYPE: "flask"
      MEDIASERVER_TYPE: "navidrome"
      NAVIDROME_URL: "http://navidrome:4533"
      NAVIDROME_USER: "admin"
      NAVIDROME_PASSWORD: "${NAVIDROME_PASSWORD}"
      # ... other AudioMuse config
```

### 2. Run Initial Analysis

1. Open AudioMuse-AI at `http://localhost:8000`
2. Navigate to "Analysis and Clustering"
3. Click "Start Analysis" (one-time, analyzes your library)
4. Wait for completion

### 3. Enable in OctoGen

Add to your `.env`:

```bash
AUDIOMUSE_ENABLED=true
AUDIOMUSE_URL=http://localhost:8000
AUDIOMUSE_AI_PROVIDER=gemini
AUDIOMUSE_AI_MODEL=gemini-2.5-flash
AUDIOMUSE_AI_API_KEY=your_api_key_here
```

### 4. Adjust Mix Ratios (Optional)

```bash
AUDIOMUSE_SONGS_PER_MIX=25  # Songs from AudioMuse (default: 25)
LLM_SONGS_PER_MIX=5         # Songs from LLM (default: 5)
```

**Note:** Total songs per daily mix remains 30.

---

## 🔧 Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `NAVIDROME_URL` | Navidrome server URL | `http://192.168.1.100:4533` |
| `NAVIDROME_USER` | Navidrome username | `admin` |
| `NAVIDROME_PASSWORD` | Navidrome password | `your_password` |
| `OCTOFIESTA_URL` | Octo-Fiesta server URL | `http://192.168.1.100:8080` |
| `AI_API_KEY` | AI provider API key | `your_llm_api_key` |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MODEL` | `gemini-2.5-flash` | AI model to use |
| `AI_BACKEND` | `gemini` | Backend: `gemini` or `openai` |
| `AI_BASE_URL` | (none) | Custom API endpoint |
| `SCHEDULE_CRON` | (none) | Cron schedule (e.g., `0 6 * * *`) |
| `TZ` | `UTC` | Timezone (e.g., `America/Chicago`) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**See [ENV_VARS.md](ENV_VARS.md) for complete reference.**

---

## 🎯 AI Provider Examples

### Gemini (Recommended - Free Tier)
```bash
AI_BACKEND=gemini
AI_MODEL=gemini-2.5-flash
AI_API_KEY=your_llm_api_key
```
**Get key:** [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Groq (Fast & Free Tier)
```bash
AI_BACKEND=openai
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
AI_API_KEY=your_groq_api_key
```
**Get key:** [https://console.groq.com](https://console.groq.com)

### OpenAI (Official)
```bash
AI_BACKEND=openai
AI_MODEL=gpt-4o
AI_API_KEY=your_openai_api_key
```

### Ollama (Local, Offline)
```bash
AI_BACKEND=openai
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama
```

### OpenRouter (100+ Models)
```bash
AI_BACKEND=openai
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=anthropic/claude-3.5-sonnet
AI_API_KEY=your_openrouter_api_key
```

---

## 🕐 Automatic Scheduling 

OctoGen now includes **built-in cron scheduling** - no external cron daemon or scripts needed!

### Quick Setup

Just add these two environment variables:

```bash
SCHEDULE_CRON=0 6 * * *    # Daily at 6 AM
TZ=America/Chicago         # Your timezone
```

The container stays running and automatically executes on schedule. You'll see countdown logs:

```
🕐 OCTOGEN SCHEDULER
══════════════════════════════════════════════════════════════════════
Schedule: 0 6 * * *
Timezone: America/Chicago
══════════════════════════════════════════════════════════════════════
📅 Next scheduled run: 2026-02-11 06:00:00
⏰ Next run in 3.5 hours (2026-02-11 06:00:00)
```

### Schedule Examples

| Schedule | Cron Expression | Description |
|----------|----------------|-------------|
| Daily at 6 AM | `0 6 * * *` | Once per day |
| Twice daily | `0 */12 * * *` | Every 12 hours |
| Every 6 hours | `0 */6 * * *` | 4 times per day |
| Weekly (Sunday 3 AM) | `0 3 * * 0` | Once per week |
| Every Monday 9 AM | `0 9 * * 1` | Weekly on Monday |

**Cron Format:**
```
* * * * *
│ │ │ │ │
│ │ │ │ └─── Day of week (0-7)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

**Test your expressions:** [crontab.guru](https://crontab.guru)

### Timezone Configuration

**Important:** Set `TZ` to get correct local times! Without it, times are in UTC.

```bash
# United States
TZ=America/New_York        # Eastern
TZ=America/Chicago         # Central  
TZ=America/Denver          # Mountain
TZ=America/Los_Angeles     # Pacific

# Europe
TZ=Europe/London           # UK
TZ=Europe/Paris            # France
TZ=Europe/Berlin           # Germany

# Other
TZ=Asia/Tokyo              # Japan
TZ=Australia/Sydney        # Australia
```

### Manual Run (No Scheduling)

Leave `SCHEDULE_CRON` unset or set to `manual`:

```bash
# Run once and exit
docker run --rm --env-file .env blueion76/octogen:latest
```

### Advanced: Kubernetes CronJob

If you prefer Kubernetes native scheduling:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: octogen
spec:
  schedule: "0 6 * * *"
  timeZone: "America/Chicago"  # Kubernetes 1.25+
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: octogen
            image: blueion76/octogen:latest
            envFrom:
            - secretRef:
                name: octogen-secrets
          restartPolicy: OnFailure
```

**Note:** Built-in scheduling is recommended for simplicity!

---

## 📊 How It Works

1. **Analyzes your Navidrome library**
   - Reads starred/favorited songs
   - Identifies top artists and genres
   - Caches ratings (daily refresh)

2. **Generates AI recommendations**
   - Sends music profile to AI
   - Excludes low-rated songs (1-2 stars)
   - Requests 11 themed playlists

3. **Creates playlists in Navidrome**
   - Searches library for each song
   - Downloads missing tracks via Octo-Fiesta
   - Adds songs to new playlists

4. **Waits for next scheduled run** (if `SCHEDULE_CRON` is set)
   - Calculates next run time
   - Shows countdown in logs
   - Automatically retries on errors

5. **Optional integrations**
   - Fetches Last.fm recommendations
   - Gets ListenBrainz suggestions
   - Merges all sources

---

## 🧪 Dry Run Mode

Test without making changes:

```bash
docker run --rm \
  -v octogen-data:/data \
  --env-file .env \
  blueion76/octogen:latest \
  python octogen.py --dry-run
```

Shows what would happen without:
- Downloading songs
- Creating playlists
- Making any changes

---

## 📁 Data Persistence

OctoGen stores data in `/data`:

```
/data/
├── octogen.log              # Application logs
├── octogen_cache.db         # Star ratings cache
├── gemini_cache.json        # AI context cache
└── octogen.lock             # Prevents duplicate runs
```

Mount a volume to persist data:
```bash
-v octogen-data:/data
```

---

## 🔍 Monitoring

### View Logs
```bash
# Real-time logs
docker logs -f octogen

# Last 100 lines
docker logs --tail 100 octogen

# Save to file
docker logs octogen > octogen.log
```

### Check Status
```bash
# Container status
docker ps -a | grep octogen

# Resource usage
docker stats octogen

# Inspect container
docker inspect octogen
```

### Verify Scheduler
```bash
# Check if scheduler is running
docker logs octogen | grep "SCHEDULER"

# See next run time
docker logs octogen | grep "Next scheduled run"

# Verify timezone
docker logs octogen | grep "Timezone:"
```

### Verify Data
```bash
# Check data directory
docker exec octogen ls -lh /data

# View log file
docker exec octogen tail -n 50 /data/octogen.log

# Check cache
docker exec octogen sqlite3 /data/octogen_cache.db "SELECT COUNT(*) FROM ratings;"
```

---

## 🛠️ Troubleshooting

### Problem: "Can't connect to Navidrome"

**Solution:**
- Check `NAVIDROME_URL` is correct
- Use Docker network name if both containers on same network
- Try: `http://navidrome:4533` instead of `http://localhost:4533`

### Problem: "AI API error"

**Solution:**
- Verify API key is correct
- Check API provider status
- Ensure you have API credits/quota
- Try different model if rate limited

### Problem: "No playlists created"

**Solution:**
- Check logs: `docker logs octogen`
- Ensure you have starred songs in Navidrome
- Verify Octo-Fiesta is running
- Try dry-run mode to see what would happen

### Problem: "Downloads not working"

**Solution:**
- Verify `OCTOFIESTA_URL` is correct
- Check Octo-Fiesta is configured properly
- Ensure Navidrome credentials are correct
- Check network connectivity between containers

### Problem: "Scheduler not working"

**Solution:**
- Verify `SCHEDULE_CRON` is set: `docker inspect octogen | grep SCHEDULE_CRON`
- Check logs for "OCTOGEN SCHEDULER" message
- Ensure container has restart policy: `--restart unless-stopped`
- Verify timezone: `docker logs octogen | grep "Timezone:"`

### Problem: "Wrong time scheduled"

**Solution:**
- Set `TZ` environment variable to your timezone
- Without `TZ`, times are in UTC
- Check current timezone in logs
- Test cron expression at [crontab.guru](https://crontab.guru)

---


**Components:**
- **Navidrome API**: Reads library, creates playlists
- **AI Provider**: Generates recommendations
- **Octo-Fiesta**: Downloads missing tracks
- **SQLite Cache**: Stores ratings (daily refresh)
- **Logs**: Application activity
- **Built-in Scheduler**: Automatic execution 

---

## 📚 Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- **[ENV_VARS.md](ENV_VARS.md)** - Complete variable reference (26 variables)

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **[Navidrome](https://www.navidrome.org/)** - Open-source music server
- **[Octo-Fiesta](https://github.com/V1ck3s/octo-fiesta)** - Automated music downloader
- **[Google Gemini](https://ai.google.dev/)** - AI recommendations
- **[Last.fm](https://www.last.fm/)** - Music discovery API
- **[ListenBrainz](https://listenbrainz.org/)** - Open music metadata

---

## 🔗 Links

- **Docker Hub**: [hub.docker.com/r/blueion76/octogen](https://hub.docker.com/r/blueion76/octogen)
- **GitHub**: [github.com/Blueion76/Octogen](https://github.com/Blueion76/Octogen)
- **GHCR**: [ghcr.io/blueion76/octogen](https://ghcr.io/blueion76/octogen)
- **Issues**: [github.com/Blueion76/Octogen/issues](https://github.com/Blueion76/Octogen/issues)

---

## ⭐ Star History

If you find this project useful, please consider giving it a star! ⭐

---

**Made with ❤️ for the self-hosted music community**
