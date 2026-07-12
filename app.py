import os
import json
from flask import Flask, render_template, send_from_directory
from flask_sock import Sock
from google import genai
from google.genai import types

app = Flask(__name__)
sock = Sock(app)

# Active WebSocket device mapping array
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
            
            # Handshake device identifier registration mapping
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Device linked successfully: {device_identity}")
                continue
            
            # Conversational AI Query Interface Path
            if data_packet.get('type') == 'question':
                user_query = data_packet.get('payload', '')
                print(f"[AI CORE] Processing conversational query: {user_query}")
                try:
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=user_query,
                        config=types.GenerateContentConfig(
                            system_instruction="""You are TiTaN, a highly advanced robotic AI assistant designed for mechatronics and automation tasks by Malhar Deshmukh at TiTaN Labs Of iNNvovention.
                            You must always provide technically complete, highly intelligent, exhaustive, and fully structured answers that pass rigorous academic and supervisor review panels.
                            Never truncate, crop, or cut off any sentence halfway. Every explanation must conclude its complete logical thought structure fully.
                            You are deeply multilingual. If the user talks to you or asks a question in Marathi (or requests 'tell marathi'), lock your processing entirely into fluent, grammatically perfect Marathi text. If they speak in Hindi, respond professionally in Hindi. If they speak in English, respond in English.
                            When answering queries regarding historical icons, structural histories, or kings—especially the legendary Chhatrapati Shivaji Maharaj—you must write with absolute reverence, profound dignity, and deep, thorough detail.""",
                            max_output_tokens=3072
                        )
                    )
                    ai_answer = response.text
                except Exception as ai_err:
                    print(f"[AI ERROR] Failed to generate response: {ai_err}")
                    ai_answer = "System variance caught in core processing pipeline execution loop."
                
                reply_packet = json.dumps({'type': 'ai_reply', 'payload': ai_answer})
                # Broadcast back to control display layers instantly
                if 'deck' in connected_devices:
                    try: connected_devices['deck'].send(reply_packet)
                    except: pass
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(reply_packet)
                    except: pass
                continue
            
            # FIXED INTERNAL ROUTING PIPELINE
            # If data comes from deck -> send to robot. If data comes from robot -> send to deck.
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
