import os
import json
from flask import Flask, render_template
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)

# Dictionary to maintain active cross-device WebSocket links
connected_devices = {}

@app.route('/')
def index():
    """Renders the main control panel dashboard for your laptop/secondary phone"""
    return render_template('index.html')

@app.route('/robot')
def robot():
    """Renders the hardware node interface for the old phone mounted on the robot"""
    return render_template('robot_node.html')

@sock.route('/core')
def core_routing_hub(ws):
    """
    Central real-time message router. Receives data packets from one device
    and immediately shoots them over to the other device.
    """
    device_identity = None
    try:
        while True:
            # Await data packet from the socket connection
            raw_payload = ws.receive()
            if not raw_payload:
                break
                
            data_packet = json.loads(raw_payload)
            
            # Device Registration Handshake Handler
            if 'register' in data_packet:
                device_identity = data_packet['register']
                connected_devices[device_identity] = ws
                print(f"[SYSTEM CORE] Device linked successfully: {device_identity}")
                continue
            
            # Matrix Router: Send the data packet to the opposite device node
            target_node = 'deck' if device_identity == 'robot' else 'robot'
            
            if target_node in connected_devices:
                try:
                    connected_devices[target_node].send(json.dumps(data_packet))
                except Exception:
                    # Clear dead connections gracefully if transmission fails
                    print(f"[SYSTEM WARNING] Failed transmission to {target_node}. Purging socket.")
                    del connected_devices[target_node]
                    
    except Exception as error_context:
        print(f"[DISCONNECT] Connection closed for {device_identity}: {error_context}")
        
    finally:
        # Clean up global dictionary records when a socket session terminates
        if device_identity in connected_devices:
            del connected_devices[device_identity]
            print(f"[SYSTEM CORE] Device removed from registry: {device_identity}")

if __name__ == '__main__':
    # Dynamically extract deployment port from environment variables for Render compatibility
    deployment_port = int(os.environ.get('PORT', 5000))
    
    # Run the server engine
    print(f"[BOOT] Initializing TiTaN Voice Core Server on port {deployment_port}...")
    app.run(host='0.0.0.0', port=deployment_port)
