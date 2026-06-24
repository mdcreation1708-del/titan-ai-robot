import os
import time
import threading
from flask import Flask, render_template, Response, jsonify
from flask_cors import CORS
import requests
import cv2
from gtts import gTTS

app = Flask(__name__)
CORS(app)

# ==================== 🛠️ TITAN CONFIGURATION LAYER ====================
ESP32_IP = "192.168.0.125"  # Your mandatory hardware node IP address
PHONE_STREAM_URL = "http://192.168.0.50:8080/video"  # ⚠️ Replace with your IP Webcam app stream link
# ======================================================================

# Global Automation State Flags
autonomous_mode = True  
current_status = "Titan System Online"

# 🔊 Asynchronous Voice Processing Engine (Non-blocking)
def speak(text):
    def run():
        try:
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save("response.mp3")
            # Platform-independent media execution switch
            os.system("mpg123 response.mp3 || afplay response.mp3 || start response.mp3")
        except Exception as e:
            print(f"Voice Engine Error: {e}")
    threading.Thread(target=run).start()

# 🚀 Wake-Word Activation Sequence
speak("Hello MD Sir. Hey Titan core system initialized and operational.")

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

# 🎥 Computer Vision Analysis Loop (Primary Autonomous Mode)
def generate_frames():
    global autonomous_mode, current_status
    
    # Connects directly to your smartphone's wireless network feed link
    cap = cv2.VideoCapture(PHONE_STREAM_URL) 
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            frame_width = frame.shape[1]
            frame_center = frame_width // 2

            if len(faces) == 0 and autonomous_mode:
                current_status = "[Hey Titan] Scanning for MD Sir..."
                send_hardware_command("stop")

            for (x, y, w, h) in faces:
                # Render tracking lock bounding box layer on dashboard layout
                cv2.rectangle(frame, (x, y), (x+w, y+h), (154, 255, 222), 2)
                cv2.putText(frame, "Lock: MD Sir", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (154, 255, 222), 2)
                
                box_center = x + (w // 2)
                
                if autonomous_mode:
                    # 1. Depth Mapping Estimation (Tracking your strides)
                    if w < 110:    # Box small = Target walking away, track forward
                        send_hardware_command("forward")
                    elif w > 190:  # Box oversized = Target too close, halt
                        send_hardware_command("stop")
                    else:
                        # 2. Angular Centering Logic (Steering matching)
                        if box_center < frame_center - 60:
                            send_hardware_command("left")
                        elif box_center > frame_center + 60:
                            send_hardware_command("right")
                        else:
                            send_hardware_command("stop")
                break 

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Dashboard Secondary Override Route Handlers
@app.route('/<action>')
def action_handler(action):
    global autonomous_mode
    if action in ["forward", "backward", "left", "right", "stop"]:
        autonomous_mode = False # Suspend auto-tracking on direct manual override input
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
