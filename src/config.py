"""Configuration loader for RPi MQTT Relay."""

import yaml
from pathlib import Path
from typing import Any, Dict, List


class Config:
    """Load and manage configuration from YAML file."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize configuration from YAML file.
        
        Args:
            config_path: Path to the configuration YAML file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    @property
    def mqtt_broker(self) -> Dict[str, Any]:
        """Get MQTT broker configuration."""
        return self.config.get('mqtt', {})
    
    @property
    def mqtt_inputs(self) -> List[Dict[str, Any]]:
        """Get list of MQTT input configurations."""
        return self.config.get('inputs', {}).get('mqtt', [])
    
    @property
    def mqtt_outputs(self) -> List[Dict[str, Any]]:
        """Get list of MQTT output configurations."""
        return self.config.get('outputs', {}).get('mqtt', [])
    
    @property
    def gpio_outputs(self) -> List[Dict[str, Any]]:
        """Get list of GPIO output configurations."""
        return self.config.get('outputs', {}).get('gpio', [])
    
    @property
    def lcd_config(self) -> Dict[str, Any]:
        """Get LCD configuration."""
        return self.config.get('lcd', {})
