# Joyonway P25B37 RS485 MQTT Gateway

An open-source integration to connect a **Joyonway P25B37** Spa Controller to Home Assistant using a local MQTT Broker. 

**Disclaimer:** This is a community-driven reverse engineering project. It is currently in a functional but experimental state. Contributions are highly welcome!

## Background & Differences to other Models

Joyonway produces various spa controllers. Some newer models (like the `P69B133` with integrated heat pumps) use a protocol running at 115200 baud with simple 8-bit checksums (similar to Balboa).

**The P25B37 is completely different!**
- It runs at **38400 Baud**.
- It uses a proprietary framing protocol (`1A` start, `1D` end).
- It utilizes a complex **Hardware CRC-32 (MPEG-2)** over little-endian word-swapped payload blocks.
- It enforces a **Rolling Counter** on toggle commands (Light, Heater) to prevent replay attacks and debouncing.

## Hardware Setup
1. Raspberry Pi (or similar).
2. USB to RS485 adapter connected to the RS485 A/B pins of the Joyonway Spa mainboard.
3. MQTT Broker (e.g., Mosquitto) running on your local network.

*Note: In the current setup, we are using `socat` to bridge a TCP stream (via a USR-W610 or similar module) to the RS485 interface.*

## Installation

1. Clone this repository.
2. Install Python requirements: `pip install paho-mqtt`
3. Edit `joyonway_mqtt.py` and adjust your MQTT Broker IP and RS485/Socat configuration.
4. Run the daemon: `python3 joyonway_mqtt.py`
5. *Optional:* Use the provided `joyonway.service` file to run it as a systemd background daemon.

## Features (Home Assistant Auto-Discovery)

When the script is running, it will automatically register the following entities in Home Assistant via MQTT Discovery:
- **Sensors:** Water Temperature (°C), Target Temperature (°C)
- **Binary Sensors:** Heater status, Circulation pump status, Pump 1 status (Low/High), Light status.
- **Controls:**
  - `Number` slider to set the absolute target temperature (15°C - 40°C).
  - `Select` dropdown for Pump speeds (OFF / LOW / HIGH).
  - `Button` to toggle the Light (cycles through the 8 colors).
  - `Button` to override the Heating mode.

## Protocol Deep-Dive (For Contributors)

If you want to contribute and improve the connection reliability, here is the decoded P25B37 RS485 Protocol.

### 1. Serial Port
**38400 Baud, 8 Data bits, No Parity, 1 Stop bit (8N1)**

### 2. Framing & Byte Stuffing
Every packet starts with `0x1A` and ends with `0x1D`.
If a data byte happens to be `0x1A`, `0x1B`, `0x1C` or `0x1D`, it must be escaped using a `0x1B` prefix.
*   `0x1A` -> `1B 11`
*   `0x1B` -> `1B 13`
*   `0x1C` -> `1B 14`
*   `0x1D` -> `1B 15`
*(You must unescape incoming payloads before parsing, and escape outgoing payloads before sending!)*

### 3. Controller Status Broadcast (`1A FF`)
The mainboard continuously broadcasts its state. The unescaped payload starts with `1A FF`.
*   **Byte 09:** Current water temperature in °F (e.g., Hex `50` = 80°F = 26.6°C)
*   **Byte 16:** Target temperature setpoint in °F
*   **Byte 12:** Jets / Pump (Bitmask: `0x02` = Pump 1 Low, `0x04` = Pump 1 High)
*   **Byte 14:** Heater & Circulation (Bitmask: `0x10` = Heater active, `0x08` = Circulation pump active)
*   **Byte 17:** Light Status (Values `0x01` to `0x08` = Light colors, `0x80` / `0x00` = Off)

### 4. Sending Commands & Hardware CRC32
The display sends commands to the controller starting with `1A 01 20 10 ...`.
Every command **MUST** include the *current* target temperature in Fahrenheit, otherwise the CRC is invalid and the controller ignores it.

**The CRC Algorithm:**
The Joyonway P25B37 uses the standard `CRC32-MPEG-2` polynomial (`0x04C11DB7`), but the data is processed in **32-Bit Little-Endian Words**.
Before calculating the CRC, the payload must be padded to a multiple of 4 bytes, and every 4-byte block must be byte-swapped (e.g., `A B C D` becomes `D C B A`). The resulting 32-Bit CRC is then appended as Little-Endian to the packet.

### 5. Rolling Counters (Debouncing)
If you send the exact same command for "Toggle Light" twice, the controller ignores the second command. The physical display increments a counter for toggle buttons.
*   For Light commands: Byte 21 increments from `0x80` to `0x87` and rolls over.
*   For Heater commands: Byte 21 increments similarly.

### 6. Known Limitation: Bus Collisions
This is a Master-Slave bus. The controller expects the display to only send data at specific times. Since we do not perfectly synchronize our transmission windows with the display, collisions occur.
**Current Workaround:** The script uses "Command Flooding". When a command is triggered in HA, the script floods the bus with the correctly generated command every 50ms for 3 seconds. Statistically, one of the packets always gets through. This is ugly but functional. A proper collision avoidance algorithm is needed.
