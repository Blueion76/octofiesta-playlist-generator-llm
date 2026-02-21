"""Playlist template management"""

import logging
import os
import yaml
from pathlib import Path
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)


class PlaylistTemplate:
    """Represents a playlist template"""
    
    def __init__(self, name: str, song_count: int = 30, **kwargs):
        """Initialize playlist template.
        
        Args:
            name: Template name
            song_count: Number of songs
            **kwargs: Additional template parameters
        """
        self.name = name
        self.song_count = song_count
        self.characteristics = kwargs.get('characteristics', [])
        self.genres = kwargs.get('genres', [])
        self.mood_filters = kwargs.get('mood_filters', {})
        self.time_of_day = kwargs.get('time_of_day')
        
    def to_prompt(self) -> str:
        """Convert template to AI prompt string.
        
        Returns:
            Prompt string for AI generation
        """
        parts = [f"{self.name} ({self.song_count} songs)"]
        
        if self.characteristics:
            parts.append(f"characteristics: {', '.join(self.characteristics)}")
        if self.genres:
            parts.append(f"genres: {', '.join(self.genres)}")
        if self.mood_filters:
            filters = []
            for key, value in self.mood_filters.items():
                filters.append(f"{key}={value}")
            parts.append(f"filters: {', '.join(filters)}")
        if self.time_of_day:
            parts.append(f"time: {self.time_of_day}")
            
        return " - ".join(parts)


class PlaylistTemplateManager:
    """Manages playlist templates from YAML files"""
    
    def __init__(self, template_file: Optional[Path] = None):
        """Initialize template manager.
        
        Args:
            template_file: Optional path to template YAML file
        """
        self.templates: List[PlaylistTemplate] = []
        
        if template_file and template_file.exists():
            self.load_templates(template_file)
        else:
            logger.info("No template file specified, using default templates")
            self._load_default_templates()
    
    def _load_default_templates(self):
        """Load default playlist templates"""
        default_templates = [
            {
                'name': 'Morning Motivation',
                'song_count': 30,
                'characteristics': ['upbeat', 'energetic', 'positive'],
                'mood_filters': {'energy_min': 0.7, 'valence_min': 0.6},
                'time_of_day': 'morning'
            },
            {
                'name': 'Focus Deep Work',
                'song_count': 60,
                'characteristics': ['instrumental', 'ambient', 'minimal vocals'],
                'genres': ['ambient', 'classical', 'electronic'],
                'mood_filters': {'energy_max': 0.5, 'tempo_max': 120},
                'time_of_day': 'day'
            },
            {
                'name': 'Evening Wind Down',
                'song_count': 40,
                'characteristics': ['relaxing', 'calm', 'mellow'],
                'mood_filters': {'energy_max': 0.4, 'tempo_max': 100},
                'time_of_day': 'evening'
            },
            {
                'name': 'Workout Intensity',
                'song_count': 30,
                'characteristics': ['high-energy', 'intense', 'driving'],
                'mood_filters': {'energy_min': 0.8, 'tempo_min': 140}
            }
        ]
        
        for template_data in default_templates:
            self.templates.append(PlaylistTemplate(**template_data))
        
        logger.info(f"Loaded {len(self.templates)} default templates")
    
    def load_templates(self, template_file: Path):
        """Load templates from YAML file.
        
        Args:
            template_file: Path to YAML file
        """
        try:
            with open(template_file, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'templates' not in data:
                logger.warning("Invalid template file format, using defaults")
                self._load_default_templates()
                return
            
            self.templates = []
            for template_data in data['templates']:
                self.templates.append(PlaylistTemplate(**template_data))
            
            logger.info(f"Loaded {len(self.templates)} templates from {template_file}")
            
        except Exception as e:
            logger.error(f"Failed to load templates: {e}")
            logger.info("Using default templates instead")
            self._load_default_templates()
    
    def get_template(self, name: str) -> Optional[PlaylistTemplate]:
        """Get template by name.
        
        Args:
            name: Template name
            
        Returns:
            PlaylistTemplate or None
        """
        for template in self.templates:
            if template.name.lower() == name.lower():
                return template
        return None
    
    def get_all_templates(self) -> List[PlaylistTemplate]:
        """Get all templates.
        
        Returns:
            List of PlaylistTemplate objects
        """
        return self.templates


def load_templates(template_file: Optional[str] = None) -> PlaylistTemplateManager:
    """Load playlist templates from file or use defaults.
    
    Args:
        template_file: Optional path to template file
        
    Returns:
        PlaylistTemplateManager instance
    """
    if template_file:
        template_path = Path(template_file)
    else:
        # Check for default location
        template_path = Path(os.getenv('PLAYLIST_TEMPLATES_FILE', '/config/playlist_templates.yaml'))
    
    return PlaylistTemplateManager(template_path if template_path.exists() else None)
