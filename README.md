# RPi MQTT Relay

> ⚠️ **Work in Progress** - This project is still under active development. Features, configuration, and documentation may change.

Raspberry Pi MQTT Relay is a small footprint controller that can receive inputs from an MQTT server, then act on the GPIO to activate/deactivate external relays.
At the same time, the controller can display information in a LCD display, and publish events to the MQTT server.

All of the reading from MQTT, control of GPIO pins, write to an LCD display, and publish values to MQTT.

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

### Configuration

Before running, ensure your `config.yaml` is properly configured with:

- **MQTT Inputs**: Define the MQTT topics you want to subscribe to
- **GPIO Outputs**: Configure GPIO pins and activation logic
- **LCD Display**: Optional display configuration for information output

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

- `./scripts/setup` - Set up the environment on the Pi
- `./scripts/debug` - Run with Python debugger attached
- `./scripts/test` - Run tests on the Pi
- `./scripts/build` - Build Docker image on the Pi

## Web Status API

A minimal web interface is available for status monitoring. After starting the controller, visit:

    http://<raspberry-pi-ip>:5000/status

This endpoint returns a JSON object with the current state of all MQTT inputs, GPIO outputs, MQTT outputs, and LCD lines.

Example output:

```json
{
  "inputs": {"temperature": 22.5, "ph": 7.1, ...},
  "gpio_outputs": {"drain_pump": false, ...},
  "mqtt_outputs": {"rpi-mqtt-relay/relay/drain_pump": "OFF", ...},
  "lcd": ["  100 % |  22.5 °C", " 7.10 pH"]
}
```

> **Note:**
> To access the web status API from outside the container, add the following to your `docker-compose.yml` or `docker-compose.dev.yml` under the `rpi-mqtt-relay` service:
>
> ```yaml
>     ports:
>       - "5000:5000"
> ```
>
> This maps the container's port 5000 to the host, making the web interface available at `http://<raspberry-pi-ip>:5000/status`.
