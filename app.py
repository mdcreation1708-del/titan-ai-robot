import os
import json
from flask import Flask, render_template
from flask_sock import Sock
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

app = Flask(__name__)
sock = Sock(app)

connected_devices = {}

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
    deployment_port = int(os.environ.get('PORT', 5000))
    print(f"[BOOT] Initializing Production WebSocket Server on port {deployment_port}...")
    
    # Fire up the production WebSocket server
    http_server = WSGIServer(('0.0.0.0', deployment_port), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
