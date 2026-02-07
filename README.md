# Spotify Clone - Automated Music Discovery Engine

An AI-powered music discovery system that generates personalized playlists by analyzing your Navidrome music library and leveraging AI recommendations (OpenAI/Gemini), Last.fm, and ListenBrainz. Please note I used Claude Code to generate this script. Any pull requests are welcome.

## Features

- **AI-Powered Recommendations**: Uses Gemini or OpenAI endpoints to generate 11 unique playlists based on your listening preferences
- **Star Rating Integration**: Automatically excludes songs rated 1-2 stars from recommendations
- **Smart Caching**: Daily cache invalidation with SQLite database for ratings
- **Automatic Music Discovery**: Integrates with octo-fiesta to download recommended tracks
- **Multi-Source Recommendations**: Optional Last.fm and ListenBrainz integration
- **Duplicate Prevention**: Tracks processed songs to avoid redundant downloads
- **Async Processing**: Parallel album scanning for improved performance
- **Dry Run Mode**: Test without making actual downloads or playlist changes
- **Instance Locking**: Prevents multiple simultaneous runs

## Prerequisites

### Required Services
- [**Navidrome**](https://www.navidrome.org/): Self-hosted music server with Subsonic API support
- [**octo-fiesta**](https://github.com/V1ck3s/octo-fiesta): Music download service with Subsonic API endpoints
- **LLM API Key**: Either Google Gemini API or OpenAI-compatible endpoint

### Optional Services
- **Last.fm API**: For additional recommendations (requires API key)
- **ListenBrainz**: For collaborative filtering recommendations

## Installation

### 1. Clone the Repository

git clone https://github.com/Blueion76/octofiesta-playlist-generator-llm
cd spotify-clone

### 2. Install Python Dependencies

pip install openai requests aiohttp

For Gemini SDK support (recommended):

pip install google-genai

### 3. Configure the Application

Create a `config.json` file in the same directory as `spotify_clone.py`:
```
{
  "navidrome": {
    "url": "http://your-navidrome-server:4533",
    "username": "your_username",
    "password": "your_password"
  },
  "octofiestarr": {
    "url": "http://your-octofiesta-server:port"
  },  
  "ai": {
    "api_key": "your_api_key",
    "model": "gemini-2.0-flash-thinking-exp-01-21",
    "backend": "gemini",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "max_context_songs": 500,
    "max_output_tokens": 65535
  },
  "performance": {
    "album_batch_size": 500,
    "max_albums_scan": 10000,
    "scan_timeout": 30,
    "download_delay_seconds": 6,
    "post_scan_delay_seconds": 2
  },
  "lastfm": {
    "enabled": false,
    "api_key": "your_lastfm_key",
    "username": "your_lastfm_username"
  },
  "listenbrainz": {
    "enabled": false,
    "username": "your_listenbrainz_username",
    "token": "your_listenbrainz_token"
  }
}
```
## Configuration Guide

### AI Backend Options

#### Option 1: Google Gemini (Recommended)
```
"ai": {
  "api_key": "YOUR_GEMINI_API_KEY",
  "model": "gemini-2.0-flash-thinking-exp-01-21",
  "backend": "gemini",
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"
}
```
Get your API key: https://aistudio.google.com/apikey

#### Option 2: OpenAI or Compatible Endpoint
```
"ai": {
  "api_key": "YOUR_OPENAI_API_KEY",
  "model": "gpt-4",
  "backend": "openai",
  "base_url": null
}
```
For custom endpoints (e.g., local LLMs):

```"base_url": "http://localhost:1234/v1/"```

### Performance Tuning

- `album_batch_size`: Number of albums to fetch per API call (default: 500)
- `max_albums_scan`: Maximum albums to scan during rating collection (default: 10000)
- `download_delay_seconds`: Wait time after triggering download (default: 6)
- `post_scan_delay_seconds`: Wait time after library scan (default: 2)
- `max_context_songs`: Number of favorited songs sent to AI for context (default: 500)

### Optional Service Setup

#### Last.fm
1. Create API account: https://www.last.fm/api/account/create
2. Enable in config and add your API key and username

#### ListenBrainz
1. Create account: https://listenbrainz.org
2. Generate user token in settings
3. Enable in config and add username/token

## Usage

### Basic Run

```python3 spotify_clone.py```

### Dry Run Mode (No Downloads/Changes)

```python3 spotify_clone.py --dry-run```

## Generated Playlists

The engine creates 11 personalized playlists:

1. **Discovery Weekly**: 50 songs (45 new discoveries + 5 from library)
2. **Daily Mix 1-6**: 30 songs each based on your top genres (25 library + 5 new)
3. **Chill Vibes**: 30 relaxing songs
4. **Workout Energy**: 30 high-energy songs
5. **Focus Flow**: 30 ambient/instrumental songs
6. **Drive Time**: 30 upbeat songs

## How It Works

1. **Library Analysis**: Scans your Navidrome library for starred songs and ratings
2. **Profile Building**: Extracts top artists and genres from your favorites
3. **AI Generation**: Uses AI to generate personalized playlists while excluding low-rated songs
4. **Smart Matching**: Searches library first before triggering downloads
5. **Automated Downloads**: Uses octo-fiesta to fetch missing tracks
6. **Playlist Creation**: Creates/updates playlists in Navidrome

## File Structure

- `spotify_clone.py` - Main application script
- `config.json` - Configuration file
- `discovery_engine.log` - Application logs
- `ratings_cache.db` - SQLite database for rating cache
- `gemini_cache.json` - Gemini API cache metadata
- `discovery_engine.lock` - Instance lock file

## Troubleshooting

### "Another instance is already running"
The lock file prevents multiple simultaneous runs. If crashed, remove `discovery_engine.lock`:

```rm discovery_engine.lock```

### "ERROR: pip install openai requests aiohttp"
Install missing dependencies:

```pip install openai requests aiohttp google-genai```

### Gemini "cache invalid" messages
Cache is automatically regenerated daily. This is normal behavior.

### Songs not downloading
- Verify octo-fiesta is running and accessible
- Check `download_delay_seconds` - increase if downloads timing out
- Review logs in `discovery_engine.log`

### API Rate Limiting
Adjust `max_output_tokens` in config or reduce `max_context_songs` to lower token usage.

## Advanced Features

### Rating System
- Songs rated 1-2 stars are automatically excluded from recommendations
- Rating cache refreshes daily to track new ratings
- Clear cache manually: Delete `ratings_cache.db`

### Cache Management
- Gemini cache expires after 24 hours
- Ratings cache refreshes daily at first run
- Clear Gemini cache: Delete `gemini_cache.json`

## Logs

View real-time logs:

```tail -f discovery_engine.log```

## Performance

- **First Run**: 10-20 seconds for Gemini cache creation
- **Subsequent Runs**: ~3-5 seconds with cache
- **Library Scan**: Depends on library size (async parallel processing)

## Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## Credits

- Integrates with [Navidrome](https://www.navidrome.org/)
- Powered by Google Gemini / OpenAI
- Uses Subsonic API protocol
- [Octo Fiesta](https://github.com/V1ck3s/octo-fiesta)
