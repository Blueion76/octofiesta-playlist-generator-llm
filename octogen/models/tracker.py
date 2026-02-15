"""Run tracking models with time-period awareness"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RunTracker:
    """Track OctoGen runs with service status and time-period awareness."""
    
    def __init__(self, data_dir: Path):
        """Initialize run tracker.
        
        Args:
            data_dir: Data directory for tracker file
        """
        self.data_dir = data_dir
        self.tracker_file = data_dir / "octogen_last_run.json"
        self.services: Dict[str, Dict[str, Any]] = {}
    
    def record_service(self, service_name: str, success: bool, **kwargs) -> None:
        """Record a service execution.
        
        Args:
            service_name: Name of the service
            success: Whether the service succeeded
            **kwargs: Additional service metadata (e.g., playlists, reason)
        """
        self.services[service_name] = {
            "success": success,
            **kwargs
        }
    
    def save(self, next_scheduled_run: Optional[str] = None, time_period: Optional[str] = None) -> None:
        """Save run tracking data.
        
        Args:
            next_scheduled_run: Next scheduled run time (ISO format)
            time_period: Current time period (morning/afternoon/evening/night)
        """
        try:
            now = datetime.now(timezone.utc)
            
            data = {
                "last_run_timestamp": now.isoformat(),
                "last_run_date": now.strftime("%Y-%m-%d"),
                "services": self.services,
            }
            
            if next_scheduled_run:
                data["next_scheduled_run"] = next_scheduled_run
            
            if time_period:
                data["last_time_period"] = time_period
            
            with open(self.tracker_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.info("✓ Run tracking data saved")
            
        except Exception as e:
            logger.error(f"Error saving run tracking data: {e}")
    
    def load(self) -> Optional[Dict[str, Any]]:
        """Load run tracking data.
        
        Returns:
            Tracking data dict or None if not found
        """
        try:
            if not self.tracker_file.exists():
                return None
            
            with open(self.tracker_file, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Error loading run tracking data: {e}")
            return None
    
    def get_last_time_period(self) -> Optional[str]:
        """Get the time period from last run.
        
        Returns:
            Last time period or None
        """
        data = self.load()
        if data:
            return data.get("last_time_period")
        return None


class ServiceTracker:
    """Track individual service executions for a single run."""
    
    def __init__(self):
        """Initialize service tracker."""
        self.services: Dict[str, Dict[str, Any]] = {}
    
    def record(self, service_name: str, success: bool, **kwargs) -> None:
        """Record a service execution.
        
        Args:
            service_name: Name of the service
            success: Whether the service succeeded
            **kwargs: Additional metadata
        """
        self.services[service_name] = {
            "success": success,
            **kwargs
        }
        
        status = "✅" if success else "❌"
        logger.info(f"{status} Service: {service_name}")
        
        if not success and "reason" in kwargs:
            logger.info(f"   Reason: {kwargs['reason']}")
