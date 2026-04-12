"""LCD display manager for rendering and updating Jinja2 template lines."""

import logging
from typing import Dict, Any, Optional, Set, List
from jinja2 import Environment, Template, meta
from config import Config

try:
    from RPLCD.i2c import CharLCD
    LCD_AVAILABLE = True
except (ImportError, RuntimeError):
    LCD_AVAILABLE = False
    print("WARNING: RPLCD not available. LCD display will not be updated.")


# Configure logging
logger = logging.getLogger(__name__)


class LCDDisplay:
    """Manages LCD display by rendering Jinja2 templates."""
    
    def __init__(self, config: Config):
        """Initialize LCD display manager.
        
        Args:
            config: Configuration object containing LCD settings
        """
        self.config = config
        self.lcd_config = config.lcd_config
        
        # Get LCD lines from config
        self.lcd_lines = self.lcd_config.get('lines', [])
        
        # Store current rendered values
        self.current_values: Dict[int, str] = {}
        
        # Compile templates for each line
        self.templates: Dict[int, Template] = {}
        
        # Track dependencies: which variables each line depends on
        self.dependencies: Dict[int, Set[str]] = {}
        
        # Reverse mapping: which lines depend on each variable
        self.variable_to_lines: Dict[str, Set[int]] = {}
        
        # Jinja2 environment
        self.jinja_env = Environment()
        
        # LCD device
        self.lcd = None
        
        # Initialize LCD if available
        if LCD_AVAILABLE:
            self._initialize_lcd()
        
        # Compile templates
        for line_idx, template_str in enumerate(self.lcd_lines):
            print(f"DEBUG: LCD line {line_idx}: {template_str}")
            
            try:
                template = self.jinja_env.from_string(template_str)
                self.templates[line_idx] = template
                
                # Extract variables used in template
                ast = self.jinja_env.parse(template_str)
                variables = meta.find_undeclared_variables(ast)
                print(f"DEBUG: LCD line {line_idx} depends on: {variables}")
                self.dependencies[line_idx] = variables
                
                # Build reverse mapping
                for var in variables:
                    if var not in self.variable_to_lines:
                        self.variable_to_lines[var] = set()
                    self.variable_to_lines[var].add(line_idx)
                
                dep_list = ', '.join(sorted(variables)) if variables else 'none'
                logger.info(f"LCD line {line_idx} depends on: {dep_list}")
                
            except Exception as e:
                logger.error(f"Failed to compile template for LCD line {line_idx}: {e}")
                print(f"DEBUG: Exception: {e}")
                import traceback
                traceback.print_exc()
                self.templates[line_idx] = self.jinja_env.from_string('')
                self.dependencies[line_idx] = set()
            
            # Initialize current value as empty
            self.current_values[line_idx] = ''
    
    def _initialize_lcd(self):
        """Initialize LCD display via I2C."""
        try:
            import time
            
            # Default I2C address for 16x2 LCD is 0x27
            i2c_address = self.lcd_config.get('i2c_address', 0x27)
            i2c_port = self.lcd_config.get('port', 1)
            
            logger.info(f"Initializing LCD at I2C address: 0x{i2c_address:02x} on port {i2c_port}")
            print(f"Initializing LCD at I2C address: 0x{i2c_address:02x} on port {i2c_port}")
            
            # Give I2C device time to initialize
            time.sleep(0.5)
            
            self.lcd = CharLCD(
                i2c_expander="PCF8574",
                address=i2c_address,
                port=i2c_port,
                cols=16,
                rows=2,
                dotsize=8
            )
            
            # Give LCD time to initialize
            time.sleep(0.5)
            
            # Clear display and write test message
            self.lcd.clear()
            self.lcd.cursor_pos = (0, 0)
            self.lcd.write_string("RPi MQTT Relay")
            self.lcd.cursor_pos = (1, 0)
            self.lcd.write_string("Initializing...")
            
            logger.info("LCD initialized successfully")
            print("✓ LCD initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize LCD: {e}")
            print(f"✗ ERROR: Failed to initialize LCD at 0x{i2c_address:02x}: {e}")
            print("  Check: 1) Is I2C enabled? 2) Is LCD connected? 3) Is address correct?")
            import traceback
            traceback.print_exc()
            self.lcd = None
    
    def update(self, values: Dict[str, Any], changed_variable: Optional[str] = None) -> bool:
        """Update LCD display based on current values.
        
        Only updates lines that depend on the changed variable (if specified).
        If changed_variable is None, updates all lines.
        
        Args:
            values: Dictionary of variable names to current values
            changed_variable: Optional name of the variable that changed
            
        Returns:
            True if display was updated, False otherwise
        """
        # Debug: print LCD availability status
        if not LCD_AVAILABLE:
            print("DEBUG LCD: RPLCD not available")
            return False
        
        if not self.lcd:
            print("DEBUG LCD: self.lcd is None")
            return False
        
        updated = False
        
        # Determine which lines to update
        if changed_variable and changed_variable in self.variable_to_lines:
            lines_to_update = self.variable_to_lines[changed_variable]
            logger.debug(f"Variable '{changed_variable}' changed, updating LCD lines: {lines_to_update}")
            print(f"DEBUG LCD: Variable '{changed_variable}' changed, updating lines: {lines_to_update}")
        else:
            # Update all lines (e.g., on startup or when variable is None)
            lines_to_update = self.templates.keys()
            print(f"DEBUG LCD: Updating all {len(list(lines_to_update))} lines (changed_variable={changed_variable})")
        
        for line_idx in lines_to_update:
            template = self.templates[line_idx]
            old_value = self.current_values.get(line_idx, '')
            
            try:
                # Render template with current values
                new_value = template.render(**values)
                
                # Truncate to 16 characters for 16x2 display
                new_value = new_value[:16]
                print(f"DEBUG LCD: Line {line_idx} rendered: '{new_value}' (was: '{old_value}')")
            except Exception as e:
                logger.error(f"Error rendering LCD line {line_idx}: {e}")
                print(f"DEBUG LCD: Error rendering line {line_idx}: {e}")
                new_value = 'ERROR'
            
            # Check if value changed
            if old_value != new_value:
                self.current_values[line_idx] = new_value
                print(f"DEBUG LCD: Writing line {line_idx}: '{new_value}'")
                self._write_line(line_idx, new_value)
                updated = True
            else:
                print(f"DEBUG LCD: Line {line_idx} unchanged, skipping write")
        
        print(f"DEBUG LCD: Update complete, {updated}")
        return updated
    
    def _write_line(self, line_idx: int, text: str):
        """Write text to a specific LCD line.
        
        Args:
            line_idx: Line number (0 or 1)
            text: Text to display (will be truncated to 16 chars)
        """
        if not self.lcd:
            print(f"DEBUG LCD: _write_line called but self.lcd is None")
            return
        
        try:
            text = text[:16].ljust(16)  # Pad to 16 characters
            self.lcd.cursor_pos = (line_idx, 0)
            self.lcd.write_string(text)
            print(f"✓ LCD line {line_idx}: '{text}'")
            logger.debug(f"LCD line {line_idx}: {text}")
        except Exception as e:
            print(f"✗ ERROR writing to LCD line {line_idx}: {e}")
            logger.error(f"Error writing to LCD line {line_idx}: {e}")
    
    def get_dependencies(self, line_idx: int) -> Set[str]:
        """Get the variables that an LCD line depends on.
        
        Args:
            line_idx: Line number
            
        Returns:
            Set of variable names the line depends on
        """
        return self.dependencies.get(line_idx, set()).copy()
    
    def get_dependent_lines(self, variable: str) -> Set[int]:
        """Get the LCD lines that depend on a specific variable.
        
        Args:
            variable: Variable name
            
        Returns:
            Set of line indices that depend on this variable
        """
        return self.variable_to_lines.get(variable, set()).copy()
    
    def get_current_lines(self) -> list:
        """Return the current rendered values for all LCD lines as a list."""
        # Return the lines in order
        return [self.current_values.get(idx, '') for idx in range(len(self.lcd_lines))]
    
    def cleanup(self):
        """Clean up LCD resources."""
        if self.lcd:
            try:
                logger.info("Cleaning up LCD display")
                print("Cleaning up LCD display...")
                self.lcd.clear()
                self.lcd.close()
            except Exception as e:
                logger.error(f"Error cleaning up LCD: {e}")
