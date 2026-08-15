import os
import json
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_sock import Sock
from openai import OpenAI

app = Flask(__name__)
sock = Sock(app)

connected_devices = {}
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

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

@app.route('/api/cmd', methods=['GET', 'POST'])
def handle_cmd():
    global last_motor_command
    if request.method == 'POST':
        data = request.get_json() or {}
        last_motor_command = data.get('command', 'STOP')
        return jsonify({"status": "ok", "command": last_motor_command})
    else:
        return jsonify({"command": last_motor_command})

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
                print(f"[CORE LINKED] Device registered: {device_identity}")
                
                # Notify deck if robot is already present or vice versa
                if device_identity == 'robot' and 'deck' in connected_devices:
                    try: connected_devices['deck'].send(json.dumps({'type': 'robot_online'}))
                    except: pass
                elif device_identity == 'deck' and 'robot' in connected_devices:
                    try: ws.send(json.dumps({'type': 'robot_online'}))
                    except: pass
                continue

            # Keep-alive Ping / Pong
            if data_packet.get('type') == 'ping_heartbeat':
                try: ws.send(json.dumps({'type': 'pong_heartbeat'}))
                except: pass
                continue

            # Hardware Ping
            if data_packet.get('type') == 'ping_esp':
                try: ws.send(json.dumps({'type': 'esp_status', 'payload': 'ONLINE'}))
                except: pass
                continue

            # Remote Mic Toggle from Dashboard
            if data_packet.get('type') == 'toggle_mic':
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(json.dumps(data_packet))
                    except: pass
                continue

            # Stop Speech
            if data_packet.get('type') == 'stop_speech':
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(json.dumps(data_packet))
                    except: pass
                continue

            # Movement Signal
            if data_packet.get('type') == 'movement':
                cmd = data_packet.get('payload', 'STOP')
                last_motor_command = cmd
                if 'robot' in connected_devices and device_identity != 'robot':
                    try: connected_devices['robot'].send(json.dumps(data_packet))
                    except: pass
                continue

            # OpenAI Processing
            if data_packet.get('type') == 'question':
                user_query = data_packet.get('payload', '')
                if not ai_client:
                    ai_answer = "API Key not configured."
                else:
                    try:
                        res = ai_client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system", 
                                    "content": "You are TiTaN, an industrial robotic AI assistant. If spoken to in Marathi, reply in Marathi Devanagari. If Hindi, reply in Hindi. Keep responses clear and concise."
                                },
                                {"role": "user", "content": user_query}
                            ],
                            max_tokens=2048
                        )
                        ai_answer = res.choices[0].message.content
                    except Exception as e:
                        ai_answer = f"Error: {str(e)}"

                reply_packet = json.dumps({'type': 'ai_reply', 'payload': ai_answer})
                if 'deck' in connected_devices:
                    try: connected_devices['deck'].send(reply_packet)
                    except: pass
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(reply_packet)
                    except: pass
                continue

            # WebRTC Signaling Relay (SDP Offer/Answer/Candidates)
            target = 'robot' if device_identity == 'deck' else 'deck'
            if target in connected_devices:
                try:
                    connected_devices[target].send(json.dumps(data_packet))
                except Exception:
                    del connected_devices[target]

    except Exception:
        pass
    finally:
        if device_identity in connected_devices:
            del connected_devices[device_identity]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
