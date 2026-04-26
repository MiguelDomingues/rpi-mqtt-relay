"""Configuration loader for RPi MQTT Relay."""

import yaml
from pathlib import Path
from typing import Any, Dict, List
from jinja2 import Environment, meta, TemplateSyntaxError


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

        self._validate_jinja_templates()

    def _validate_jinja_templates(self) -> None:
        """Validate Jinja2 expressions in configuration.

        Raises:
            ValueError: If any template contains syntax errors or unknown variables.
        """
        env = Environment()
        errors: List[str] = []

        mqtt_inputs = self.config.get('inputs', {}).get('mqtt', []) or []
        gpio_outputs = self.config.get('outputs', {}).get('gpio', []) or []
        mqtt_outputs = self.config.get('outputs', {}).get('mqtt', []) or []
        lcd_lines = self.config.get('lcd', {}).get('lines', []) or []

        input_ids = {inp.get('id') for inp in mqtt_inputs if inp.get('id')}
        gpio_ids = {out.get('id') for out in gpio_outputs if out.get('id')}

        allowed_gpio_vars = input_ids | gpio_ids
        allowed_mqtt_vars = input_ids | gpio_ids | {'now'}
        allowed_lcd_vars = input_ids | gpio_ids

        def validate_template(template_str: str, location: str, allowed_vars: set) -> None:
            if not isinstance(template_str, str):
                errors.append(f"{location}: template must be a string")
                return

            try:
                ast = env.parse(template_str)
            except TemplateSyntaxError as exc:
                errors.append(f"{location}: syntax error (line {exc.lineno}): {exc.message}")
                return
            except Exception as exc:
                errors.append(f"{location}: parse error: {exc}")
                return

            variables = meta.find_undeclared_variables(ast)
            unknown_vars = sorted(var for var in variables if var not in allowed_vars)
            if unknown_vars:
                errors.append(
                    f"{location}: unknown variable(s): {', '.join(unknown_vars)}"
                )

        for idx, output in enumerate(gpio_outputs):
            output_id = output.get('id', f'index {idx}')
            template_str = output.get(True, output.get('on', 'False'))
            validate_template(
                template_str,
                f"outputs.gpio[{idx}] ({output_id}) 'on'",
                allowed_gpio_vars,
            )

        for idx, output in enumerate(mqtt_outputs):
            topic = output.get('topic', f'index {idx}')
            template_str = output.get('value', '')
            validate_template(
                template_str,
                f"outputs.mqtt[{idx}] ({topic}) 'value'",
                allowed_mqtt_vars,
            )

        for idx, line_template in enumerate(lcd_lines):
            validate_template(
                line_template,
                f"lcd.lines[{idx}]",
                allowed_lcd_vars,
            )

        if errors:
            error_block = "\n  - " + "\n  - ".join(errors)
            raise ValueError(f"Invalid Jinja2 expressions in {self.config_path}:{error_block}")
    
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
