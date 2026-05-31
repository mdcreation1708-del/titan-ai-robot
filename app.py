import os
from flask import Flask, request, jsonify, render_template, Response
from google import genai
from google.genai import types

app = Flask(__name__)

# --- SECURE API INITIALIZATION ---
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# --- GLOBAL MEMORY STORAGE LAYER ---
current_command = "idle"
esp_wifi_list = ["Loading networks... Please trigger scan from robot."]
esp_connection_status = "Disconnected"
latest_frame = None  # FIXED: Changed // to # for valid Python syntax

@app.route('/')
def index():
    """Serves the main integrated central control room dashboard."""
    return render_template('index.html')


# --- MODULE 1: ROVER MOTOR ACTUATION ROUTING ---

@app.route('/send_command', methods=['POST'])
def send_command():
    """Receives direction overrides from your custom App or web dashboard."""
    global current_command
    current_command = request.form.get('direction', 'idle')
    return f"Movement state successfully altered: {current_command}", 200

@app.route('/get_command', methods=['GET'])
def get_command():
    """Polled by the ESP32-S3 every 100-200ms to fetch active driving directives."""
    global current_command
    return current_command


# --- MODULE 2: LIVE MJPEG VIDEO STREAMING ---

@app.route('/upload_frame', methods=['POST'])
def upload_frame():
    """Receives raw binary JPEG frame buffers directly from the OV3660 camera."""
    global latest_frame
    latest_frame = request.data
    return "Frame Cached", 200

def generate_video_stream():
    """Continually yields frames matching multipart MIME specifications."""
    global latest_frame
    while True:
        if latest_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    """Feeds the MJPEG dynamic imagery matrix straight to the dashboard image tag."""
    return Response(generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# --- MODULE 3: GEMINI AI CORE INTEGRATION ---

@app.route('/ask_chat', methods=['POST'])
def ask_chat():
    """Handles text query actions regarding Mechatronics and Maratha History."""
    try:
        user_message = request.form.get('message', '')
        if not user_message:
            return jsonify({"status": "error", "message": "Empty query received"}), 400

        system_instruction = (
            "You are the central brain of TiTaN Ai RoBoT v3.0. You handle advanced mechatronics engineering "
            "tasks, circuit debugging, and answer historical queries regarding the Maratha Empire "
            "(Chhatrapati Shivaji Maharaj / Chhatrapati Sambhaji Maharaj). "
            "Keep answers engaging, authoritative, and strictly under 80 words."
        )

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction, 
                max_output_tokens=250
            )
        )
        return jsonify({"status": "success", "reply": response.text})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- MODULE 4: WI-FI SYNCHRONIZATION NETWORKS ---

@app.route('/update_esp_networks', methods=['POST'])
def update_esp_networks():
    """Called by the ESP32 to push its physically scanned local router arrays up to the cloud."""
    global esp_wifi_list, esp_connection_status
    data = request.get_json(force=True)
    esp_wifi_list = data.get("networks", [])
    esp_connection_status = "Online (Ready to Connect)"
    return jsonify({"status": "success"}), 200

@app.route('/get_wifi_list', methods=['GET'])
def get_wifi_list():
    """Polled by your dashboard JavaScript loop to show current connectivity states."""
    global esp_wifi_list, esp_connection_status
    return jsonify({
        "status": esp_connection_status,
        "networks": esp_wifi_list
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
