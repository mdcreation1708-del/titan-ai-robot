import os
import json
from flask import Flask, render_template, send_from_directory
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)

connected_devices = {}

# Fixes the logo issue by serving favicon.ico straight to Chrome
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
            
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Device linked successfully: {device_identity}")
                continue
            
            target_node = 'deck' if device_identity == 'robot' else 'robot'
            
            if target_node in connected_devices:
                try:
                    connected_devices[target_node].send(json.dumps(data_packet))
                except Exception:
                    del connected_devices[target_node]
                    
    except Exception as error_context:
        print(f"[DISCONNECT] Connection closed for {device_identity}")
        
    finally:
        if device_identity in connected_devices:
            del connected_devices[device_identity]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
