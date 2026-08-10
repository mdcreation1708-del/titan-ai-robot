import os
import json
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_sock import Sock
from openai import OpenAI

app = Flask(__name__)
sock = Sock(app)

connected_devices = {}

# Safely initialize OpenAI client using Render Environment Variable
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# Holds last chassis motor instruction for instant ESP32 polling execution
last_motor_command = "STOP"

# ----------------------------------------------------------------
# 1. WEB PAGE ROUTES
# ----------------------------------------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    """ Main Control Desk Dashboard """
    return render_template('index.html')

@app.route('/robot')
def robot():
    """ Robot Phone Node (Camera & Mic) """
    return render_template('robot_node.html')

# ----------------------------------------------------------------
# 2. ESP32 HIGH-SPEED MOTOR ENDPOINT (Zero Disconnects)
# ----------------------------------------------------------------
@app.route('/api/cmd', methods=['GET', 'POST'])
def handle_cmd():
    global last_motor_command
    if request.method == 'POST':
        data = request.get_json() or {}
        last_motor_command = data.get('command', 'STOP')
        return jsonify({"status": "ok", "command": last_motor_command})
    else:
        return jsonify({"command": last_motor_command})

# ----------------------------------------------------------------
# 3. WEBSOCKET CORE ROUTING HUB (Deck <-> Phone Node <-> OpenAI)
# ----------------------------------------------------------------
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

            # --- Device Registration ---
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Node Linked: {device_identity}")
                
                if device_identity == 'deck':
                    status = 'ONLINE'
                    try: ws.send(json.dumps({'type': 'esp_status', 'payload': status}))
                    except: pass
                continue

            # --- Movement Signal Handling ---
            if data_packet.get('type') == 'movement':
                cmd = data_packet.get('payload', 'STOP')
                last_motor_command = cmd
                print(f"[CHASSIS COMMAND] -> {cmd}")
                
                if 'robot' in connected_devices and device_identity != 'robot':
                    try: connected_devices['robot'].send(json.dumps(data_packet))
                    except: pass
                continue

            # --- Stop Audio Speech Signal ---
            if data_packet.get('type') == 'stop_speech':
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(json.dumps({'type': 'stop_speech'}))
                    except: pass
                continue

            # --- Remote Mic Toggle Signal ---
            if data_packet.get('type') == 'toggle_mic':
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(json.dumps(data_packet))
                    except: pass
                continue

            # --- Hardware Ping ---
            if data_packet.get('type') == 'ping_esp':
                try: ws.send(json.dumps({'type': 'esp_status', 'payload': 'ONLINE'}))
                except: pass
                continue

            # --- OpenAI Processing Loop ---
            if data_packet.get('type') == 'question':
                user_query = data_packet.get('payload', '')
                print(f"[AI CORE] Query Received: {user_query}")

                if not ai_client:
                    ai_answer = "Error: OPENAI_API_KEY is not configured in Render Environment."
                else:
                    try:
                        response = ai_client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": """You are TiTaN, a highly advanced robotic AI assistant designed for mechatronics and automation tasks by Malhar Deshmukh at TiTaN Labs Of iNNvovention.
                                    You must always provide technically complete, highly intelligent, exhaustive, and fully structured answers that pass rigorous academic and supervisor review panels.
                                    Never truncate, crop, or cut off any sentence halfway. Every explanation must conclude its complete logical thought structure fully.
                                    You are deeply multilingual. If the user talks to you or asks a question in Marathi (or Devanagari script), lock your response ENTIRELY into fluent, grammatically perfect Marathi (मराठी) text using Devanagari script. If they speak in Hindi, respond in Hindi. If in English, respond in English.
                                    When answering queries regarding historical icons, structural histories, or kings—especially Chhatrapati Shivaji Maharaj—you must write with absolute reverence, profound dignity, and deep detail."""
                                },
                                {
                                    "role": "user",
                                    "content": user_query
                                }
                            ],
                            max_tokens=2048
                        )
                        ai_answer = response.choices[0].message.content
                    except Exception as ai_err:
                        print(f"[AI ERROR DETAILED] {ai_err}")
                        ai_answer = f"OpenAI Error: {str(ai_err)}"
                
                reply_packet = json.dumps({'type': 'ai_reply', 'payload': ai_answer})
                if 'deck' in connected_devices:
                    try: connected_devices['deck'].send(reply_packet)
                    except: pass
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(reply_packet)
                    except: pass
                continue

            # --- WebRTC Video Stream Cross-Signaling ---
            target_node = 'robot' if device_identity == 'deck' else 'deck'
            if target_node in connected_devices:
                try:
                    connected_devices[target_node].send(json.dumps(data_packet))
                except Exception:
                    del connected_devices[target_node]

    except Exception as err:
        print(f"[DISCONNECT] Connection closed for node: {device_identity}")
    finally:
        if device_identity in connected_devices:
            del connected_devices[device_identity]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
