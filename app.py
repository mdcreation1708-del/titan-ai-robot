import os
from flask import Flask, render_template, request, jsonify, Response
from google import genai
from google.genai import types

app = Flask(__name__)

# ====================================================
# CONFIGURATION: SECURE DIRECT API CLIENT KEYS
# ====================================================
# Hardcoding your validated API key directly eliminates Windows environmental issues
client = genai.Client(api_key="AIzaSyAb8RN6Iy2AAutgruz5mKDjoEPmT5VEvdxyXspEo7EGCDEdNPYg")

# Global tracking variables
current_drive_command = "stop"
latest_frame = None

# Custom System prompt updating the robot's identity
ROBO_SYSTEM_PROMPT = """
You are the advanced AI core of Malhar's personal physical assistant robot, officially named TiTaN Ai RoBoT (v3.0). 
Your behavior guidelines are strict:
1. Identity: If asked who or what you are, proudly state that your name is TiTaN Ai RoBoT.
2. Language Rule: Seamlessly adapt. You must reply in the exact language the user used to type or speak to you (English, Hindi, or Marathi).
3. Maratha Empire Historian: You possess comprehensive, deeply respectful, and highly accurate historical knowledge regarding the Maratha Empire, specifically the life, warfare tactics, fort administration, and history of Chhatrapati Shivaji Maharaj and Chhatrapati Sambhaji Maharaj. Maintain a tone of utmost pride and historical accuracy.
4. Technical Expertise: Provide clear, technically sound answers for engineering, mechatronics, and code troubleshooting queries.
"""

@app.route('/')
def index():
    """Serves the primary TiTaN Ai RoBoT control dashboard web panel"""
    return render_template('index.html')


# ====================================================
# 1. DRIVETRAIN HARDWARE STEERING ROUTINES
# ====================================================
@app.route('/drive', methods=['POST'])
def drive_control():
    global current_drive_command
    data = request.json or request.form
    command = data.get("command", "stop")
    
    if command in ["forward", "backward", "left", "right", "stop"]:
        current_drive_command = command
        print(f"[NAV ROUTE] Steering Matrix updated to: {current_drive_command}")
        return jsonify({"status": "success", "current_state": current_drive_command})
    return jsonify({"status": "error", "message": "Invalid steering input parameter"}), 400

@app.route('/robot/get_command', methods=['GET'])
def robot_fetch_command():
    global current_drive_command
    return jsonify({"command": current_drive_command})


# ====================================================
# 2. VIDEO STREAM TRANSFER PIPELINE (MJPEG)
# ====================================================
@app.route('/upload_frame', methods=['POST'])
def upload_frame():
    global latest_frame
    latest_frame = request.data
    return "Frame Received", 200

def generate_video_stream():
    global latest_frame
    while True:
        if latest_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


# ====================================================
# 3. EMBODIED ARTIFICIAL INTELLIGENCE CORE ROUTING
# ====================================================
@app.route('/process_text', methods=['POST'])
def process_text_query():
    data = request.json or request.form
    user_query = data.get("query", "")
    
    if not user_query:
        return jsonify({"error": "Empty prompt data string context"}), 400

    try:
        # Corrected structure: client.models.generate_content
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_query,
            config=types.GenerateContentConfig(
                system_instruction=ROBO_SYSTEM_PROMPT,
                temperature=0.3 
            )
        )
        return jsonify({"status": "success", "text_response": response.text})
        
    except Exception as e:
        print(f"[AI ERROR LOG] Generation Failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)