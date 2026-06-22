import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
import serial

app = Flask(__name__)
CORS(app)

# ==========================================
# 🧠 MULTILINGUAL TITAN AI INITIALIZATION
# ==========================================
client = genai.Client()

SYSTEM_RULES = (
    "You are the onboard intelligence core for the Titan AI Robot. "
    "You assist the engineer with hardware theory, code debugging, historical queries, and automation problems. "
    "You must accept input and respond fluently in English, Hindi (हिंदी), or Marathi (मराठी) "
    "matching the language the user speaks to you in. Keep technical facts direct and accurate."
)

# ==========================================
# 🔌 PHYSICAL MOTOR CONTROLLER LINK
# ==========================================
try:
    # Connects to your ESP32 via Bluetooth / USB COM port
    esp32_serial = serial.Serial(port='COM5', baudrate=115200, timeout=1)
    print("🚀 Connected to ESP32 Propulsion Core!")
except Exception as e:
    esp32_serial = None
    print(f"⚠️ Serial connection offline: {e}. Running in simulation mode.")

def send_hardware_command(command_char):
    if esp32_serial and esp32_serial.is_open:
        esp32_serial.write(command_char.encode())

# ==========================================
# 🌐 API ROUTING MATRIX
# ==========================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/ask-ai', methods=['GET'])
def handle_ai_query():
    user_prompt = request.args.get('prompt', '')
    if not user_prompt:
        return jsonify({"reply": "Input cannot be empty."})
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_RULES,
                temperature=0.3,
            )
        )
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"reply": f"AI Engine Timeout: {str(e)}"})

@app.route('/api/drive', methods=['GET'])
def handle_driving_signals():
    direction = request.args.get('cmd', 'S')
    send_hardware_command(direction)
    return jsonify({"status": f"Command {direction} received"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
