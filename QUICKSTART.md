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
OCTOFIESTA_URL=http://192.168.1.100:5274
AI_API_KEY=your_gemini_api_key

# Optional
AI_MODEL=gemini-2.5-flash
AI_BACKEND=gemini
LOG_LEVEL=INFO
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
  blueion76/octogen:latest
```

### 4. Check Logs
```bash
docker logs -f octogen
```

### 5. Check Navidrome
Open your Navidrome web interface and look for 11 new playlists! 🎉

**Done!** Your playlists are ready.

---

## 🐳 With Docker Compose (Recommended)

### 1. Create docker-compose.yml
```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  octogen:
    image: blueion76/octogen:latest
    container_name: octogen
    volumes:
      - octogen-data:/data
    env_file:
      - .env
    restart: unless-stopped

volumes:
  octogen-data:
EOF
```

### 2. Create .env
```bash
cat > .env << 'EOF'
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=your_password
OCTOFIESTA_URL=http://192.168.1.100:5274
AI_API_KEY=your_gemini_api_key
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

### Minimal (Required Only)
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

# Groq AI
AI_BACKEND=openai
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
AI_API_KEY=gsk_abc123...
```

### With Ollama (Local, Offline)
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:5274

# Ollama (local)
AI_BACKEND=openai
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama
```

### With Last.fm Integration
```bash
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=secret123
OCTOFIESTA_URL=http://192.168.1.100:5274
AI_API_KEY=AIzaSyABC123...

# Last.fm
LASTFM_ENABLED=true
LASTFM_API_KEY=your_lastfm_key
LASTFM_USERNAME=your_lastfm_username
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

---

## 🔄 Run Daily

### Option 1: Manual
```bash
docker start octogen
```

### Option 2: Cron (Automatic at 6 AM)
```bash
crontab -e

# Add line:
0 6 * * * docker start octogen
```

### Option 3: Docker Compose Loop
```yaml
services:
  octogen:
    image: blueion76/octogen:latest
    command: |
      sh -c "while true; do
        python octogen.py
        sleep 86400
      done"
```

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

---

## 📖 More Information

- **Complete setup**: See [GITHUB_WEB_UI_SETUP.md](GITHUB_WEB_UI_SETUP.md)
- **All variables**: See [ENV_VARS.md](ENV_VARS.md)
- **Full docs**: See [README.md](README.md)

---

## 🔗 Quick Links

- **Docker Hub**: https://hub.docker.com/r/blueion76/octogen
- **GitHub**: https://github.com/Blueion76/Octogen
- **Issues**: https://github.com/Blueion76/Octogen/issues

---

**That's it! You're running OctoGen.** 🎉
