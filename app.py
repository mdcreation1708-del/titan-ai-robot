import os
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'titan_secret_key_1708'

# Initialize SocketIO with eventlet for high-performance production async tasks
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robot')
def robot():
    return render_template('robot_node.html')

# Listen for direction commands from the dashboard and broadcast them out
@socketio.on('chassis_command')
def handle_chassis(data):
    emit('robot_receive', data, broadcast=True)

# Listen for text/chat input from the dashboard and broadcast them out
@socketio.on('terminal_message')
def handle_terminal(data):
    emit('robot_receive', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
