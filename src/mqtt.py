"""MQTT client for listening to input topics and handling messages."""

import logging
import paho.mqtt.client as mqtt
from typing import Dict, Any, Callable, Optional
from config import Config


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MQTTListener:
    """MQTT client that subscribes to configured input topics."""
    
    def __init__(self, config: Config, on_value_change: Optional[Callable[[Dict[str, Any], str], None]] = None):
        """Initialize MQTT listener with configuration.
        
        Args:
            config: Configuration object containing MQTT settings
            on_value_change: Optional callback function called when any value changes.
                           Receives the complete values dictionary and the ID of the changed variable.
        """
        self.config = config
        self.broker_config = config.mqtt_broker
        self.inputs = config.mqtt_inputs
        self.on_value_change = on_value_change
        
        # Store current values
        self.values: Dict[str, Any] = {}
        
        # Topic to input ID mapping
        self.topic_map: Dict[str, Dict[str, Any]] = {}
        for input_config in self.inputs:
            topic = input_config.get('topic')
            if topic:
                self.topic_map[topic] = input_config
                # Initialize value as None
                self.values[input_config['id']] = None
        
        # Create MQTT client
        self.client = mqtt.Client(client_id="rpi-mqtt-relay")
        
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # Set up authentication if provided
        username = self.broker_config.get('username')
        password = self.broker_config.get('password')
        if username and password:
            self.client.username_pw_set(username, password)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker.
        
        Args:
            client: MQTT client instance
            userdata: User data
            flags: Connection flags
            rc: Result code
        """
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            
            # Subscribe to all input topics
            for topic in self.topic_map.keys():
                client.subscribe(topic)
                logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Callback when a message is received.
        
        Args:
            client: MQTT client instance
            userdata: User data
            msg: Message object containing topic and payload
        """
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        # Get input configuration for this topic
        input_config = self.topic_map.get(topic)
        if not input_config:
            logger.warning(f"Received message on unknown topic: {topic}")
            return
        
        input_id = input_config['id']
        input_name = input_config['name']
        unit = input_config.get('unit', '')
        
        # Store previous value
        old_value = self.values.get(input_id)
        
        # Try to convert to float if possible
        try:
            new_value = float(payload)
        except ValueError:
            new_value = payload
        
        # Update stored value
        self.values[input_id] = new_value
        
        # Print to console only if value changed
        unit_str = f" {unit}" if unit else ""
        value_changed = False
        
        if old_value is None:
            logger.info(f"[{input_name}] Initial value: {new_value}{unit_str}")
            print(f"[{input_name}] Initial value: {new_value}{unit_str}")
            value_changed = True
        elif old_value != new_value:
            logger.info(f"[{input_name}] Changed: {old_value}{unit_str} → {new_value}{unit_str}")
            print(f"[{input_name}] Changed: {old_value}{unit_str} → {new_value}{unit_str}")
            value_changed = True
        
        # Trigger callback if value changed, passing which input changed
        if value_changed and self.on_value_change:
            self.on_value_change(self.values, input_id)
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker.
        
        Args:
            client: MQTT client instance
            userdata: User data
            rc: Result code
        """
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker. Return code: {rc}")
            print(f"Disconnected from MQTT broker (rc={rc})")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def connect(self):
        """Connect to MQTT broker and start listening."""
        host = self.broker_config.get('host', 'localhost')
        port = self.broker_config.get('port', 1883)
        keepalive = self.broker_config.get('keepalive', 60)
        
        logger.info(f"Connecting to MQTT broker at {host}:{port}")
        print(f"Connecting to MQTT broker at {host}:{port}...")
        
        try:
            self.client.connect(host, port, keepalive)
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise
    
    def start(self):
        """Start the MQTT client loop (blocking)."""
        logger.info("Starting MQTT listener loop")
        print("MQTT Listener started. Waiting for messages...")
        print("-" * 60)
        self.client.loop_forever()
    
    def start_background(self):
        """Start the MQTT client loop in background (non-blocking)."""
        logger.info("Starting MQTT listener loop in background")
        print("MQTT Listener started in background. Waiting for messages...")
        print("-" * 60)
        self.client.loop_start()
    
    def stop(self):
        """Stop the MQTT client loop."""
        logger.info("Stopping MQTT listener")
        self.client.loop_stop()
        self.client.disconnect()
    
    def get_value(self, input_id: str) -> Any:
        """Get current value for an input.
        
        Args:
            input_id: ID of the input
            
        Returns:
            Current value or None if not set
        """
        return self.values.get(input_id)
    
    def get_all_values(self) -> Dict[str, Any]:
        """Get all current values.
        
        Returns:
            Dictionary of input IDs to current values
        """
        return self.values.copy()
