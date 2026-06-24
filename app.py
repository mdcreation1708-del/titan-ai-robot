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
ESP32_IP = "192.168.0.125"  
PHONE_STREAM_URL = "http://192.168.0.105:8080/video"  # ⚠️ Make sure this matches your phone's current IP!
# ======================================================================

autonomous_mode = True  
current_status = "Titan System Online"

def speak(text):
    def run():
        try:
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save("response.mp3")
            os.system("mpg123 response.mp3 || afplay response.mp3 || start response.mp3")
        except Exception as e:
            print(f"Voice Engine Error: {e}")
    threading.Thread(target=run).start()

speak("Hello MD Sir. Hey Titan core system initialized.")

def send_hardware_command(action):
    global current_status
    if action == "stop":
        current_status = "[Hey Titan] Target Locked"
    else:
        current_status = f"[Hey Titan] Executing: {action}"
    try:
        url = f"http://{ESP32_IP}/{action}"
        requests.get(url, timeout=0.5)
    except:
        pass

# 🔄 NEW: Local Network Proxy Route
@app.route('/phone_proxy')
def phone_proxy():
    """Proxies the phone's unsecure HTTP stream through the server to bypass browser blocks."""
    try:
        req = requests.get(PHONE_STREAM_URL, stream=True, timeout=5)
        return Response(req.iter_content(chunk_size=1024), content_type=req.headers.get('content-type'))
    except Exception as e:
        return f"Could not connect to phone stream: {e}", 500

def generate_frames():
    global autonomous_mode, current_status
    
    # OpenCV now analyzes the secure internal proxy route instead of the raw local link!
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
                cv2.rectangle(frame, (x, y), (x+w, y+h), (154, 255, 222), 2)
                cv2.putText(frame, "Lock: MD Sir", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (154, 255, 222), 2)
                
                box_center = x + (w // 2)
                
                if autonomous_mode:
                    if w < 110:    
                        send_hardware_command("forward")
                    elif w > 190:  
                        send_hardware_command("stop")
                    else:
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

@app.route('/<action>')
def action_handler(action):
    global autonomous_mode
    if action in ["forward", "backward", "left", "right", "stop"]:
        autonomous_mode = False 
        speak("Ok Boss I will Do")
        send_hardware_command(action)
        return jsonify(status="Manual Mode", action=action)
    return jsonify(status="Invalid Vector")

@app.route('/reset_auto')
def reset_auto():
    global autonomous_mode
    autonomous_mode = True
    speak("Titan autonomous tracking re engaged")
    return jsonify(status="Auto Tracking Active")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
