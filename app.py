import os
import json
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_sock import Sock
from google import genai
from google.genai import types

app = Flask(__name__)
sock = Sock(app)

connected_devices = {}
ai_client = genai.Client(api_key="AQ.Ab8RN6KZpYeF4n86cwzgJJffYagaZiZlxlcB9airDlhCIgjikg")

# Global variable to hold last motor command for HTTP polling backup
last_motor_command = "STOP"

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robot')
def robot():
    return render_template('robot_node.html')

# --- DIRECT HTTP FALLBACK FOR ESP32 (GUARANTEED NO DISCONNECTS) ---
@app.route('/api/cmd', methods=['GET', 'POST'])
def handle_cmd():
    global last_motor_command
    if request.method == 'POST':
        data = request.get_json() or {}
        last_motor_command = data.get('command', 'STOP')
        return jsonify({"status": "ok", "command": last_motor_command})
    else:
        # ESP32 polls this endpoint
        cmd = last_motor_command
        return jsonify({"command": cmd})

@sock.route('/core')
def core_routing_hub(ws):
    global last_motor_command
    device_identity = None
    try:
        while True:
            raw_payload = ws.receive()
            if raw_payload is None:
                break
            
            try:
                data_packet = json.loads(raw_payload)
            except Exception:
                continue

            # Registration
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Linked: {device_identity}")
                
                if device_identity == 'esp32' and 'deck' in connected_devices:
                    try: connected_devices['deck'].send(json.dumps({'type': 'esp_status', 'payload': 'ONLINE'}))
                    except: pass
                
                if device_identity == 'deck':
                    status = 'ONLINE' if 'esp32' in connected_devices else 'OFFLINE'
                    try: ws.send(json.dumps({'type': 'esp_status', 'payload': status}))
                    except: pass
                continue

            # Movement commands from Deck / Robot
            if data_packet.get('type') == 'movement':
                cmd = data_packet.get('payload', 'STOP')
                last_motor_command = cmd # Save for HTTP backup
                print(f"[CHASSIS COMMAND] -> {cmd}")
                
                if 'esp32' in connected_devices:
                    try: connected_devices['esp32'].send(json.dumps(data_packet))
                    except: pass
                continue

            # Ping
            if data_packet.get('type') == 'ping_esp':
                status = 'ONLINE' if 'esp32' in connected_devices else 'OFFLINE'
                try: ws.send(json.dumps({'type': 'esp_status', 'payload': status}))
                except: pass
                continue

            # AI Question
            if data_packet.get('type') == 'question':
                user_query = data_packet.get('payload', '')
                print(f"[AI CORE] Query: {user_query}")
                try:
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=user_query,
                        config=types.GenerateContentConfig(
                            system_instruction="""You are TiTaN, a highly advanced robotic AI assistant designed for mechatronics and automation tasks by Malhar Deshmukh at TiTaN Labs Of iNNvovention.""",
                            max_output_tokens=2048
                        )
                    )
                    ai_answer = response.text
                except Exception as ai_err:
                    ai_answer = "Core processing loop error."
                
                reply_packet = json.dumps({'type': 'ai_reply', 'payload': ai_answer})
                if 'deck' in connected_devices:
                    try: connected_devices['deck'].send(reply_packet)
                    except: pass
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(reply_packet)
                    except: pass
                continue

    except Exception as err:
        print(f"[DISCONNECT] Node closed: {device_identity}")
    finally:
        if device_identity in connected_devices:
            del connected_devices[device_identity]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
