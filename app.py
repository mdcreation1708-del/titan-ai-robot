import os
import json
from flask import Flask, render_template, send_from_directory
from flask_sock import Sock
from google import genai
from google.genai import types

app = Flask(__name__)
sock = Sock(app)

# Track active client socket pipelines
connected_devices = {}

# Initialize GenAI Client with direct fallback authentication injection
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
            
            # Handle handshake node registration
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Device linked successfully: {device_identity}")
                continue
            
            # Intercept and process speech/text question payloads with AI Brain
            if data_packet.get('type') == 'question':
                user_query = data_packet.get('payload', '')
                print(f"[AI CORE] Processing conversational query: {user_query}")
                try:
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=user_query,
                        config=types.GenerateContentConfig(
                            system_instruction="""You are TiTaN, an advanced robotic AI assistant created by Malhar Deshmukh at TiTaN Labs Of iNNvovention. 
                            You are fully conversational and empathetic, talking to the user just like a human peer would. 
                            You are fully multilingual. If the user talks to you or asks a question in Marathi, answer cleanly in fluent Marathi. If they speak in Hindi, reply in Hindi. If they speak in English, reply in English. 
                            Keep your answers smart, crisp, very short (maximum 1-2 sentences), and highly conversational so they sound natural when spoken out loud by the voice module.""",
                            max_output_tokens=150
                        )
                    )
                    ai_answer = response.text
                except Exception as ai_err:
                    print(f"[AI ERROR] Failed to generate response: {ai_err}")
                    ai_answer = "System pipeline error. Unable to process text context."
                
                # Broadcast AI answer text down to both endpoints simultaneously
                reply_packet = json.dumps({'type': 'ai_reply', 'payload': ai_answer})
                if 'deck' in connected_devices:
                    try: connected_devices['deck'].send(reply_packet)
                    except: pass
                if 'robot' in connected_devices:
                    try: connected_devices['robot'].send(reply_packet)
                    except: pass
                continue
            
            # Standard signaling cross-relay between operator and chassis nodes
            target_node = 'deck' if device_identity == 'robot' else 'robot'
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
