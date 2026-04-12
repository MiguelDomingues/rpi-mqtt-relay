"""RPi MQTT Relay Controller - Main entry point."""

import sys
from config import Config
from mqtt import MQTTListener
from outputs import GPIOOutputs
from mqtt_outputs import MQTTOutputs
from lcd import LCDDisplay
from web_status import start_web_status_thread
import threading


def main():
    """Main entry point for the application."""
    print("=" * 60)
    print("Starting RPi MQTT Relay Controller...")
    print("=" * 60)
    
    try:
        # Load configuration
        print("\nLoading configuration from config.yaml...")
        config = Config("config.yaml")
        
        # Display loaded MQTT inputs
        print(f"\nFound {len(config.mqtt_inputs)} MQTT input(s):")
        for inp in config.mqtt_inputs:
            print(f"  - {inp['name']} ({inp['id']}): {inp['topic']}")
        
        # Display loaded GPIO outputs
        print(f"\nFound {len(config.gpio_outputs)} GPIO output(s):")
        for out in config.gpio_outputs:
            print(f"  - {out['name']} ({out['id']}): Pin {out['pin']}")
            print(f"    DEBUG: Full config: {out}")
        
        # Create LCD display manager first (shows initialization on screen)
        print("\nInitializing LCD display...")
        lcd_display = LCDDisplay(config)
        
        # Display LCD lines and their dependencies
        print(f"\nFound {len(config.lcd_config.get('lines', []))} LCD line(s):")
        for line_idx in range(len(config.lcd_config.get('lines', []))):
            deps = lcd_display.get_dependencies(line_idx)
            dep_str = ', '.join(sorted(deps)) if deps else 'none'
            print(f"  - Line {line_idx}: depends on {dep_str}")
        
        # Create GPIO outputs manager
        print("\nInitializing GPIO outputs manager...")
        gpio_outputs = GPIOOutputs(config)
        
        # Print dependencies
        print("\nOutput dependencies:")
        for out in config.gpio_outputs:
            output_id = out['id']
            deps = gpio_outputs.get_dependencies(output_id)
            dep_str = ', '.join(sorted(deps)) if deps else 'none'
            print(f"  - {out['name']}: {dep_str}")
        
        # Debug: Print reverse mapping
        print("\nVariable → Output mapping:")
        for var, outputs in gpio_outputs.variable_to_outputs.items():
            print(f"  - '{var}' triggers: {', '.join(outputs)}")
        
        # Create MQTT listener (without callback for now)
        print("\nInitializing MQTT listener...")
        listener = MQTTListener(config)
        
        # Create MQTT outputs manager
        print("\nInitializing MQTT outputs manager...")
        mqtt_outputs = MQTTOutputs(config, listener.client)
        
        # Display loaded MQTT outputs
        print(f"\nFound {len(config.mqtt_outputs)} MQTT output(s):")
        for out in config.mqtt_outputs:
            topic = out.get('topic', 'N/A')
            deps = mqtt_outputs.get_dependencies(topic)
            dep_str = ', '.join(sorted(deps)) if deps else 'none'
            print(f"  - {topic}: depends on {dep_str}")
        
        # Create combined callback that updates GPIO, MQTT, and LCD
        def on_value_change(mqtt_values: dict, changed_variable: str):
            """Handle value changes from MQTT inputs.
            
            Args:
                mqtt_values: Current MQTT input values
                changed_variable: ID of the variable that changed
            """
            # Update GPIO outputs based on MQTT inputs
            gpio_changes = gpio_outputs.update(mqtt_values, changed_variable)
            
            # Combine MQTT inputs and GPIO output states for MQTT outputs
            combined_values = mqtt_values.copy()
            combined_values.update(gpio_outputs.get_all_states())
            
            # Update MQTT outputs with combined values
            # First, update based on the MQTT input that changed
            mqtt_outputs.update(combined_values, changed_variable)
            
            # Then, if any GPIO outputs changed, update MQTT outputs that depend on them
            for gpio_output_id in gpio_changes.keys():
                mqtt_outputs.update(combined_values, gpio_output_id)
            
            # Update LCD display with combined values
            lcd_display.update(combined_values, changed_variable)
            
            # If GPIO outputs changed, also update LCD lines that depend on them
            for gpio_output_id in gpio_changes.keys():
                lcd_display.update(combined_values, gpio_output_id)
        
        # Set the callback on the listener
        listener.on_value_change = on_value_change
        
        # Create callback for when GPIO state changes complete (including after delays)
        def on_gpio_state_change(output_id: str, new_state: bool):
            """Handle GPIO state changes (called after delays complete).
            
            Args:
                output_id: GPIO output ID that changed
                new_state: The new state of the GPIO output
            """
            print(f"\n✓ GPIO callback: {output_id} → {new_state}")
            
            # Get current MQTT values and all GPIO states
            mqtt_values = listener.get_all_values()
            combined_values = mqtt_values.copy()
            combined_values.update(gpio_outputs.get_all_states())
            
            # Update MQTT outputs that depend on this GPIO output
            mqtt_outputs.update(combined_values, output_id)
            
            # Update LCD lines that depend on this GPIO output
            lcd_display.update(combined_values, output_id)
        
        # Set the callback on GPIO outputs
        gpio_outputs.on_state_change = on_gpio_state_change
        
        # Evaluate all outputs with initial values (all None)
        print("\nEvaluating initial output states...")
        initial_values = listener.get_all_values()
        gpio_outputs.update(initial_values)
        
        # Combine for MQTT outputs and LCD
        combined_initial = initial_values.copy()
        combined_initial.update(gpio_outputs.get_all_states())
        mqtt_outputs.update(combined_initial)
        lcd_display.update(combined_initial)
        
        # After initial evaluation, force update of web status data
        # This ensures the web endpoint has the latest state even before any MQTT messages are received
        if hasattr(lcd_display, 'get_current_lines'):
            lcd_display.get_current_lines()
        if hasattr(gpio_outputs, 'get_all_states'):
            gpio_outputs.get_all_states()
        if hasattr(mqtt_outputs, 'get_all_states'):
            mqtt_outputs.get_all_states()
        
        # Connect to broker
        listener.connect()
        
        # --- Move get_status here so it captures the live objects ---

        def get_status():
            try:
                # Map MQTT input values by topic for consistency, including units
                mqtt_input_by_topic = {}
                if hasattr(listener, 'inputs') and hasattr(listener, 'get_all_values'):
                    values = listener.get_all_values()
                    for inp in listener.inputs:
                        topic = inp.get('topic')
                        var_id = inp.get('id')
                        unit = inp.get('unit', '')
                        if topic and var_id in values:
                            mqtt_input_by_topic[topic] = {
                                "value": values[var_id],
                                "unit": unit
                            }

                # Dependencies
                dependencies = {
                    "inputs_to_outputs": {},  # topic -> list of output ids
                    "inputs_to_lcd": {},      # topic -> list of lcd line indices
                }
                # Inputs to outputs and LCD
                if hasattr(listener, 'inputs') and hasattr(gpio_outputs, 'variable_to_outputs') and hasattr(lcd_display, 'variable_to_lines'):
                    for inp in listener.inputs:
                        var_id = inp.get('id')
                        topic = inp.get('topic')
                        if not topic or not var_id:
                            continue
                        # Outputs
                        outputs = list(gpio_outputs.variable_to_outputs.get(var_id, set()))
                        dependencies["inputs_to_outputs"][topic] = outputs
                        # LCD lines
                        lcd_lines = list(lcd_display.variable_to_lines.get(var_id, set()))
                        dependencies["inputs_to_lcd"][topic] = lcd_lines

                return {
                    "inputs": {
                        "mqtt": mqtt_input_by_topic
                    },
                    "outputs": {
                        "gpio": gpio_outputs.get_all_states() if 'gpio_outputs' in locals() else {},
                        "mqtt": mqtt_outputs.get_all_states() if 'mqtt_outputs' in locals() else {},
                    },
                    "lcd": lcd_display.get_current_lines() if 'lcd_display' in locals() else [],
                    "dependencies": dependencies,
                }
            except Exception as e:
                import traceback; traceback.print_exc()
                return {"error": str(e)}

        # Start web status server in a background thread
        start_web_status_thread(get_status)
        
        # Start listening (blocking)
        listener.start()
        
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        
        # Clean up LCD first
        if 'lcd_display' in locals():
            lcd_display.cleanup()
        
        # Turn off all GPIO outputs first
        if 'gpio_outputs' in locals():
            gpio_outputs.cleanup()
        
        # Publish final MQTT states with GPIO outputs OFF (while still connected)
        if 'mqtt_outputs' in locals() and 'listener' in locals():
            # Create final values with all GPIO outputs set to False
            final_values = listener.get_all_values().copy()
            if 'gpio_outputs' in locals():
                final_values.update(gpio_outputs.get_all_states())
            mqtt_outputs.shutdown(final_values)
        
        # Stop MQTT listener (disconnect)
        if 'listener' in locals():
            listener.stop()
        
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up LCD first
        if 'lcd_display' in locals():
            lcd_display.cleanup()
        
        # Turn off all GPIO outputs on error
        if 'gpio_outputs' in locals():
            gpio_outputs.cleanup()
        
        # Publish final MQTT states (while still connected)
        if 'mqtt_outputs' in locals() and 'listener' in locals():
            final_values = listener.get_all_values().copy()
            if 'gpio_outputs' in locals():
                final_values.update(gpio_outputs.get_all_states())
            mqtt_outputs.shutdown(final_values)
        
        # Stop MQTT listener
        if 'listener' in locals():
            listener.stop()
        
        sys.exit(1)

if __name__ == "__main__":
    main()