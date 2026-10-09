import os
import time
import threading
import requests

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from ddgs import DDGS
from google import genai
from google.genai import types


# ============================================================
# TiTaN AI ROBOT - FLASK BACKEND
# ============================================================

app = Flask(__name__)


# ============================================================
# SHARED ROBOT STATE
# ============================================================

state_lock = threading.Lock()

last_motor_command = "STOP"
last_command_time = time.monotonic()

latest_frame = None
latest_frame_time = 0

phone_last_seen = 0
esp32_last_seen = 0

microphone_active = False

telemetry = {
    "battery": 0,
    "wifi_rssi": 0,
    "ip": "",
    "uptime": 0,
    "command": "STOP",
}


# ============================================================
# CONFIGURATION
# ============================================================

COMMAND_TIMEOUT = float(
    os.environ.get("COMMAND_TIMEOUT", "1.5")
)

VIDEO_TIMEOUT = float(
    os.environ.get("VIDEO_TIMEOUT", "3.0")
)

PHONE_TIMEOUT = float(
    os.environ.get("PHONE_TIMEOUT", "5.0")
)

ESP32_TIMEOUT = float(
    os.environ.get("ESP32_TIMEOUT", "5.0")
)


# ============================================================
# ALLOWED MOTOR COMMANDS
# ============================================================

ALLOWED_COMMANDS = {
    "FORWARD",
    "BACKWARD",
    "LEFT",
    "RIGHT",
    "STOP",
}


# ============================================================
# JSON HELPER
# ============================================================

def request_json():
    return request.get_json(silent=True) or {}


# ============================================================
# MOTOR CONTROL
# ============================================================

def set_motor_command(command):
    global last_motor_command
    global last_command_time

    command = str(command).upper().strip()

    if command not in ALLOWED_COMMANDS:
        return False

    with state_lock:
        last_motor_command = command
        last_command_time = time.monotonic()

        telemetry["command"] = command

    return True


def get_safe_motor_command():
    with state_lock:
        if (
            time.monotonic() - last_command_time
            > COMMAND_TIMEOUT
        ):
            return "STOP"

        return last_motor_command


# ============================================================
# MAIN DASHBOARD
# URL: /
# FILE: templates/index.html
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# ROBOT NODE
# URL: /robot
# FILE: templates/robot_node.html
# ============================================================

@app.route("/robot")
def robot():
    return render_template("robot_node.html")


# ============================================================
# HEALTH STATUS
# URL: /api/health
# ============================================================

@app.route("/api/health")
def health():
    now = time.monotonic()

    with state_lock:
        phone_online = (
            phone_last_seen > 0
            and now - phone_last_seen <= PHONE_TIMEOUT
        )

        esp32_online = (
            esp32_last_seen > 0
            and now - esp32_last_seen <= ESP32_TIMEOUT
        )

        camera_online = (
            latest_frame is not None
            and now - latest_frame_time <= VIDEO_TIMEOUT
        )

        mic_on = bool(microphone_active)

        current_telemetry = dict(telemetry)

    # Obtain the command outside the existing lock.
    motor_command = get_safe_motor_command()

    return jsonify({
        "server": "ONLINE",

        "phone": (
            "ONLINE" if phone_online else "OFFLINE"
        ),

        "esp32": (
            "ONLINE" if esp32_online else "OFFLINE"
        ),

        "camera": (
            "ONLINE" if camera_online else "OFFLINE"
        ),

        "microphone": (
            "ON" if mic_on else "OFF"
        ),

        "phone_online": phone_online,
        "esp32_online": esp32_online,
        "camera_online": camera_online,
        "mic_on": mic_on,

        "motor_command": motor_command,

        "battery": current_telemetry.get(
            "battery", 0
        ),

        "rssi": current_telemetry.get(
            "wifi_rssi", 0
        ),

        "telemetry": current_telemetry,
    })


# ============================================================
# PHONE HEARTBEAT
# URL: /api/phone/heartbeat
# ============================================================

@app.route(
    "/api/phone/heartbeat",
    methods=["POST"]
)
def phone_heartbeat():
    global phone_last_seen

    with state_lock:
        phone_last_seen = time.monotonic()

    return jsonify({
        "status": "ok"
    })


# ============================================================
# MICROPHONE STATUS
# URL: /api/mic_status
# ============================================================

@app.route(
    "/api/mic_status",
    methods=["POST"]
)
def mic_status():
    global microphone_active

    data = request_json()

    microphone_active = bool(
        data.get("active", False)
    )

    return jsonify({
        "status": "ok",
        "microphone": (
            "ON" if microphone_active else "OFF"
        ),
    })


# ============================================================
# CAMERA FRAME UPLOAD
# URL: /api/video_feed
# ============================================================

@app.route(
    "/api/video_feed",
    methods=["POST"]
)
def upload_frame():
    global latest_frame
    global latest_frame_time
    global phone_last_seen

    frame = request.get_data()

    if not frame:
        return jsonify({
            "error": "Empty frame"
        }), 400

    # Reject frames larger than 2 MB.
    if len(frame) > 2 * 1024 * 1024:
        return jsonify({
            "error": "Frame too large"
        }), 413

    now = time.monotonic()

    with state_lock:
        latest_frame = frame
        latest_frame_time = now
        phone_last_seen = now

    return jsonify({
        "status": "received"
    })


# ============================================================
# LIVE CAMERA STREAM
# URL: /video_stream
# ============================================================

def generate_stream():
    last_frame = None

    while True:
        with state_lock:
            frame = latest_frame
            frame_time = latest_frame_time

        if (
            frame is not None
            and time.monotonic() - frame_time <= VIDEO_TIMEOUT
            and frame != last_frame
        ):
            last_frame = frame

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-cache\r\n"
                b"\r\n"
                + frame
                + b"\r\n"
            )

        else:
            time.sleep(0.05)


@app.route("/video_stream")
def video_stream():
    return Response(
        generate_stream(),
        mimetype=(
            "multipart/x-mixed-replace; boundary=frame"
        ),
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )


# ============================================================
# ROBOT MOVEMENT API
# GET  /api/cmd -> ESP32 reads command
# POST /api/cmd -> Dashboard sends command
# ============================================================

@app.route(
    "/api/cmd",
    methods=["GET", "POST"]
)
def handle_cmd():
    if request.method == "POST":
        data = request_json()

        command = data.get("command", "STOP")

        if not set_motor_command(command):
            return jsonify({
                "status": "error",
                "error": "Invalid motor command",
            }), 400

        return jsonify({
            "status": "ok",
            "command": str(command).upper(),
        })

    return jsonify({
        "status": "ok",
        "command": get_safe_motor_command(),
        "server_time": time.time(),
    })


# ============================================================
# ESP32 TELEMETRY
# URL: /api/telemetry
# ============================================================

@app.route(
    "/api/telemetry",
    methods=["POST"]
)
def update_telemetry():
    global esp32_last_seen

    data = request_json()

    with state_lock:
        esp32_last_seen = time.monotonic()

        for key in (
            "battery",
            "wifi_rssi",
            "ip",
            "uptime",
        ):
            if key in data:
                telemetry[key] = data[key]

        if "command" in data:
            telemetry["command"] = str(
                data["command"]
            ).upper()

    return jsonify({
        "status": "ok"
    })


# ============================================================
# TEXT TO SPEECH
# URL: /api/tts
# ============================================================

@app.route(
    "/api/tts",
    methods=["POST"]
)
def text_to_speech():
    data = request_json()

    text = str(
        data.get("text", "")
    ).strip()

    if not text:
        return jsonify({
            "error": "No text provided"
        }), 400

    api_key = os.environ.get(
        "ELEVENLABS_API_KEY",
        ""
    ).strip()

    if not api_key:
        return jsonify({
            "error": "ELEVENLABS_API_KEY missing"
        }), 500

    voice_id = os.environ.get(
        "ELEVENLABS_VOICE_ID",
        "XPtpzgZIma7xJiyvHcK7"
    ).strip()

    text = text[:1500]

    url = (
        "https://api.elevenlabs.io/"
        f"v1/text-to-speech/{voice_id}"
    )

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.80,
            "similarity_boost": 0.80,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=20,
        )

        if response.status_code == 200:
            return Response(
                response.content,
                mimetype="audio/mpeg",
                headers={
                    "Cache-Control": "no-store"
                },
            )

        return jsonify({
            "error": (
                f"ElevenLabs error "
                f"{response.status_code}"
            ),
            "details": response.text[:500],
        }), 502

    except requests.RequestException as exc:
        return jsonify({
            "error": f"TTS request failed: {exc}"
        }), 502


# ============================================================
# GEMINI CLIENT
# ============================================================

def get_gemini_client():
    api_key = os.environ.get(
        "GEMINI_API_KEY",
        ""
    ).strip()

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured"
        )

    return genai.Client(
        api_key=api_key
    )


# ============================================================
# TiTaN AI CHAT
# URL: /api/ask_ai
# ============================================================

@app.route(
    "/api/ask_ai",
    methods=["POST"]
)
def ask_ai():
    data = request_json()

    # Accept either frontend field name.
    user_query = str(
        data.get(
            "message",
            data.get("query", "")
        )
    ).strip()

    if not user_query:
        return jsonify({
            "reply": "Please give me a question."
        }), 400

    live_context = (
        "No live internet data available."
    )

    # --------------------------------------------------------
    # LIVE WEB SEARCH
    # --------------------------------------------------------

    try:
        results = DDGS().text(
            user_query,
            max_results=3
        )

        snippets = []

        for result in results:
            title = result.get("title", "")
            body = result.get("body", "")

            if title or body:
                snippets.append(
                    f"- {title}: {body}"
                )

        if snippets:
            live_context = "\n".join(snippets)

    except Exception as exc:
        print(
            f"[WEB SEARCH ERROR] {exc}"
        )

    # --------------------------------------------------------
    # GEMINI RESPONSE
    # --------------------------------------------------------

    try:
        client = get_gemini_client()

        system_instruction = """
You are TiTaN, a custom AI robotic assistant.

You are the intelligence layer of the TiTaN mobile robot.

Rules:
1. Give useful, concise, natural answers.
2. Reply in Marathi Devanagari when the user speaks Marathi.
3. Reply in Hindi when the user speaks Hindi.
4. Reply in English when the user speaks English.
5. Never claim to have physically performed an action unless
   the application actually sent the required command.
6. Never reveal API keys or secret credentials.
7. Treat live web information as reference material.
8. Never invent robot sensor values.
9. Robot movement is controlled by the robot control system.
10. Keep answers suitable for voice output.
"""

        prompt = f"""
USER QUERY:

{user_query}

LIVE INTERNET INFORMATION:

{live_context}

Answer the user's question naturally.
Use the live information when relevant.
"""

        model_name = os.environ.get(
            "GEMINI_MODEL",
            "gemini-2.5-flash"
        ).strip()

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4,
                max_output_tokens=256,
            ),
        )

        answer = (
            response.text or ""
        ).strip()

        if not answer:
            answer = (
                "I could not generate a response."
            )

        return jsonify({
            "reply": answer
        })

    except Exception as exc:
        print(
            f"[GEMINI ERROR] {exc}"
        )

        return jsonify({
            "reply": (
                "TiTaN AI is temporarily unavailable."
            )
        }), 502


# ============================================================
# FAVICON
# ============================================================

@app.route("/favicon.ico")
def favicon():
    path = os.path.join(
        app.root_path,
        "favicon.ico"
    )

    if os.path.exists(path):
        return send_from_directory(
            app.root_path,
            "favicon.ico"
        )

    return "", 204


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    port = int(
        os.environ.get("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
