import os
import requests
from flask import Flask, render_template, send_from_directory, request, jsonify, Response
from duckduckgo_search import DDGS
from google import genai
from google.genai import types

app = Flask(__name__)

# Initialize Gemini Client cleanly using standard SDK initialization
ai_client = genai.Client()

last_motor_command = "STOP"
latest_frame = None  
mic_state = False    

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
# 1. LIVE VIDEO & MOTOR ROUTES
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
        import time
        time.sleep(0.04)

@app.route('/video_stream')
def video_stream():
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/cmd', methods=['GET', 'POST'])
def handle_cmd():
    global last_motor_command
    if request.method == 'POST':
        data = request.get_json() or {}
        last_motor_command = data.get('command', 'STOP')
        return jsonify({"status": "ok", "command": last_motor_command})
    else:
        return jsonify({"command": last_motor_command})

@app.route('/api/mic_status', methods=['GET', 'POST'])
def handle_mic():
    global mic_state
    if request.method == 'POST':
        data = request.get_json() or {}
        mic_state = data.get('active', False)
        return jsonify({"mic_active": mic_state})
    else:
        return jsonify({"mic_active": mic_state})

# ---------------------------------------------------------
# 2. FIXED ELEVENLABS TTS ROUTE (Voice Attached)
# ---------------------------------------------------------
@app.route('/api/tts', methods=['POST'])
def text_to_speech():
    data = request.get_json() or {}
    text = data.get('text', '')

    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "XPtpzgZIma7xJiyvHcK7").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if not elevenlabs_key:
        print("[TTS ERROR] ELEVENLABS_API_KEY missing on Render environment.")
        return jsonify({"error": "ElevenLabs API Key missing"}), 500

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": elevenlabs_key
    }
    
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.80,
            "similarity_boost": 0.80,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            audio_path = "titan_voice.mp3"
            with open(audio_path, "wb") as f:
                f.write(response.content)
            return send_file(audio_path, mimetype="audio/mpeg")
        else:
            print(f"[ELEVENLABS ERROR Response]: {response.text}")
            return jsonify({"error": f"ElevenLabs failed: {response.text}"}), 500
    except Exception as e:
        print(f"[TTS SERVER EXCEPTION]: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------
# 3. FIXED DUCKDUCKGO SEARCH + GEMINI AI BRAIN
# ---------------------------------------------------------
@app.route('/api/ask_ai', methods=['POST'])
def ask_ai():
    data = request.get_json() or {}
    user_query = data.get('query', '')

    if not user_query:
        return jsonify({"reply": "No query received."})

    # A. Fetch live internet data via DuckDuckGo (Free, No API Key)
    live_context = "No live internet data available."
    try:
        results = DDGS().text(user_query, max_results=2)
        extracted_texts = []
        for result in results:
            title = result.get('title', '')
            body = result.get('body', '')
            extracted_texts.append(f"- {title}: {body}")
            
        if extracted_texts:
            live_context = "\n".join(extracted_texts)
    except Exception as e:
        print(f"[DUCKDUCKGO ERROR]: {str(e)}")

    # B. Send Search Results + User Query to Gemini AI Brain using types Config
    try:
        system_instruction = f"""You are TiTaN, an advanced industrial robotic AI assistant engineered by Malhar Deshmukh at TiTaN Labs Of iNNvovention.
        You have access to live internet search results. Use the 'Live Internet Data' below to answer the user accurately. If irrelevant, use your core knowledge.
        If spoken to in Marathi, reply entirely in fluent Marathi Devanagari. If in Hindi, reply in Hindi. If in English, reply in English.
        Keep responses crisp, calculated, and direct for speech synthesis.
        
        === LIVE INTERNET DATA ===
        {live_context}
        ==========================
        """

        # Using the standard modern Google GenAI SDK configuration structure
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_query,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=256,
                temperature=0.4
            )
        )
        
        ai_answer = response.text
        return jsonify({"reply": ai_answer})

    except Exception as e:
        error_details = str(e)
        print(f"[GEMINI ERROR LOG]: {error_details}")
        return jsonify({"reply": f"AI Processor Error: {error_details}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
