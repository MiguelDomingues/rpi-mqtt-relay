"""GPIO output manager for controlling relays based on templates."""

import logging
import threading
from typing import Dict, Any, Optional, Set
from jinja2 import Environment, Template, meta
from config import Config

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("WARNING: RPi.GPIO not available. GPIO pins will not be controlled.")


# Configure logging
logger = logging.getLogger(__name__)


class GPIOOutputs:
    """Manages GPIO outputs by evaluating Jinja2 templates."""
    
    def __init__(self, config: Config):
        """Initialize GPIO outputs manager.
        
        Args:
            config: Configuration object containing GPIO output settings
        """
        self.config = config
        self.gpio_outputs = config.gpio_outputs
        
        # Store current states (True = ON, False = OFF)
        self.states: Dict[str, bool] = {}
        
        # Track pending state changes (timers)
        self.pending_timers: Dict[str, Optional[threading.Timer]] = {}
        
        # Track target states (what we're planning to change to after delay)
        self.target_states: Dict[str, Optional[bool]] = {}
        
        # Compile templates for each output
        self.templates: Dict[str, Template] = {}
        self.output_configs: Dict[str, Dict[str, Any]] = {}
        
        # Track dependencies: which variables each output depends on
        self.dependencies: Dict[str, Set[str]] = {}
        
        # Reverse mapping: which outputs depend on each variable
        self.variable_to_outputs: Dict[str, Set[str]] = {}
        
        # Jinja2 environment
        self.jinja_env = Environment()
        
        # Callback for when a GPIO state change completes (called from _apply_state_change)
        self.on_state_change = None  # Will be set to callback(output_id: str, new_state: bool)
        
        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            # Use BCM pin numbering
            GPIO.setmode(GPIO.BCM)
            # Disable warnings about pins already in use
            GPIO.setwarnings(False)
            logger.info("GPIO initialized with BCM pin numbering")
            print("GPIO initialized with BCM pin numbering")
        
        # Initialize outputs
        for output_config in self.gpio_outputs:
            output_id = output_config['id']
            print(f"DEBUG: Raw output_config for '{output_id}': {output_config}")
            # Note: YAML parses 'on' as boolean True, so check for both
            template_str = output_config.get(True, output_config.get('on', 'False'))
            print(f"DEBUG: Template string extracted: '{template_str}'")
            
            # Store output config
            self.output_configs[output_id] = output_config
            
            # Compile template and extract dependencies
            try:
                print(f"DEBUG: Processing output '{output_id}' with template: {template_str}")
                template = self.jinja_env.from_string(template_str)
                self.templates[output_id] = template
                
                # Extract variables used in template
                ast = self.jinja_env.parse(template_str)
                variables = meta.find_undeclared_variables(ast)
                print(f"DEBUG: Extracted variables: {variables}")
                self.dependencies[output_id] = variables
                
                # Build reverse mapping
                for var in variables:
                    print(f"DEBUG: Adding mapping '{var}' -> '{output_id}'")
                    if var not in self.variable_to_outputs:
                        self.variable_to_outputs[var] = set()
                    self.variable_to_outputs[var].add(output_id)
                
                dep_list = ', '.join(sorted(variables)) if variables else 'none'
                logger.info(f"Output '{output_id}' depends on: {dep_list}")
                logger.info(f"  Template: {template_str}")
                print(f"DEBUG: variable_to_outputs now contains: {self.variable_to_outputs}")
                
            except Exception as e:
                logger.error(f"Failed to compile template for '{output_id}': {e}")
                print(f"DEBUG: Exception occurred: {e}")
                import traceback
                traceback.print_exc()
                self.templates[output_id] = self.jinja_env.from_string('False')
                self.dependencies[output_id] = set()
            
            # Setup GPIO pin if available
            if GPIO_AVAILABLE:
                pin = output_config.get('pin')
                if pin:
                    GPIO.setup(pin, GPIO.OUT)
                    # Initialize to HIGH (OFF)
                    GPIO.output(pin, GPIO.HIGH)
                    logger.info(f"GPIO Pin {pin} initialized for '{output_id}'")
                    print(f"GPIO Pin {pin} initialized for '{output_id}'")
            
            # Initialize state as None (unknown)
            self.states[output_id] = None
    
    def update(self, values: Dict[str, Any], changed_variable: Optional[str] = None) -> Dict[str, bool]:
        """Update GPIO outputs based on current input values.
        
        Only updates outputs that depend on the changed variable (if specified).
        If changed_variable is None, updates all outputs.
        
        Args:
            values: Dictionary of input IDs to current values
            changed_variable: Optional ID of the variable that changed
            
        Returns:
            Dictionary of output IDs to their new states
        """
        changes = {}
        
        logger.debug(f"update() called with changed_variable='{changed_variable}'")
        
        # Determine which outputs to update
        if changed_variable and changed_variable in self.variable_to_outputs:
            outputs_to_update = self.variable_to_outputs[changed_variable]
            logger.info(f"Variable '{changed_variable}' changed, updating {len(outputs_to_update)} dependent output(s)")
            print(f"  -> Evaluating outputs dependent on '{changed_variable}': {', '.join(outputs_to_update)}")
        else:
            # Update all outputs (e.g., on startup or when variable is None)
            outputs_to_update = self.templates.keys()
            if changed_variable:
                logger.warning(f"Variable '{changed_variable}' has no dependent outputs")
                print(f"  -> No outputs depend on '{changed_variable}'")
        
        for output_id in outputs_to_update:
            template = self.templates[output_id]
            current_state = self.states.get(output_id)
            
            try:
                # Render template with current values
                result = template.render(**values)
                
                # Convert result to boolean
                # Jinja2 might return 'True'/'False' strings or actual booleans
                if isinstance(result, str):
                    desired_state = result.strip().lower() in ('true', '1', 'yes', 'on')
                else:
                    desired_state = bool(result)
                
            except Exception as e:
                logger.error(f"Error evaluating template for '{output_id}': {e}")
                desired_state = False  # Default to OFF on error
            
            # Check if desired state is different from current state
            if current_state != desired_state:
                self._handle_state_change(output_id, desired_state, changes)
            else:
                # Desired state same as current state
                # If there's a pending timer, cancel it since we're staying in current state
                if output_id in self.pending_timers and self.pending_timers[output_id]:
                    logger.info(f"[{output_id}] Desired state reverted, canceling pending change")
                    print(f"[{self.output_configs[output_id]['name']}] Canceling pending state change")
                    self.pending_timers[output_id].cancel()
                    self.pending_timers[output_id] = None
                    self.target_states[output_id] = None
        
        return changes
    
    def _handle_state_change(self, output_id: str, desired_state: bool, changes: Dict[str, bool]):
        """Handle a state change with optional delay.
        
        Args:
            output_id: Output identifier
            desired_state: The desired new state
            changes: Dictionary to track changes
        """
        output_config = self.output_configs[output_id]
        current_state = self.states.get(output_id)
        
        # Check if we're already planning to change to this state
        if self.target_states.get(output_id) == desired_state:
            # Already have a pending change to this state, do nothing
            return
        
        # Cancel any existing pending timer
        if output_id in self.pending_timers and self.pending_timers[output_id]:
            self.pending_timers[output_id].cancel()
            self.pending_timers[output_id] = None
        
        # Get delay configuration
        delay_config = output_config.get('delay', {})
        output_name = output_config['name']
        
        print(f"DEBUG: [{output_name}] delay_config: {delay_config}, current: {current_state}, desired: {desired_state}")
        
        # Determine which delay to use
        if current_state is None:
            # Initial state (None -> something) - apply immediately
            delay_seconds = 0
            transition = f"Initial → {'ON' if desired_state else 'OFF'}"
        elif desired_state and not current_state:
            # OFF -> ON transition (current_state is False)
            # YAML parses 'on' as True, so check for both
            delay_seconds = delay_config.get(True, delay_config.get('on', 0))
            transition = "OFF → ON"
        elif not desired_state and current_state:
            # ON -> OFF transition (current_state is True)
            # YAML parses 'off' as False, so check for both
            delay_seconds = delay_config.get(False, delay_config.get('off', 0))
            transition = "ON → OFF"
        else:
            # Shouldn't reach here, but default to no delay
            delay_seconds = 0
            transition = f"{'ON' if desired_state else 'OFF'} (no change)"
        
        print(f"DEBUG: [{output_name}] delay_seconds: {delay_seconds}, transition: {transition}")
        
        if delay_seconds > 0:
            # Schedule delayed change
            print(f"DEBUG: [{output_name}] Scheduling timer for {delay_seconds}s")
            logger.info(f"[{output_name}] {transition} change scheduled in {delay_seconds} seconds")
            print(f"[{output_name}] {transition} change scheduled in {delay_seconds}s")
            
            self.target_states[output_id] = desired_state
            timer = threading.Timer(delay_seconds, self._apply_state_change, args=(output_id, desired_state, changes))
            self.pending_timers[output_id] = timer
            timer.start()
        else:
            # Apply change immediately (no delay or initial state)
            print(f"DEBUG: [{output_name}] Applying change immediately (delay={delay_seconds})")
            self._apply_state_change(output_id, desired_state, changes)
    
    def _apply_state_change(self, output_id: str, new_state: bool, changes: Dict[str, bool]):
        """Apply the actual state change to GPIO pin.
        
        Args:
            output_id: Output identifier
            new_state: The new state to apply
            changes: Dictionary to track changes
        """
        old_state = self.states.get(output_id)
        
        # Update state
        self.states[output_id] = new_state
        
        # Clear pending timer and target state
        self.pending_timers[output_id] = None
        self.target_states[output_id] = None
        
        # Track change
        if old_state != new_state:
            changes[output_id] = new_state
            self._print_state_change(output_id, old_state, new_state)
            
            # Call state change callback if set
            if self.on_state_change:
                try:
                    self.on_state_change(output_id, new_state)
                except Exception as e:
                    logger.error(f"Error in on_state_change callback for '{output_id}': {e}")
        else:
            # State didn't actually change (shouldn't happen, but log it)
            state_str = "ON" if new_state else "OFF"
            logger.debug(f"[{output_id}] State unchanged: {state_str}")
    
    def _print_state_change(self, output_id: str, old_state: Optional[bool], new_state: bool):
        """Print state change to console and update GPIO pin.
        
        Args:
            output_id: Output identifier
            old_state: Previous state (None if first update)
            new_state: New state
        """
        output_config = self.output_configs[output_id]
        output_name = output_config['name']
        pin = output_config['pin']
        
        state_str = "ON" if new_state else "OFF"
        
        # Update GPIO pin if available
        if GPIO_AVAILABLE and pin:
            gpio_state = GPIO.LOW if new_state else GPIO.HIGH
            GPIO.output(pin, gpio_state)
            logger.debug(f"GPIO Pin {pin} set to {gpio_state}")
        
        if old_state is None:
            logger.info(f"[{output_name}] Initial state: {state_str} (Pin {pin})")
            print(f"[{output_name}] Initial state: {state_str} (Pin {pin})")
        else:
            old_state_str = "ON" if old_state else "OFF"
            logger.info(f"[{output_name}] Changed: {old_state_str} → {state_str} (Pin {pin})")
            print(f"[{output_name}] Changed: {old_state_str} → {state_str} (Pin {pin})")
    
    def get_state(self, output_id: str) -> Optional[bool]:
        """Get current state for an output.
        
        Args:
            output_id: ID of the output
            
        Returns:
            Current state (True/False) or None if not set
        """
        return self.states.get(output_id)
    
    def get_all_states(self) -> Dict[str, bool]:
        """Get all current output states.
        
        Returns:
            Dictionary of output IDs to current states
        """
        return self.states.copy()
    
    def get_dependencies(self, output_id: str) -> Set[str]:
        """Get the variables that an output depends on.
        
        Args:
            output_id: ID of the output
            
        Returns:
            Set of variable names the output depends on
        """
        return self.dependencies.get(output_id, set()).copy()
    
    def get_dependent_outputs(self, variable: str) -> Set[str]:
        """Get the outputs that depend on a specific variable.
        
        Args:
            variable: Variable/input ID
            
        Returns:
            Set of output IDs that depend on this variable
        """
        return self.variable_to_outputs.get(variable, set()).copy()
    
    def get_output_info(self, output_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration info for an output.
        
        Args:
            output_id: ID of the output
            
        Returns:
            Output configuration dictionary or None
        """
        return self.output_configs.get(output_id)
    
    def cleanup(self):
        """Clean up GPIO resources by turning off all outputs."""
        logger.info("Shutting down GPIO outputs")
        print("\nShutting down GPIO outputs...")
        
        # Cancel all pending timers first
        for output_id, timer in self.pending_timers.items():
            if timer:
                output_name = self.output_configs[output_id]['name']
                logger.info(f"Canceling pending timer for {output_name}")
                print(f"  - Canceling pending change for {output_name}")
                timer.cancel()
        
        # Clear pending timers and target states
        self.pending_timers.clear()
        self.target_states.clear()
        
        if GPIO_AVAILABLE:
            # Turn off all GPIO pins
            for output_id, output_config in self.output_configs.items():
                pin = output_config.get('pin')
                output_name = output_config['name']
                
                if pin:
                    try:
                        GPIO.output(pin, GPIO.HIGH)
                        self.states[output_id] = False
                        logger.info(f"GPIO Pin {pin} ({output_name}) set to OFF")
                        print(f"  - Pin {pin} ({output_name}): OFF")
                    except Exception as e:
                        logger.error(f"Error setting Pin {pin} to OFF: {e}")
            
            # Clean up GPIO resources
            logger.info("Cleaning up GPIO resources")
            print("Cleaning up GPIO resources...")
            GPIO.cleanup()

