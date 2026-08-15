import os
import json
import time
from flask import Flask, render_template, send_from_directory, request, jsonify, Response
from groq import Groq

app = Flask(__name__)

# Initialize free Groq AI client
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
ai_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

last_motor_command = "STOP"
latest_frame = None 
mic_state = False   

# ----------------------------------------------------------------
# 1. WEB PAGE ROUTES
# ----------------------------------------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robot')
def robot():
    return render_template('robot_node.html')

# ----------------------------------------------------------------
# 2. VIDEO STREAMING PIPELINE
# ----------------------------------------------------------------
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
        time.sleep(0.04)

@app.route('/video_stream')
def video_stream():
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ----------------------------------------------------------------
# 3. CHASSIS MOTOR ENDPOINT
# ----------------------------------------------------------------
@app.route('/api/cmd', methods=['GET', 'POST'])
def handle_cmd():
    global last_motor_command
    if request.method == 'POST':
        data = request.get_json() or {}
        last_motor_command = data.get('command', 'STOP')
        return jsonify({"status": "ok", "command": last_motor_command})
    else:
        return jsonify({"command": last_motor_command})

# ----------------------------------------------------------------
# 4. REMOTE MIC & FAST FREE AI PROCESSING (GROQ)
# ----------------------------------------------------------------
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
        return jsonify({"reply": "Groq API Key not configured in Render Environment."})

    try:
        response = ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """You are TiTaN, an advanced robotic AI assistant engineered for automation and mechatronics systems by Malhar Deshmukh at TiTaN Labs Of iNNvovention.
                    If spoken to in Marathi (or Devanagari script), reply completely in fluent, clean Marathi text in Devanagari script. If in Hindi, reply in Hindi. If in English, reply in English.
                    Keep responses direct, crisp, and conversational for audio speech output."""
                },
                {"role": "user", "content": user_query}
            ],
            max_tokens=512,
            temperature=0.6
        )
        ai_answer = response.choices[0].message.content
        return jsonify({"reply": ai_answer})
    except Exception as e:
        print(f"[AI ERROR] {e}")
        return jsonify({"reply": f"AI Engine Error: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
