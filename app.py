import os
import time
import threading
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
from gtts import gTTS

app = Flask(__name__)
CORS(app)

# ==================== 🛠️ TITAN CONFIGURATION LAYER ====================
ESP32_IP = "192.168.0.125"  # Your locked hardware IP address
# ======================================================================

autonomous_mode = True  
current_status = "Titan System Online"

# 🔊 Asynchronous Voice Processing Engine
def speak(text):
    def run():
        try:
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save("response.mp3")
            os.system("mpg123 response.mp3 || afplay response.mp3 || start response.mp3")
        except Exception as e:
            print(f"Voice Engine Error: {e}")
    threading.Thread(target=run).start()

# 🚀 Wake-Word Activation Sequence
speak("Hello MD Sir. Hey Titan core system initialized.")

# Signal Routing Middleware to Hardware Edge
def send_hardware_command(action):
    global current_status
    if action == "stop":
        current_status = "[Hey Titan] Target Point Locked"
    else:
        current_status = f"[Hey Titan] Executing Vector: {action}"
        
    try:
        url = f"http://{ESP32_IP}/{action}"
        requests.get(url, timeout=0.5)
    except:
        pass

@app.route('/')
def index():
    return render_template('index.html')

# Dashboard Secondary Override Route Handlers
@app.route('/<action>')
def action_handler(action):
    global autonomous_mode
    if action in ["forward", "backward", "left", "right", "stop"]:
        autonomous_mode = False 
        speak("Ok Boss I will Do")
        send_hardware_command(action)
        return jsonify(status="Manual Mode Engaged", action=action)
    return jsonify(status="Invalid Direction Vector")

@app.route('/reset_auto')
def reset_auto():
    global autonomous_mode
    autonomous_mode = True
    speak("Titan autonomous tracking re engaged")
    return jsonify(status="Auto Tracking Active")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
