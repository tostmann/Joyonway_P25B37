import time
import socket

import zlib

import json
import threading
import queue

cmd_queue = queue.Queue()
import paho.mqtt.client as mqtt

SOCAT_HOST = '10.10.11.161'
SOCAT_PORT = 8899

MQTT_BROKER = '127.0.0.1'
MQTT_PORT = 1883
MQTT_USER = None           
MQTT_PASS = None           
MQTT_BASE_TOPIC = "joyonway"
last_setpoint_f = 98

HA_PREFIX = "homeassistant"
DEVICE_INFO = {
    "identifiers": ["joyonway_p25b37"],
    "name": "Joyonway Spa",
    "manufacturer": "Joyonway",
    "model": "P25B37 Controller"
}

# --- REPLAY COMMANDS ---
COMMANDS = {
    "light_on": bytes.fromhex("1A 01 20 08 3C AA 10 00 00 6B 73 E4 B9 1D"),
    "light_off": bytes.fromhex("1A 01 20 08 3C AA 10 00 00 6B 73 E4 B9 1D"), # Toggle command
    "pump1_on": bytes.fromhex("1A 01 20 10 3C A1 10 A1 00 00 08 08 00 C0 00 62 00 C1 21 67 7D 1D"), # Wir wissen dass dies funktioniert!
    "pump1_off": bytes.fromhex("1A 01 20 10 3C A1 10 A1 00 00 08 11 00 C0 00 62 00 FA C5 7B A7 1D"), # Wahrscheinlich OFF
    "temp_up": bytes.fromhex("1A 01 20 10 3C A1 10 A1 00 00 80 80 00 C0 00 64 00 43 0E D6 5B 1D"),
    "temp_down": bytes.fromhex("1A 01 20 10 3C A1 10 A1 00 00 80 99 00 C0 00 62 00 6A 01 19 85 1D"),
    "heat_toggle": bytes.fromhex("1A 01 20 10 3C A1 10 A1 00 00 40 59 00 C0 00 56 80 16 E8 14 CE 1D")
}

SENSORS = {
    "water_temp": {"name": "Wasser Temperatur", "device_class": "temperature", "unit_of_measurement": "°C", "type": "sensor"},
    "setpoint": {"name": "Soll Temperatur", "device_class": "temperature", "unit_of_measurement": "°C", "type": "sensor"},
    "zirkulation": {"name": "Zirkulationspumpe", "type": "binary_sensor", "icon": "mdi:water-sync"},
    "heater": {"name": "Heizung Status", "type": "binary_sensor", "icon": "mdi:heating-coil"},
    "light": {"name": "Licht Status", "type": "binary_sensor", "icon": "mdi:lightbulb"},
    "pump1": {"name": "Pumpe 1 Status", "type": "binary_sensor", "icon": "mdi:pump"},
    "pump1_high": {"name": "Pumpe 1 High Status", "type": "binary_sensor", "icon": "mdi:pump"}
}

BUTTONS = {
    "light_toggle": {"name": "Licht Umschalten", "icon": "mdi:lightbulb-multiple"},
    "heat_toggle": {"name": "Heizung Ein/Aus", "icon": "mdi:fire"},
}

SELECTS = {
    "pump": {"name": "Pumpe Geschwindigkeit", "icon": "mdi:pump", "options": ["OFF", "LOW", "HIGH"]}
}

NUMBERS = {
    "setpoint": {"name": "Ziel-Temperatur", "icon": "mdi:thermometer", "min": 15, "max": 40, "step": 1, "unit_of_measurement": "°C"}
}

def publish_discovery(client):
    for sensor_id, cfg in SENSORS.items():
        topic = f"{HA_PREFIX}/{cfg['type']}/joyonway_p25b37/{sensor_id}/config"
        payload = {
            "name": cfg['name'],
            "state_topic": f"{MQTT_BASE_TOPIC}/state",
            "unique_id": f"joyonway_p25b37_{sensor_id}",
            "device": DEVICE_INFO,
            "value_template": f"{{{{ value_json.{sensor_id} }}}}"
        }
        if "device_class" in cfg: payload["device_class"] = cfg["device_class"]
        if "unit_of_measurement" in cfg: payload["unit_of_measurement"] = cfg["unit_of_measurement"]
        if "icon" in cfg: payload["icon"] = cfg["icon"]
        client.publish(topic, json.dumps(payload), retain=True)

    for btn_id, cfg in BUTTONS.items():
        topic = f"{HA_PREFIX}/button/joyonway_p25b37/{btn_id}/config"
        payload = {
            "name": cfg['name'],
            "command_topic": f"{MQTT_BASE_TOPIC}/button/{btn_id}",
            "unique_id": f"joyonway_p25b37_{btn_id}",
            "device": DEVICE_INFO,
            "icon": cfg["icon"]
        }
        client.publish(topic, json.dumps(payload), retain=True)

    for sel_id, cfg in SELECTS.items():
        topic = f"{HA_PREFIX}/select/joyonway_p25b37/{sel_id}/config"
        payload = {
            "name": cfg['name'],
            "command_topic": f"{MQTT_BASE_TOPIC}/{sel_id}/set",
            "state_topic": f"{MQTT_BASE_TOPIC}/state",
            "value_template": f"{{{{ value_json.{sel_id}_state }}}}",
            "options": cfg['options'],
            "unique_id": f"joyonway_p25b37_{sel_id}",
            "device": DEVICE_INFO,
            "icon": cfg["icon"]
        }
        client.publish(topic, json.dumps(payload), retain=True)

    for num_id, cfg in NUMBERS.items():
        topic = f"{HA_PREFIX}/number/joyonway_p25b37/{num_id}/config"
        payload = {
            "name": cfg['name'],
            "command_topic": f"{MQTT_BASE_TOPIC}/{num_id}/set",
            "state_topic": f"{MQTT_BASE_TOPIC}/state",
            "value_template": f"{{{{ value_json.{num_id} }}}}",
            "min": cfg["min"],
            "max": cfg["max"],
            "step": cfg["step"],
            "unique_id": f"joyonway_p25b37_{num_id}",
            "device": DEVICE_INFO,
            "icon": cfg["icon"],
            "unit_of_measurement": cfg["unit_of_measurement"]
        }
        client.publish(topic, json.dumps(payload), retain=True)

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("Erfolgreich mit MQTT Broker verbunden.")
        publish_discovery(client)
        client.subscribe(f"{MQTT_BASE_TOPIC}/button/+")
        client.subscribe(f"{MQTT_BASE_TOPIC}/pump/set")
        client.subscribe(f"{MQTT_BASE_TOPIC}/setpoint/set")
    else:
        print(f"Fehler bei MQTT Verbindung: {reason_code}")

import threading


def crc32_mpeg2(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= (byte << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc

def build_command(cmd_type: str, current_setpoint_c: float) -> bytes:
    global counter_light, counter_heat
    if current_setpoint_c < 10:
        current_setpoint_c = 37.0
    setpoint_f = int(round(current_setpoint_c * 9/5 + 32))
    
    if cmd_type == "light_toggle":
        counter_light = 0x80 + ((counter_light - 0x80 + 1) % 8)
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 40 40 00 C0 00") + bytes([setpoint_f, counter_light])
    elif cmd_type == "pump1_low":
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 08 08 00 C0 00") + bytes([setpoint_f, 0x00])
    elif cmd_type == "pump1_high":
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 08 14 00 C0 00") + bytes([setpoint_f, 0x00])
    elif cmd_type == "pump1_off":
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 08 11 00 C0 00") + bytes([setpoint_f, 0x00])
    elif cmd_type == "heat_toggle":
        counter_heat = 0x80 + ((counter_heat - 0x80 + 1) % 8)
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 40 59 00 C0 00") + bytes([setpoint_f, counter_heat])
    elif cmd_type == "temp_up":
        target_f = min(104, setpoint_f + 1)
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 80 80 00 C0 00") + bytes([target_f, 0x00])
    elif cmd_type.startswith("temp_set_"):
        parts = cmd_type.split("_")
        target_f = int(parts[2])
        direction = parts[3]
        if direction == "up":
            base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 80 80 00 C0 00") + bytes([target_f, 0x00])
        else:
            base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 80 99 00 C0 00") + bytes([target_f, 0x00])
    elif cmd_type == "temp_down":
        target_f = max(50, setpoint_f - 1)
        base = bytes.fromhex("01 20 10 3C A1 10 A1 00 00 80 99 00 C0 00") + bytes([target_f, 0x00])
    else:
        return b""

    swapped = bytearray()
    for i in range(0, len(base), 4):
        word = base[i:i+4]
        swapped.extend(word[::-1])
    
    crc_val = crc32_mpeg2(swapped)
    crc_bytes = crc_val.to_bytes(4, 'little')
    
    return b"\x1A" + base + crc_bytes + b"\x1D"

def send_rs485_cmd(cmd_name):
    global state
    packet = build_command(cmd_name, state.get("setpoint", 37.0))
    if not packet:
        if cmd_name in COMMANDS:
            packet = COMMANDS[cmd_name]
        else:
            print(f"Unknown command: {cmd_name}")
            return
            
    print(f"Starte Flood für Befehl: {cmd_name}")
    def flood():
        try:
            temp_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_s.settimeout(5.0)
            temp_s.connect((SOCAT_HOST, SOCAT_PORT))
            temp_s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            start = time.time()
            sent = 0
            while time.time() - start < 3.0:
                temp_s.send(packet)
                sent += 1
                
                time.sleep(0.05)
            temp_s.close()
            print(f"Flood beendet: {sent} Pakete gesendet für {cmd_name}")
        except Exception as e:
            print(f"Fehler beim Flooding: {e}")
            
    threading.Thread(target=flood, daemon=True).start()

def process_setpoint(target_val):
    global last_setpoint_f
    target_c = float(target_val)
    target_f = int(round(target_c * 9/5 + 32))
    
    # Send absolute setpoint directly using the target_f!
    if target_f > last_setpoint_f:
        send_rs485_cmd(f"temp_set_{target_f}_up")
    elif target_f < last_setpoint_f:
        send_rs485_cmd(f"temp_set_{target_f}_down")
    else:
        pass # Already at target

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8').upper()
    print(f"MQTT Empfangen: {topic} -> {payload}")
    
    if topic == f"{MQTT_BASE_TOPIC}/pump/set":
        if payload == "LOW": send_rs485_cmd("pump1_low")
        elif payload == "HIGH": send_rs485_cmd("pump1_high")
        else: send_rs485_cmd("pump1_off")
    elif topic == f"{MQTT_BASE_TOPIC}/setpoint/set":
        threading.Thread(target=process_setpoint, args=(payload,), daemon=True).start()
    elif topic.startswith(f"{MQTT_BASE_TOPIC}/button/"):
        btn = topic.split("/")[-1]
        if btn == "light_toggle": send_rs485_cmd("light_toggle")
        elif btn == "heat_toggle": send_rs485_cmd("heat_toggle")

def mqtt_thread():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"Konnte nicht zu MQTT verbinden: {e}")




def f_to_c(f):
    return round((f - 32) * 5.0/9.0, 1)

def f_to_c_int(f):
    return int(round((f - 32) * 5.0/9.0))

def unescape_payload(data):
    res = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x1B and i + 1 < len(data):
            nxt = data[i+1]
            if nxt == 0x11:
                res.append(0x1A)
                i += 2
                continue
            elif nxt == 0x13:
                res.append(0x1B)
                i += 2
                continue
            elif nxt == 0x14:
                res.append(0x1C)
                i += 2
                continue
            elif nxt == 0x15:
                res.append(0x1D)
                i += 2
                continue
        res.append(b)
        i += 1
    return bytes(res)




def f_to_c(f):
    return round((f - 32) * 5.0/9.0, 1)

def f_to_c_int(f):
    return int(round((f - 32) * 5.0/9.0))

def unescape_payload(data):
    res = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x1B and i + 1 < len(data):
            nxt = data[i+1]
            if nxt == 0x11:
                res.append(0x1A)
                i += 2
                continue
            elif nxt == 0x13:
                res.append(0x1B)
                i += 2
                continue
            elif nxt == 0x14:
                res.append(0x1C)
                i += 2
                continue
            elif nxt == 0x15:
                res.append(0x1D)
                i += 2
                continue
        res.append(b)
        i += 1
    return bytes(res)

state = {'setpoint': 37.0}
counter_light = 0x80
counter_heat = 0x80
target_setpoint = None
def main():
    global state
    t = threading.Thread(target=mqtt_thread, daemon=True)
    t.start()

    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10.0)
            s.connect((SOCAT_HOST, SOCAT_PORT))
            print("Verbunden mit RS485 Stream (Lese Modus).")
            
            buffer = b''
            last_publish = 0
            
            # Helper mqtt client for publishing state
            pub_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            pub_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            while True:
                chunk = s.recv(1024)
                if not chunk: break
                buffer += chunk
                
                while b'\x1d' in buffer:
                    packet_raw, buffer = buffer.split(b'\x1d', 1)
                    packet_raw += b'\x1d'
                    
                    # Handled by thread instead.
                    
                    start_idx = packet_raw.find(b'\x1a\xff')
                    if start_idx != -1:
                        packet = packet_raw[start_idx:]
                        packet = unescape_payload(packet)
                        if len(packet) >= 20:
                            packet = packet[:20]
                            
                            temp_f = packet[9]
                            setpoint_f = packet[16]
                            global last_setpoint_f
                            last_setpoint_f = setpoint_f
                            if setpoint_f < 40 or setpoint_f > 110:
                                continue  # Invalid or truncated packet
                                
                            pump_byte = packet[12]
                            heat_byte = packet[14]
                            light_byte = packet[17]
                            
                            p1_low = bool(pump_byte & 0x02)
                            p1_high = bool(pump_byte & 0x04)
                            pump_state = "HIGH" if p1_high else ("LOW" if p1_low else "OFF")
                            
                            state = {
                                "water_temp": f_to_c(temp_f),
                                "setpoint": f_to_c_int(setpoint_f),
                                "pump1": "ON" if p1_low else "OFF",
                                "pump1_high": "ON" if p1_high else "OFF",
                                "pump_state": pump_state,
                                "zirkulation": "ON" if (heat_byte & 0x08) else "OFF",
                                "heater": "ON" if (heat_byte & 0x10) else "OFF",
                                "light": "ON" if (light_byte > 0 and light_byte < 0x80) else "OFF"
                            }
                            
                            now = time.time()
                            if now - last_publish >= 5.0:
                                pub_client.publish(f"{MQTT_BASE_TOPIC}/state", json.dumps(state))
                                print(f"[{time.strftime('%H:%M:%S')}] MQTT Status Update: {state}")
                                last_publish = now
                            
                            pass
                                
        except socket.timeout:
            print("Timeout, reconnecting...")
            time.sleep(2)
        except Exception as e:
            print(f"Socket Fehler: {e}")
            time.sleep(5)
            
if __name__ == "__main__":
    main()
