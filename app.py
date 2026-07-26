import os
import json
from flask import Flask, render_template, send_from_directory
from flask_sock import Sock
from google import genai
from google.genai import types

app = Flask(__name__)
sock = Sock(app)

connected_devices = {}
ai_client = genai.Client(api_key="AQ.Ab8RN6KZpYeF4n86cwzgJJffYagaZiZlxlcB9airDlhCIgjikg")

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robot')
def robot():
    return render_template('robot_node.html')

@sock.route('/core')
def core_routing_hub(ws):
    device_identity = None
    try:
        while True:
            raw_payload = ws.receive()
            if not raw_payload:
                break
            data_packet = json.loads(raw_payload)
            
            # Device Registration
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Device linked successfully: {device_identity}")
                
                if device_identity == 'esp32' and 'deck' in connected_devices:
                    try:
                        connected_devices['deck'].send(json.dumps({'type': 'esp_status', 'payload': 'ONLINE'}))
                    except: pass
                
                if device_identity == 'deck':
                    status = 'ONLINE' if 'esp32' in connected_devices else 'OFFLINE'
                    ws.send(json.dumps({'type': 'esp_status', 'payload': status}))
                continue
            
            # ESP Ping Handler
            if data_packet.get('type') == 'ping_esp':
                status = 'ONLINE' if 'esp32' in connected_devices else 'OFFLINE'
                ws.send(json.dumps({'type': 'esp_status', 'payload': status}))
                continue

            # Stop Audio Speech Signal
            if data_packet.get('type') == 'stop_speech':
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(json.dumps({'type': 'stop_speech'}))
                    except: pass
                continue

            # AI Query Processing Loop
            if data_packet.get('type') == 'question':
                user_query = data_packet.get('payload', '')
                print(f"[AI CORE] Processing query: {user_query}")
                try:
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=user_query,
                        config=types.GenerateContentConfig(
                            system_instruction="""You are TiTaN, a highly advanced robotic AI assistant designed for mechatronics and automation tasks by Malhar Deshmukh at TiTaN Labs Of iNNvovention.
                            You must always provide technically complete, highly intelligent, exhaustive, and fully structured answers that pass rigorous academic and supervisor review panels.
                            Never truncate, crop, or cut off any sentence halfway. Every explanation must conclude its complete logical thought structure fully.
                            You are deeply multilingual. If the user talks to you or asks a question in Marathi (or Devanagari script), lock your response ENTIRELY into fluent, grammatically perfect Marathi (मराठी) text using Devanagari script. If they speak in Hindi, respond in Hindi. If in English, respond in English.
                            When answering queries regarding historical icons, structural histories, or kings—especially Chhatrapati Shivaji Maharaj—you must write with absolute reverence, profound dignity, and deep detail.""",
                            max_output_tokens=3072
                        )
                    )
                    ai_answer = response.text
                except Exception as ai_err:
                    print(f"[AI ERROR] Failed to generate response: {ai_err}")
                    ai_answer = "System variance caught in core processing pipeline execution loop."
                
                reply_packet = json.dumps({'type': 'ai_reply', 'payload': ai_answer})
                if 'deck' in connected_devices:
                    try: connected_devices['deck'].send(reply_packet)
                    except: pass
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(reply_packet)
                    except: pass
                continue
            
            # Standard Message Cross-Routing
            target_node = 'robot' if device_identity == 'deck' else 'deck'
            if target_node in connected_devices:
                try:
                    connected_devices[target_node].send(json.dumps(data_packet))
                except Exception:
                    del connected_devices[target_node]
                    
    except Exception as error_context:
        print(f"[DISCONNECT] Connection closed for: {device_identity}")
    finally:
        if device_identity in connected_devices:
            del connected_devices[device_identity]
        if device_identity == 'esp32' and 'deck' in connected_devices:
            try:
                connected_devices['deck'].send(json.dumps({'type': 'esp_status', 'payload': 'OFFLINE'}))
            except: pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
