"""MQTT output manager for publishing values based on templates."""

import logging
from typing import Dict, Any, Optional, Set
from jinja2 import Environment, Template, meta
from config import Config
import paho.mqtt.client as mqtt


# Configure logging
logger = logging.getLogger(__name__)


class MQTTOutputs:
    """Manages MQTT outputs by evaluating Jinja2 templates and publishing."""
    
    def __init__(self, config: Config, mqtt_client: mqtt.Client):
        """Initialize MQTT outputs manager.
        
        Args:
            config: Configuration object containing MQTT output settings
            mqtt_client: MQTT client instance to use for publishing
        """
        self.config = config
        self.mqtt_outputs = config.mqtt_outputs
        self.mqtt_client = mqtt_client
        
        # Store current values for each output
        self.values: Dict[str, str] = {}
        
        # Compile templates for each output
        self.templates: Dict[str, Template] = {}
        self.output_configs: Dict[str, Dict[str, Any]] = {}
        
        # Track dependencies: which variables each output depends on
        self.dependencies: Dict[str, Set[str]] = {}
        
        # Reverse mapping: which outputs depend on each variable
        self.variable_to_outputs: Dict[str, Set[str]] = {}
        
        # Jinja2 environment
        self.jinja_env = Environment()
        
        # Initialize outputs
        for idx, output_config in enumerate(self.mqtt_outputs):
            # Use topic as ID
            topic = output_config.get('topic')
            if not topic:
                logger.warning(f"MQTT output #{idx} missing 'topic', skipping")
                continue
            
            output_id = topic
            template_str = output_config.get('value', '')
            
            print(f"DEBUG: MQTT output topic: {topic}")
            print(f"DEBUG: Template string: '{template_str}'")
            
            # Store output config
            self.output_configs[output_id] = output_config
            
            # Compile template and extract dependencies
            try:
                template = self.jinja_env.from_string(template_str)
                self.templates[output_id] = template
                
                # Extract variables used in template
                ast = self.jinja_env.parse(template_str)
                variables = meta.find_undeclared_variables(ast)
                print(f"DEBUG: MQTT output '{topic}' depends on: {variables}")
                self.dependencies[output_id] = variables
                
                # Build reverse mapping
                for var in variables:
                    if var not in self.variable_to_outputs:
                        self.variable_to_outputs[var] = set()
                    self.variable_to_outputs[var].add(output_id)
                
                dep_list = ', '.join(sorted(variables)) if variables else 'none'
                logger.info(f"MQTT output '{topic}' depends on: {dep_list}")
                
            except Exception as e:
                logger.error(f"Failed to compile template for MQTT output '{topic}': {e}")
                print(f"DEBUG: Exception occurred: {e}")
                import traceback
                traceback.print_exc()
                self.templates[output_id] = self.jinja_env.from_string('')
                self.dependencies[output_id] = set()
            
            # Initialize value as None (unknown)
            self.values[output_id] = None
    
    def update(self, values: Dict[str, Any], changed_variable: Optional[str] = None) -> Dict[str, str]:
        """Update MQTT outputs based on current values.
        
        Only updates outputs that depend on the changed variable (if specified).
        If changed_variable is None, updates all outputs.
        
        Args:
            values: Dictionary of variable names to current values
            changed_variable: Optional name of the variable that changed
            
        Returns:
            Dictionary of output topics to their new values
        """
        changes = {}
        
        logger.debug(f"MQTT update() called with changed_variable='{changed_variable}'")
        
        # Determine which outputs to update
        if changed_variable and changed_variable in self.variable_to_outputs:
            outputs_to_update = self.variable_to_outputs[changed_variable]
            logger.info(f"Variable '{changed_variable}' changed, updating {len(outputs_to_update)} MQTT output(s)")
            print(f"  -> Publishing MQTT outputs dependent on '{changed_variable}'")
        else:
            # Update all outputs (e.g., on startup or when variable is None)
            outputs_to_update = self.templates.keys()
            if changed_variable:
                logger.debug(f"Variable '{changed_variable}' has no dependent MQTT outputs")
        
        for output_id in outputs_to_update:
            template = self.templates[output_id]
            old_value = self.values.get(output_id)
            
            try:
                # Render template with current values
                new_value = template.render(**values)
                
            except Exception as e:
                logger.error(f"Error evaluating template for MQTT output '{output_id}': {e}")
                new_value = ''  # Default to empty string on error
            
            # Update stored value
            self.values[output_id] = new_value
            
            # Check if value changed
            if old_value != new_value:
                changes[output_id] = new_value
                self._publish_value(output_id, old_value, new_value)
        
        return changes
    
    def _publish_value(self, topic: str, old_value: Optional[str], new_value: str):
        """Publish value to MQTT topic.
        
        Args:
            topic: MQTT topic to publish to
            old_value: Previous value (None if first update)
            new_value: New value to publish
        """
        # Publish to MQTT
        try:
            result = self.mqtt_client.publish(topic, new_value, qos=1, retain=True)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Published to {topic}: {new_value}")
            else:
                logger.warning(f"Failed to publish to {topic}, rc={result.rc}")
        except Exception as e:
            logger.error(f"Error publishing to {topic}: {e}")
        
        # Print to console
        if old_value is None:
            logger.info(f"[MQTT: {topic}] Initial value: {new_value}")
            print(f"[MQTT: {topic}] Initial value: {new_value}")
        else:
            logger.info(f"[MQTT: {topic}] Changed: {old_value} → {new_value}")
            print(f"[MQTT: {topic}] Changed: {old_value} → {new_value}")
    
    def get_value(self, topic: str) -> Optional[str]:
        """Get current value for an MQTT output.
        
        Args:
            topic: MQTT topic
            
        Returns:
            Current value or None if not set
        """
        return self.values.get(topic)
    
    def get_all_values(self) -> Dict[str, str]:
        """Get all current MQTT output values.
        
        Returns:
            Dictionary of topics to current values
        """
        return self.values.copy()
    
    def get_all_states(self) -> Dict[str, str]:
        """Return the current state of all MQTT outputs."""
        return dict(self.values)
    
    def get_dependencies(self, topic: str) -> Set[str]:
        """Get the variables that an MQTT output depends on.
        
        Args:
            topic: MQTT topic
            
        Returns:
            Set of variable names the output depends on
        """
        return self.dependencies.get(topic, set()).copy()
    
    def get_dependent_outputs(self, variable: str) -> Set[str]:
        """Get the MQTT outputs that depend on a specific variable.
        
        Args:
            variable: Variable name
            
        Returns:
            Set of topics that depend on this variable
        """
        return self.variable_to_outputs.get(variable, set()).copy()
    
    def shutdown(self, final_values: Dict[str, Any]):
        """Publish final MQTT output states with all GPIO outputs off.
        
        Args:
            final_values: Dictionary with all variables including GPIO states set to False
        """
        logger.info("Publishing final MQTT output states")
        print("\nPublishing final MQTT output states...")
        
        # Update all MQTT outputs with final values (GPIO outputs should be False)
        for output_id in self.templates.keys():
            template = self.templates[output_id]
            
            try:
                # Render template with final values
                final_value = template.render(**final_values)
                
                # Publish to MQTT
                result = self.mqtt_client.publish(output_id, final_value, qos=1, retain=True)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"  - {output_id}: {final_value}")
                    logger.info(f"Published final state to {output_id}: {final_value}")
                else:
                    logger.warning(f"Failed to publish final state to {output_id}, rc={result.rc}")
            except Exception as e:
                logger.error(f"Error publishing final state to {output_id}: {e}")
