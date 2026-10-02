import os
import threading
import time

import requests
from flask import Flask, Response, jsonify, render_template, request

from duckduckgo_search import DDGS
from google import genai
from google.genai import types

app = Flask(__name__)

# ============================================================
# TiTaN SERVER STATE
# ============================================================

state_lock = threading.Lock()

last_motor_command = "STOP"
last_command_time = time.monotonic()

latest_frame = None
latest_frame_time = 0.0

phone_last_seen = 0.0
esp32_last_seen = 0.0

telemetry = {
    "battery": None,
    "wifi_rssi": None,
    "ip": None,
    "uptime": None,
    "command": "STOP",
}

COMMAND_TIMEOUT = float(os.environ.get("COMMAND_TIMEOUT", "1.5"))
VIDEO_TIMEOUT = float(os.environ.get("VIDEO_TIMEOUT", "3.0"))
PHONE_TIMEOUT = float(os.environ.get("PHONE_TIMEOUT", "5.0"))
ESP32_TIMEOUT = float(os.environ.get("ESP32_TIMEOUT", "5.0"))

ALLOWED_COMMANDS = {
    "FORWARD",
    "REVERSE",
    "LEFT",
    "RIGHT",
    "STOP",
}


def set_motor_command(command):
    global last_motor_command, last_command_time

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
        if time.monotonic() - last_command_time > COMMAND_TIMEOUT:
            return "STOP"
        return last_motor_command


# ============================================================
# PAGES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/robot")
def robot():
    return render_template("robot_node.html")


@app.route("/favicon.ico")
def favicon():
    from flask import send_from_directory

    path = os.path.join(app.root_path, "favicon.ico")

    if os.path.exists(path):
        return send_from_directory(
            app.root_path,
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )

    return ("", 204)


# ============================================================
# HEALTH
# ============================================================

@app.route("/api/health")
def health():
    now = time.monotonic()

    with state_lock:
        return jsonify({
            "server": "ONLINE",
            "phone": (
                "ONLINE"
                if now - phone_last_seen <= PHONE_TIMEOUT
                else "OFFLINE"
            ),
            "esp32": (
                "ONLINE"
                if now - esp32_last_seen <= ESP32_TIMEOUT
                else "OFFLINE"
            ),
            "camera": (
                "ONLINE"
                if latest_frame is not None
                and now - latest_frame_time <= VIDEO_TIMEOUT
                else "OFFLINE"
            ),
            "motor_command": get_safe_motor_command(),
            "telemetry": dict(telemetry),
        })


# ============================================================
# PHONE NODE
# ============================================================

@app.route("/api/phone/heartbeat", methods=["POST"])
def phone_heartbeat():
    global phone_last_seen

    with state_lock:
        phone_last_seen = time.monotonic()

    return jsonify({"status": "ok"})


@app.route("/api/mic_status", methods=["POST"])
def mic_status():
    data = request_json()
    return jsonify({
        "status": "ok",
        "microphone": "ON" if bool(data.get("active")) else "OFF",
    })


# ============================================================
# CAMERA
# Phone POSTs JPEG frames here.
# Dashboard reads MJPEG stream from /video_stream.
# ============================================================

@app.route("/api/video_feed", methods=["POST"])
def upload_frame():
    global latest_frame, latest_frame_time, phone_last_seen

    frame = request.get_data()

    if not frame:
        return jsonify({"error": "Empty frame"}), 400

    if len(frame) > 2 * 1024 * 1024:
        return jsonify({"error": "Frame too large"}), 413

    with state_lock:
        latest_frame = frame
        latest_frame_time = time.monotonic()
        phone_last_seen = time.monotonic()

    return jsonify({"status": "received"})


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
                b"Cache-Control: no-cache\r\n\r\n"
                + frame
                + b"\r\n"
            )

        time.sleep(0.05)


@app.route("/video_stream")
def video_stream():
    return Response(
        generate_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ============================================================
# MOTOR COMMAND API
#
# POST /api/cmd -> Dashboard/phone sends command.
# GET  /api/cmd -> ESP32 polls command.
# ============================================================

@app.route("/api/cmd", methods=["GET", "POST"])
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
        "command": get_safe_motor_command(),
        "server_time": time.time(),
    })


# ============================================================
# ESP32 TELEMETRY
# ============================================================

@app.route("/api/telemetry", methods=["POST"])
def update_telemetry():
    global esp32_last_seen

    data = request_json()

    with state_lock:
        esp32_last_seen = time.monotonic()

        for key in ("battery", "wifi_rssi", "ip", "uptime"):
            if key in data:
                telemetry[key] = data[key]

        if "command" in data:
            telemetry["command"] = str(data["command"]).upper()

    return jsonify({"status": "ok"})


# ============================================================
# ELEVENLABS TTS
# ============================================================

@app.route("/api/tts", methods=["POST"])
def text_to_speech():
    data = request_json()
    text = str(data.get("text", "")).strip()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get(
        "ELEVENLABS_VOICE_ID",
        "XPtpzgZIma7xJiyvHcK7",
    ).strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    if not api_key:
        return jsonify({
            "error": "ELEVENLABS_API_KEY missing"
        }), 500

    text = text[:1500]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

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
                headers={"Cache-Control": "no-store"},
            )

        return jsonify({
            "error": f"ElevenLabs error {response.status_code}",
            "details": response.text[:500],
        }), 502

    except requests.RequestException as exc:
        return jsonify({
            "error": f"TTS request failed: {exc}"
        }), 502


# ============================================================
# GEMINI AI
# Google AI Studio API
# ============================================================

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    return genai.Client(api_key=api_key)


@app.route("/api/ask_ai", methods=["POST"])
def ask_ai():
    data = request_json()
    user_query = str(data.get("query", "")).strip()

    if not user_query:
        return jsonify({
            "reply": "Please give me a question."
        }), 400

    # Optional live web context.
    live_context = "No live internet data available."

    try:
        results = DDGS().text(
            user_query,
            max_results=2
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
        print(f"[WEB SEARCH ERROR] {exc}")

    try:
        client = get_gemini_client()

        system_instruction = """
You are TiTaN, a custom AI robotic assistant engineered by
Malhar Deshmukh.

Your job is to act as the intelligence layer of a mobile robot.

Rules:
1. Keep normal answers concise and useful.
2. If the user speaks Marathi, reply in fluent Marathi Devanagari.
3. If the user speaks Hindi, reply in Hindi.
4. If the user speaks English, reply in English.
5. Never claim that the robot physically performed an action unless
   the application actually sent a motor command.
6. Do not expose API keys or secret credentials.
7. Treat live web snippets as potentially incomplete context.
8. For robot movement, the application handles direct commands;
   do not invent movement commands in a normal AI answer.
"""

        prompt = f"""
User query:
{user_query}

Optional live web context:
{live_context}
"""

        response = client.models.generate_content(
            model=os.environ.get(
                "GEMINI_MODEL",
                "gemini-3.8-flash",
            ),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4,
                max_output_tokens=256,
            ),
        )

        answer = (response.text or "").strip()

        if not answer:
            answer = "I could not generate a response."

        return jsonify({
            "reply": answer
        })

    except Exception as exc:
        print(f"[GEMINI ERROR] {exc}")

        return jsonify({
            "reply": "TiTaN AI is temporarily unavailable."
        }), 502


# ============================================================
# HELPERS
# ============================================================

def request_json():
    from flask import request

    return request.get_json(silent=True) or {}


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
