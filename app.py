import os
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'titan_secret_key_1708'

# Configure SocketIO to run perfectly on gevent architecture
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robot')
def robot():
    return render_template('robot_node.html')

@socketio.on('chassis_command')
def handle_chassis(data):
    emit('robot_receive', data, broadcast=True)

@socketio.on('terminal_message')
def handle_terminal(data):
    emit('robot_receive', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"[BOOT] TiTaN production server spinning up on port {port}...")
    
    # Create the specialized gevent server container
    server = WSGIServer(('0.0.0.0', port), app, handler_class=WebSocketHandler)
    server.serve_forever()
