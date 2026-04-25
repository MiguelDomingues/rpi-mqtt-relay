# RPi MQTT Relay

> ⚠️ **Work in Progress** - This project is still under active development. Features, configuration, and documentation may change.

Raspberry Pi MQTT Relay is a lightweight controller that receives inputs from an MQTT server, acts on GPIO pins to activate/deactivate external relays, displays information on an LCD display, and publishes events back to the MQTT server.

## Hardware & Prerequisites

### Supported Platforms

- **Developed & Tested on**: Raspberry Pi 1 Model B
  - Uses lightweight Alpine Linux base (arm6vl architecture for RPi 1 compatibility)
  - Minimal CPU and memory footprint
- **Other versions**: May work on other Raspberry Pi models (Pi 2, 3, 4, 5) and ARM-based Linux systems, but this is untested

⚠️ **Important Disclaimer**: This project is provided as-is with **no support whatsoever**. You use this software entirely at your own risk, regardless of your platform. Any issues, failures, or unexpected behavior are your responsibility to debug and resolve.

### GPIO Hardware

- GPIO pins controlled via BCM numbering (see your config example for pin assignments)
- **⚠️ Safety Warning**: GPIO pins are directly controlled at 3.3V logic level. Ensure:
  - Relays are properly rated for GPIO control voltage
  - No high-voltage circuits are directly connected to GPIO pins
  - Use properly isolated relay modules
  - Implement proper physical safeguards (e.g., enclosures, fuses)
  - Consult hardware datasheets before deployment

### LCD Display (Optional)

- **I2C LCD Display** (typical 16×2 character display)
- I2C address: `0x27` (fixed, may vary by manufacturer)
- Bus: I2C (pins 2/3 on most Pi boards for SDA/SCL)
- Requires I2C enabled in Pi configuration: `raspi-config` → Interfacing Options → I2C
- Can be omitted if LCD support not needed (set empty `lcd` section in config)

### Network & Services

- **MQTT Broker**: Home Assistant, Mosquitto, or any MQTT 3.1.1+ compatible broker
- **Network Connectivity**: **Ethernet recommended** (for stable, reliable MQTT communication); WiFi not tested but should work
- **SSH Access** (for remote development): Optional, enables VS Code remote debugging

## Running

### Using Docker Compose

The recommended way to run the application is using Docker Compose on your Raspberry Pi.

#### Latest Release

To run the latest stable release:

```bash
docker compose up -d
```

This uses the `latest` tag, which points to the most recent versioned release (e.g., `v1.0.0`).

#### Development Version

To run the latest development build from the main branch:

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

This uses the `dev` tag, which is updated with every commit to main and may include unreleased features or changes.

Docker Compose will:

- Pull the image from GitHub Container Registry
- Start the container with privileged access to GPIO and system devices
- Mount your `config.yaml` for configuration
- Automatically restart on failure

#### Local Development Build

To build and run the application locally from your source code:

```bash
docker compose -f docker-compose.local.yml up -d --build
```

This configuration:

- Builds the Docker image locally from your Dockerfile
- Mounts `sys` and `dev` directories for GPIO and device access
- Exposes port 5000 for the web status API
- Uses the `rpi-mqtt-relay-local` container name
- Automatically restarts the container unless stopped
- Requires privileged mode to interact with GPIO and system devices

This is useful for testing local changes without publishing to the registry, or for development when you don't have network access to GitHub Container Registry.

### Configuration

Before running, ensure your `config.yaml` is properly configured with:

- **MQTT Inputs**: Define the MQTT topics you want to subscribe to
- **GPIO Outputs**: Configure GPIO pins and activation logic
- **LCD Display**: Optional display configuration for information output

## MQTT Configuration

The controller communicates with an MQTT broker to receive sensor inputs and publish output states. Your MQTT broker (Home Assistant, Mosquitto, etc.) must be running and accessible before starting the controller.

### MQTT Broker Setup

Add the following to your `config.yaml` under the `mqtt` key:

```yaml
mqtt:
  host: "192.168.1.100"            # MQTT broker IP address or hostname
  port: 1883                       # Optional: MQTT broker port (defaults to 1883)
  username: "mqtt_user"            # Optional: MQTT broker username
  password: "mqtt_password"        # Optional: MQTT broker password
```

All fields except `host` are optional. The controller defaults to port 1883, but you can customize it if your MQTT broker uses a different port.

### Topic Naming Conventions

Topics can follow any MQTT-compatible naming scheme. These are recommended patterns for organization, but any valid MQTT topic path will work:

- **Sensor data from Home Assistant**: `homeassistant/<device>/<sensor>`
  - Examples: `homeassistant/pool/temperature`, `homeassistant/pool/ph`
- **Custom topics**: Use any MQTT-compatible path you prefer
  - Format: `<domain>/<device>/<measurement>` or any structure that makes sense for your setup
- **Simple topics**: You can use flat or minimal hierarchies
  - Examples: `pool/temp`, `sensors/ph`, or even `temp`, `ph`

The controller will subscribe to whatever topics you define in your configuration, regardless of naming structure.

### MQTT Input Values

The controller subscribes to MQTT input topics and automatically parses values as:

- **Numeric** (float): Converted using `|float` filter (e.g., "22.5" → 22.5)
- **Integer** (int): Converted using `|int` filter (e.g., "75" → 75)
- **String**: Kept as-is (e.g., "ON", "OFF")

If an input topic doesn't publish a value, it's stored as `None` (null). Use conditional checks in templates:

```yaml
on: "{{ temperature|float > 25 if temperature is not none else False }}"
```

### MQTT Output Publishing

The controller automatically publishes GPIO output states back to MQTT. Define output topics in your config:

```yaml
outputs:
  mqtt:
  - topic: "rpi-mqtt-relay/relay/pump_status"
    value: "{{ 'ON' if drain_pump else 'OFF' }}"
  - topic: "rpi-mqtt-relay/output/water_level"
    value: "{{ water_level }}"  # Publish current input value
```

### Home Assistant Integration

To integrate with Home Assistant, ensure your MQTT broker is accessible. Example configuration:

```yaml
mqtt:
  host: "192.168.1.100"
  username: "mqtt_user"
  password: "mqtt_password"
```

#### Create MQTT Automations in Home Assistant

Set up automations in Home Assistant to publish sensor values to MQTT topics that your controller listens to. This example publishes a pH sensor value to the relay controller:

```yaml
alias: MQTT Publish homeassistant/pool/ph
description: "Publish pH sensor state to MQTT for relay controller"
triggers:
  - trigger: state
    entity_id:
      - sensor.ph
conditions: []
actions:
  - action: mqtt.publish
    data:
      payload: "{{ states('sensor.ph') }}"
      topic: homeassistant/pool/ph
mode: single
```

Then subscribe to this topic in your relay controller config:

```yaml
inputs:
  mqtt:
  - id: ph
    name: pH Level
    topic: homeassistant/pool/ph
    unit: ""
```

This approach gives you full control over which Home Assistant entities get published to MQTT and allows for custom transformations in the automation.

#### Remote Control Switches

You can also manually create MQTT switches in Home Assistant and subscribe to their state topics for remote control of GPIO outputs.

## Sample configuration

This example demonstrates a pool automation system where the controller monitors water quality and level sensors via MQTT, then automatically controls various pumps and valves through GPIO relays. The controller continuously reads sensor values, evaluates conditions using configurable logic, and acts accordingly by triggering relays and publishing state updates.

### How it works

```mermaid
graph LR
    A["MQTT Broker<br/>(Home Assistant)"] -->|Sensor Data| B["RPi MQTT Relay<br/>Controller"]
    B -->|GPIO Control| C["Relays"]
    C -->|Activate/Deactivate| D["Pumps & Valves"]
    B -->|State Updates| A
    B -->|Display| E["LCD Screen"]
    
    style B fill:#4A90E2,color:#fff
    style A fill:#50C878,color:#fff
    style C fill:#FF6B6B,color:#fff
    style D fill:#FFD700,color:#000
    style E fill:#9B59B6,color:#fff
```

The example shows a pool control scenario with the following configuration:

- **Inputs**: Temperature, pH, ORP, salinity, water level sensors
- **Outputs**: Drain pump, water inlet valve, pH increase pump
- **Logic**: Automatically maintain water level between 50-75%, regulate pH, manage heating
- **Feedback**: LCD display showing real-time status, MQTT state publishing for monitoring

### Inputs

Define MQTT topics to subscribe to for reading sensor values:

```yaml
inputs:
  mqtt:
  - id: temperature
    name: Temperature
    topic: homeassistant/pool/temperature
    unit: "°C"
  - id: water_level
    name: Water Level
    topic: homeassistant/pool/water_level
    unit: "%"
  - id: ph
    name: pH
    topic: homeassistant/pool/ph
    unit: ""
```

### Outputs

Configure GPIO pins with conditional logic using Jinja2 templates, and publish output states back to MQTT:

```yaml
outputs:
  gpio:
  - id: drain_pump
    name: Drain Pump
    pin: 24
    on: "{{ water_level|float > 75 if water_level is not none else False }}"
    delay:
      on: 30
      off: 0
  - id: water_inlet_valve
    name: Water Inlet Valve
    pin: 17
    on: "{{ (water_level|float < 50) if water_level is not none else False }}"
    delay:
      on: 30
      off: 0
  - id: ph_increase_pump
    name: pH Increase Pump
    pin: 22
    on: "{{ ph|float < 7.2 if ph is not none else False }}"
    delay:
      on: 30
      off: 30
  
  mqtt:
  - topic: rpi-mqtt-relay/relay/drain_pump
    value: "{{ 'ON' if drain_pump else 'OFF' }}"
  - topic: rpi-mqtt-relay/relay/water_inlet_valve
    value: "{{ 'ON' if water_inlet_valve else 'OFF' }}"
  - topic: rpi-mqtt-relay/relay/ph_increase_pump
    value: "{{ 'ON' if ph_increase_pump else 'OFF' }}"
```

### LCD Display

Configure up to 2 lines for the LCD display with dynamic content using Jinja2 templates:

```yaml
lcd:
  lines:
    - "{{ '{:>5}'.format('%3.0f' % water_level|float) if water_level is not none else ' Lvl' }} % | {{ '{:>5}'.format('%0.1f' % temperature|float) if temperature is not none else ' Temp' }} °C"
    - "{{ '{:>5}'.format('%0.2f' % ph|float) if ph is not none else '  pH' }} pH"
```

## GPIO Output Behavior

### Delay Mechanism

Each GPIO output supports independent **on** and **off** delays to prevent rapid switching and protect hardware:

```yaml
outputs:
  gpio:
  - id: drainage_pump
    pin: 24
    delay:
      on: 300    # Wait 300 seconds before turning ON
      off: 5     # Wait 5 seconds before turning OFF
```

#### How Delays Work

1. When template evaluates to `true`, the controller starts a timer for the **on** delay
2. After the delay expires, the GPIO pin is set HIGH (activated)
3. When template evaluates to `false`, the controller starts a timer for the **off** delay
4. After the delay expires, the GPIO pin is set LOW (deactivated)
5. If the template output changes before the delay completes, the timer is cancelled and restarted

#### Use cases

- **Long on-delays**: Prevent accidental activation (safety measure for pump control)
- **Short off-delays**: Stabilize outputs that flicker or oscillate
- **Zero delays**: Set to `0` for immediate response (e.g., `delay: { on: 0, off: 0 }`)

### Template Variables & Filters

Templates use Jinja2 with access to all input variables and GPIO output states:

#### Available variables

- All MQTT input IDs: `{{ temperature }}`, `{{ water_level }}`, etc.
- All GPIO output IDs (current state): `{{ drain_pump }}`, `{{ water_inlet_valve }}`
- Special function: `{{ now() }}` - returns current timestamp

#### Common filters

- `|float` - Convert to floating-point number: `{{ temperature|float }}`
- `|int` - Convert to integer: `{{ salinity|int }}`
- `|default(value)` - Provide default if variable is missing: `{{ temperature|default(20) }}`

#### Type checking

- `is not none` - Check if variable has a value: `{{ temperature is not none }}`
- `is none` - Check if variable is missing: `{{ orp is none }}`

#### Example with filters

```yaml
on: "{{ temperature|float > 25 if temperature is not none else False }}"
```

### Preventing Conflicting Outputs

You can reference other GPIO outputs in templates to create mutual exclusion logic:

```yaml
outputs:
  gpio:
  - id: drain_pump
    pin: 24
    on: "{{ not water_inlet_valve and water_level|float > 75 }}"
  - id: water_inlet_valve
    pin: 23
    on: "{{ not drain_pump and water_level|float < 50 }}"
```

In this example:

- Drain pump only activates if water inlet valve is OFF
- Water inlet valve only activates if drain pump is OFF
- Prevents both pumps from running simultaneously

### GPIO Pin Conflicts

⚠️ **Important**: Ensure each GPIO pin is only used once in your configuration. If two outputs reference the same pin, behavior is undefined. Pin assignment example:

```yaml
outputs:
  gpio:
  - id: pump_1
    pin: 24      # BCM pin 24
  - id: pump_2
    pin: 23      # BCM pin 23 (different pin)
```

Always verify your pin numbers match your hardware wiring diagram and that no pins are duplicated.

## LCD Display Setup

### Hardware Configuration

The LCD display communicates via I2C protocol. Typical 16×2 character displays use the following wiring:

| LCD Pin | Raspberry Pi Pin |
| --- | --- |
| VCC | 5V (pin 2 or 4) |
| GND | GND (pin 6, 9, 14, or 20) |
| SDA | GPIO 2 (pin 3) |
| SCL | GPIO 3 (pin 5) |

#### Enabling I2C on Raspberry Pi

1. Run `raspi-config` on your Pi
2. Navigate to: Interfacing Options → I2C → Enable
3. Reboot the device

### I2C Address Detection

The controller defaults to I2C address `0x27` on port 1. To verify your LCD is accessible:

```bash
i2cdetect -y 1
```

This will show all devices on the I2C bus. If your LCD shows a different address, you may need to check your hardware or LCD module documentation. The default address `0x27` works with most common 16×2 I2C displays.

### LCD Line Templates

Each line supports Jinja2 templating with dynamic content:

```yaml
lcd:
  lines:
    - "{{ temperature|float if temperature is not none else '---' }} C"
    - "pH: {{ ph|float|round(2) if ph is not none else '---' }}"
```

#### Important considerations

- **Character limit**: 16 characters per line (typical 16×2 display)
- **Line limit**: Maximum 2 lines supported
- **Missing inputs**: Use `is not none` checks to handle missing sensor values
- **Formatting**: Use Jinja2 filters for alignment, rounding, padding:
  - `{{ value|round(2)|string }}` - Round to 2 decimals
  - `{{ '{:>5}'.format(value) }}` - Right-align in 5 characters
  - `{{ '{:<10}'.format(text) }}` - Left-align in 10 characters

### LCD Display Behavior

- **Update frequency**: Display updates whenever any input value changes
- **Graceful degradation**: If LCD is not connected or disabled, the controller continues operating normally
- **No LCD**: To disable LCD display, leave the `lcd` section empty or omit it entirely

## Web API & Frontend

### REST API Endpoint

A Flask web server runs on **port 5000** and provides a JSON status endpoint:

```http
GET http://<raspberry-pi-ip>:5000/status
```

### Response Structure

The `/status` endpoint returns the complete current state:

```json
{
  "inputs": {
    "temperature": 22.5,
    "water_level": 65.0,
    "ph": 7.1,
    "pool_pump": "ON"
  },
  "gpio_outputs": {
    "drain_pump": false,
    "water_inlet_valve": true,
    "ph_increase_pump": false
  },
  "mqtt_outputs": {
    "rpi-mqtt-relay/relay/drain_pump": "OFF",
    "rpi-mqtt-relay/relay/water_inlet_valve": "ON",
    "rpi-mqtt-relay/keepalive": "2026-04-25 14:30:45.123456"
  },
  "lcd": [
    " 065 % |  22.5 °C",
    " 7.10 pH   820 ORP"
  ]
}
```

#### Response fields

- `inputs` - Current values of all MQTT input topics (or `null` if no value received yet)
- `gpio_outputs` - Current GPIO output states (true = ON, false = OFF)
- `mqtt_outputs` - Published MQTT output topics and their current values
- `lcd` - Current rendered LCD display lines

### Web Dashboard

A simple web dashboard is available at:

```http
GET http://<raspberry-pi-ip>:5000/
```

This serves a JavaScript-based frontend (`static/index.html`) that displays real-time status updates. The dashboard:

- Polls the `/status` endpoint periodically
- Displays all inputs, outputs, and LCD content
- Shows current system state at a glance

### Port Exposure

The web API on port 5000 is already exposed in all provided Docker Compose configurations (`docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.local.yml`).

Access the web API at: `http://<raspberry-pi-ip>:5000/status`

**Note:** If using a custom Docker Compose setup without port mapping, you'll need to configure port exposure to access the API from outside the container.

### Security Considerations

The web API currently has **no authentication**. It exposes:

- Current sensor values
- Output states
- System status

In a production environment with internet access, consider:

- Restricting network access (firewall rules)
- Using a reverse proxy with authentication
- Running behind a VPN
- Disabling port exposure to external networks

## Local development

### Remote Development Setup

This project is configured for remote development on a Raspberry Pi with automatic code synchronization and debugging.

#### Prerequisites

- SSH access to your Raspberry Pi configured in `~/.ssh/` (typically with `id_ed25519` key)
- VS Code with the [SFTP extension](https://marketplace.visualstudio.com/items?itemName=Natizysklyansky.sftp) installed

#### Setup

1. **Copy configuration files:**

```bash
cp .vscode/settings.json.sample .vscode/settings.json
cp .vscode/sftp.json.sample .vscode/sftp.json
```

1. **Update `.vscode/settings.json`** with your Raspberry Pi details:

```json
{
    "pi_hostname": "your-pi-hostname-or-ip",
    "pi_username": "pi",
    "pi_root_folder": "/home/pi/rpi-mqtt-relay/"
}
```

1. **Update `.vscode/sftp.json`** with your Raspberry Pi host and SSH key path

#### Debugging

With the configuration in place, you can debug the application directly on the Raspberry Pi:

1. **Press F5** in VS Code to start debugging
   - This runs the Debug task which executes `./scripts/debug` on the Pi via SSH
   - The app starts with the Python debugger (`debugpy`) listening on port 5678

2. **Code synchronization** happens automatically:
   - The SFTP extension watches `src/`, `scripts/`, `requirements.txt`, and `config.yaml`
   - Changes are automatically synced to the Pi when files are saved
   - The debugger attaches to the remote Python process for interactive debugging

3. **Set breakpoints** in VS Code and they will trigger in the remote process

#### Available Scripts

- `./scripts/setup` - Set up the environment on the Pi (installs dependencies in virtual environment)
- `./scripts/debug` - Run with Python debugger attached (debugpy listening on port 5678)
- `./scripts/build` - Build Docker image on the Pi with tag `rpi-mqtt-relay:arm6vl`

## Troubleshooting

### MQTT Connection Issues

**Problem**: "Failed to connect to MQTT broker"

**Solutions:**

- Verify MQTT broker is running and accessible: `ping <broker-ip>`
- Check `mqtt.host` in `config.yaml` matches your broker
- Confirm firewall allows port 1883
- If using authentication, verify `username` and `password` are correct
- Check broker logs for connection errors
- Restart the controller after fixing config: `docker compose restart`

### GPIO Access Errors

**Problem**: "Permission denied" or "GPIO not available"

**Solutions:**

- Ensure container is running in **privileged mode** (check docker-compose)
- Required flag: `privileged: true`
- Without this, GPIO pins cannot be controlled
- Verify RPi GPIO driver is installed: `python3 -c "import RPi.GPIO"` on the Pi

### Template Evaluation Failures

**Problem**: Outputs not activating despite correct sensor values

**Solutions:**

- Check template syntax in `config.yaml` - Jinja2 is strict about quotes and braces
- Verify input variables exist: `{{ debug_var }}` in template to test
- Use `if variable is not none` to handle missing sensors
- Check application logs for template errors: `docker logs <container-name>`
- Test template with simple example: `on: "{{ True }}"` to verify GPIO works

#### Common template mistakes

```yaml
# ❌ WRONG - quotes not escaped
on: "{{ temperature|float > "25" else False }}"

# ✅ CORRECT
on: "{{ temperature|float > 25 else False }}"

# ❌ WRONG - missing filter
on: "{{ water_level > 50 }}"

# ✅ CORRECT (water_level is a string from MQTT)
on: "{{ water_level|float > 50 if water_level is not none else False }}"
```

### LCD Display Not Updating

**Problem**: LCD screen blank or not showing updates

**Solutions:**

- Verify I2C connection: `i2cdetect -y 1` on the Pi
- Confirm LCD address matches config (default 0x27)
- Check that I2C is enabled: `raspi-config` → Interfacing Options → I2C → Enable
- Verify pin connections (SDA to GPIO 2, SCL to GPIO 3)
- Enable LCD in config - it's optional and disabled if `lcd` section is empty
- Check application logs for I2C errors

### Web API Not Responding

**Problem**: `http://<pi-ip>:5000/status` times out or connection refused

**Solutions:**

- Verify port 5000 is exposed in docker-compose: `ports: ["5000:5000"]`
- Check container is running: `docker ps | grep mqtt-relay`
- Verify firewall allows port 5000 on your network
- Check application logs: `docker logs rpi-mqtt-relay`
- Test local connection from Pi: `curl http://localhost:5000/status`
- If using dev/local compose, ensure `--build` was used: `docker compose -f docker-compose.dev.yml up -d --build`

### Container Fails to Start

**Problem**: Container exits immediately or crashes

**Solutions:**

- Check logs: `docker logs rpi-mqtt-relay` (or `rpi-mqtt-relay-dev`, `rpi-mqtt-relay-local`)
- Verify `config.yaml` exists and is valid YAML (use a YAML validator)
- Ensure MQTT broker is reachable before starting
- Check required Python dependencies: `docker-compose.ps` output
- Try local build instead of pulling image: use `docker-compose.local.yml`

### GPIO Pin Already in Use

**Problem**: "Pin already in control" or similar error

**Solutions:**

- Check `config.yaml` for duplicate pin numbers in GPIO outputs
- Ensure no other process is using the same GPIO pins
- Restart the container: `docker compose restart`
- On the host, check: `lsof /dev/mem` (if GPIO conflict persists)

## Development & Testing

### Manual Testing

While formal automated tests are not yet implemented, you can validate the controller manually:

#### Test via MQTT

- Publish test messages to configured input topics
- Verify GPIO pins activate correctly
- Check that state changes are reflected on LCD and published to output topics

#### Test Configuration

- Validate YAML syntax: Online YAML validators or `python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"`
- Test template fragments: Add simple templates like `on: "{{ True }}"` to verify GPIO functionality
- Verify sensor parsing by checking log output for correct value conversions

#### Test Docker Deployment

- GPIO output logic
- MQTT message handling
- LCD rendering

### Running Locally (Non-Docker)

For development without Docker:

1. **Clone and set up Python environment:**

   ```bash
   cd rpi-mqtt-relay
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**

   ```bash
   python3 src/main.py --config config.yaml
   ```

### Code Structure

```text
src/
├── main.py              # Entry point, signal handling, orchestration
├── config.py            # YAML configuration parser
├── mqtt.py              # MQTT client for subscriptions (inputs)
├── outputs.py           # GPIO output manager with template evaluation
├── mqtt_outputs.py      # Publishing output states to MQTT
├── lcd.py               # LCD display manager with template rendering
├── web_status.py        # Flask web API server
└── static/
    ├── index.html       # Web dashboard HTML
    └── status.js        # Dashboard JavaScript (real-time updates)
```

### Key Components

- **main.py**: Initializes all subsystems, handles graceful shutdown via signals (SIGTERM, SIGINT)
- **outputs.py**: Template evaluation with Jinja2, dependency tracking, delay timers
- **mqtt.py**: Subscribes to input topics, maintains value cache, triggers callbacks
- **web_status.py**: Flask server providing `/status` endpoint and static file serving
- **config.py**: Parses `config.yaml` and validates configuration structure

### Making Code Changes

With remote development enabled:

1. Edit files locally in VS Code
2. SFTP extension automatically syncs to Pi
3. For GPIO/MQTT changes: Restart the app (`docker compose restart`)
4. For debugging: Press F5 to attach debugpy (port 5678)
5. View logs: `docker logs -f rpi-mqtt-relay`

## Operational & Deployment

### Container Environment Variables

Optional environment variables can be set in `docker-compose.yml`:

```yaml
services:
  rpi-mqtt-relay:
    environment:
      - TZ=UTC                    # Set timezone for timestamps (default: UTC)
```

**Note**: The `TZ` environment variable is the only environment variable that affects controller behavior. It sets the system timezone for timestamps in logs and message handling. Other logging configuration is built into the application (uses Python logging at INFO level).

### Logging

Application startup logs are printed to stdout. View them with:

```bash
docker logs rpi-mqtt-relay
docker logs -f rpi-mqtt-relay    # Follow logs in real-time
```

### Health & Monitoring

Monitor the application via:

1. **Web API status check**: `curl http://<pi-ip>:5000/status`
2. **Docker health**: `docker ps` (shows container status)
3. **MQTT keepalive**: Check `rpi-mqtt-relay/keepalive` topic (published with each cycle)
4. **Container logs**: `docker logs rpi-mqtt-relay`

### Performance Considerations

- **Cycle time**: Controller evaluates templates and updates outputs on each MQTT message
- **Memory**: Minimal footprint suitable for Pi 1 (typically < 50MB)
- **CPU**: Lightweight async MQTT client, efficient template evaluation
- **Network**: Updates only occur when input values change (event-driven)

### Running Multiple Instances

To run multiple controllers on the same Pi:

1. Use different container names and ports
2. Assign unique GPIO pins to each instance
3. Use separate `config.yaml` files or environment-based overrides
4. Ensure different MQTT topics to avoid conflicts

Example:

```yaml
services:
  relay-pool:
    image: ghcr.io/migueldomingues/rpi-mqtt-relay:latest
    container_name: pool-controller
    ports:
      - "5000:5000"
    volumes:
      - ./config-pool.yaml:/app/config.yaml
      
  relay-heating:
    image: ghcr.io/migueldomingues/rpi-mqtt-relay:latest
    container_name: heating-controller
    ports:
      - "5001:5000"
    volumes:
      - ./config-heating.yaml:/app/config.yaml
```

## Version Management & Upgrades

### Image Tags

The project uses semantic versioning:

- **`latest`** - Most recent stable release (e.g., `v1.2.3`)
- **`dev`** - Latest development build from main branch (updated on every commit)
- **Specific versions** - Pin to a specific release: `ghcr.io/migueldomingues/rpi-mqtt-relay:v1.2.3`
- **`main`** - Alias for dev tag

### Upgrading

**To latest stable release:**

```bash
docker compose pull
docker compose up -d
```

**To development version:**

```bash
docker compose -f docker-compose.dev.yml pull
docker compose -f docker-compose.dev.yml up -d
```

### Breaking Changes

Monitor the repository for release notes. Common upgrade considerations:

- Config.yaml schema changes may require updates
- New required MQTT topics or GPIO pins
- MQTT output format changes

Always back up your `config.yaml` before upgrading.

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE.md](LICENSE.md) for details.
