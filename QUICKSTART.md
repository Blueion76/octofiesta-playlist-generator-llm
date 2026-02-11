# ⚡ OctoGen Quick Start

The absolute fastest way to get OctoGen running.

---

## 🎯 For Users (5 Minutes to Running)

### 1. Get Gemini API Key (Free)
Visit: **https://aistudio.google.com/apikey**
- Sign in with Google account
- Click "Create API key"
- Copy the key (looks like: `AIzaSy...`)

### 2. Create Configuration
```bash
cat > .env << 'EOF'
# Required
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=your_password
OCTOFIESTA_URL=http://192.168.1.100:8080
AI_API_KEY=your_gemini_api_key

# Optional
AI_MODEL=gemini-2.5-flash
AI_BACKEND=gemini
LOG_LEVEL=INFO

# Scheduling
SCHEDULE_CRON=0 6 * * *
TZ=America/Chicago
EOF
```

**Edit the file** with your actual values:
```bash
nano .env
```

### 3. Run Docker Container
```bash
docker run -d \
  --name octogen \
  -v octogen-data:/data \
  --env-file .env \
  --restart unless-stopped \
  blueion76/octogen:latest
```

### 4. Check Logs
```bash
docker logs -f octogen

# You'll see scheduling info:
# 🕐 OCTOGEN SCHEDULER
# Schedule: 0 6 * * *
# Timezone: America/Chicago
# 📅 Next scheduled run: 2026-02-11 06:00:00
# ⏰ Next run in 3.5 hours...
```

### 5. Check Navidrome
Open your Navidrome web interface and look for 11 new playlists! 🎉

**Done!** Your playlists are ready and will auto-update daily.

---

## 🐳 With Docker Compose (Recommended)

### 1. Create docker-compose.yml
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

      # Scheduling (NEW!)
      SCHEDULE_CRON: "0 6 * * *"  # Daily at 6 AM
      TZ: America/Chicago

      # Optional
      AI_MODEL: gemini-2.5-flash
      AI_BACKEND: gemini
      LOG_LEVEL: INFO

volumes:
  octogen-data:
```

### 2. Create .env
```bash
cat > .env << 'EOF'
NAVIDROME_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
EOF
```

Edit with your values:
```bash
nano .env
```

### 3. Start Services
```bash
docker-compose up -d
```

### 4. View Logs
```bash
docker-compose logs -f octogen
```

---

## 🔧 Configuration Examples

### Minimal (Manual Run)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:8080
AI_API_KEY=AIzaSyABC123...
```

### Scheduled Daily (Recommended)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:8080
AI_API_KEY=AIzaSyABC123...

# Run daily at 6 AM
SCHEDULE_CRON=0 6 * * *
TZ=America/Chicago
```

### Every 12 Hours
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:8080
AI_API_KEY=AIzaSyABC123...

# Run twice daily
SCHEDULE_CRON=0 */12 * * *
TZ=America/New_York
```

### With Groq (Fast & Free)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:8080

# Groq AI
AI_BACKEND=openai
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
AI_API_KEY=gsk_abc123...

# Daily schedule
SCHEDULE_CRON=0 6 * * *
TZ=America/Los_Angeles
```

### With Ollama (Local, Offline)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:8080

# Ollama (local)
AI_BACKEND=openai
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama

# Weekly on Sunday at 3 AM
SCHEDULE_CRON=0 3 * * 0
TZ=UTC
```

### With Last.fm Integration
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:8080
AI_API_KEY=AIzaSyABC123...

# Last.fm
LASTFM_ENABLED=true
LASTFM_API_KEY=your_lastfm_key
LASTFM_USERNAME=your_lastfm_username

# Daily at 6 AM
SCHEDULE_CRON=0 6 * * *
TZ=Europe/London
```

---

## 🧪 Test First (Dry Run)

Test without making any changes:

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
- Making changes to Navidrome

---

## ⏰ Built-in Scheduling (NEW!)

OctoGen now has **built-in cron scheduling** - no external cron daemon needed!

### How It Works
1. Set `SCHEDULE_CRON` environment variable
2. Container stays running
3. Executes on schedule automatically
4. Shows countdown in logs

### Schedule Examples

| Schedule | Cron Expression | Description |
|----------|----------------|-------------|
| Daily at 6 AM | `0 6 * * *` | Once per day |
| Twice daily | `0 */12 * * *` | Every 12 hours |
| Every 6 hours | `0 */6 * * *` | 4 times per day |
| Weekly (Sunday 3 AM) | `0 3 * * 0` | Once per week |
| Every Monday 9 AM | `0 9 * * 1` | Weekly on Monday |
| Every 30 minutes | `*/30 * * * *` | For testing |

### Disable Scheduling
```bash
# Leave unset or set to:
SCHEDULE_CRON=manual
# Or:
SCHEDULE_CRON=off
```

### Timezone Configuration
```bash
# Set your timezone (important!)
TZ=America/Chicago      # Central Time
TZ=America/New_York     # Eastern Time
TZ=America/Los_Angeles  # Pacific Time
TZ=Europe/London        # UK
TZ=Europe/Paris         # Central Europe
TZ=Asia/Tokyo           # Japan
TZ=Australia/Sydney     # Australia
```

**Without `TZ`, times are in UTC!**

### Scheduler Logs
```
🕐 OCTOGEN SCHEDULER
══════════════════════════════════════════════════════════════════════
Schedule: 0 6 * * *
Timezone: America/Chicago
══════════════════════════════════════════════════════════════════════
📅 Next scheduled run: 2026-02-11 06:00:00
⏰ Next run in 3.5 hours (2026-02-11 06:00:00)
⏰ Next run in 30.2 minutes
⏰ Next run in 45 seconds
🚀 SCHEDULED RUN #1 - 2026-02-11 06:00:00
══════════════════════════════════════════════════════════════════════
[... OctoGen runs ...]
✅ Scheduled run #1 completed successfully
📅 Next scheduled run: 2026-02-12 06:00:00
```

---

## 📊 What You'll Get

### 11 Playlists Created:
1. **Discovery Weekly** (50 songs) - New discoveries
2. **Daily Mix 1** (30 songs) - Genre-based
3. **Daily Mix 2** (30 songs) - Genre-based
4. **Daily Mix 3** (30 songs) - Genre-based
5. **Daily Mix 4** (30 songs) - Genre-based
6. **Daily Mix 5** (30 songs) - Genre-based
7. **Daily Mix 6** (30 songs) - Genre-based
8. **Chill Vibes** (30 songs) - Relaxing
9. **Workout Energy** (30 songs) - High-energy
10. **Focus Flow** (30 songs) - Ambient/instrumental
11. **Drive Time** (30 songs) - Upbeat

**Total: 350+ songs automatically curated!**

### Daily Updates
With `SCHEDULE_CRON` set, playlists refresh automatically:
- New songs discovered
- Rotates recommendations for variety
- Uses daily cache for efficiency
- Excludes low-rated songs (1-2 stars)

---

## 🛠️ Troubleshooting

### Problem: Can't pull image
```bash
# Make sure Docker is running
docker ps

# Try explicit pull
docker pull blueion76/octogen:latest
```

### Problem: Connection to Navidrome fails
```bash
# If in same Docker network, use service name:
NAVIDROME_URL=http://navidrome:4533

# If on host machine, use host.docker.internal:
NAVIDROME_URL=http://host.docker.internal:4533
```

### Problem: AI API errors
```bash
# Verify your API key is correct
# Check you have quota/credits remaining
# Try a different AI provider (see examples above)
```

### Problem: No playlists created
```bash
# Check logs for errors
docker logs octogen

# Make sure you have starred songs in Navidrome
# Verify Octo-Fiesta is running and accessible
```

### Problem: Scheduler not working
```bash
# Check croniter is installed (should be in Docker image)
pip install croniter

# Verify SCHEDULE_CRON format
# Use https://crontab.guru to test expressions

# Check logs for scheduler output
docker logs -f octogen

# Make sure container has restart policy
docker update --restart unless-stopped octogen
```

### Problem: Wrong timezone
```bash
# Set TZ environment variable
TZ=America/Chicago

# List available timezones
timedatectl list-timezones

# Verify in logs
docker logs octogen | grep "Timezone:"
```

---

## 📖 More Information

- **All variables**: See [ENV_VARS.md](ENV_VARS.md)
- **Full docs**: See [README.md](README.md)
- **Cron expressions**: https://crontab.guru

---

## 🔗 Quick Links

- **Docker Hub**: https://hub.docker.com/r/blueion76/octogen
- **GitHub**: https://github.com/Blueion76/Octogen
- **Issues**: https://github.com/Blueion76/Octogen/issues

---

**That's it! You're running OctoGen now.** 🎉
