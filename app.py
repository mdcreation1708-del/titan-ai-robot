import os
from flask import Flask, render_template, send_from_directory, request, jsonify, Response
from openai import OpenAI

app = Flask(__name__)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

last_motor_command = "STOP"
latest_frame = None  # Holds raw JPEG frame from phone camera
mic_state = False    # Remote mic state

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robot')
def robot():
    return render_template('robot_node.html')

# ---------------------------------------------------------
# 1. LIVE VIDEO STREAMING PIPELINE (Zero WebRTC Complexity)
# ---------------------------------------------------------
@app.route('/api/video_feed', methods=['POST'])
def upload_frame():
    global latest_frame
    latest_frame = request.data
    return jsonify({"status": "received"})

def generate_stream():
    global latest_frame
    while True:
        if latest_frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')

@app.route('/video_stream')
def video_stream():
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ---------------------------------------------------------
# 2. CHASSIS MOTOR API (Instant ESP32 Polling)
# ---------------------------------------------------------
@app.route('/api/cmd', methods=['GET', 'POST'])
def handle_cmd():
    global last_motor_command
    if request.method == 'POST':
        data = request.get_json() or {}
        last_motor_command = data.get('command', 'STOP')
        return jsonify({"status": "ok", "command": last_motor_command})
    else:
        return jsonify({"command": last_motor_command})

# ---------------------------------------------------------
# 3. REMOTE MIC & AI VOICE PROCESSING
# ---------------------------------------------------------
@app.route('/api/mic_status', methods=['GET', 'POST'])
def handle_mic():
    global mic_state
    if request.method == 'POST':
        data = request.get_json() or {}
        mic_state = data.get('active', False)
        return jsonify({"mic_active": mic_state})
    else:
        return jsonify({"mic_active": mic_state})

@app.route('/api/ask_ai', methods=['POST'])
def ask_ai():
    data = request.get_json() or {}
    user_query = data.get('query', '')

    if not ai_client:
        return jsonify({"reply": "OpenAI API Key not set."})

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are TiTaN, an industrial AI robotics assistant designed by Malhar Deshmukh at TiTaN Labs. If spoken to in Marathi, reply in Marathi Devanagari. If Hindi, reply in Hindi. Keep responses crisp and direct."
                },
                {"role": "user", "content": user_query}
            ],
            max_tokens=1024
        )
        answer = response.choices[0].message.content
        return jsonify({"reply": answer})
    except Exception as e:
        return jsonify({"reply": f"AI Engine Error: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
