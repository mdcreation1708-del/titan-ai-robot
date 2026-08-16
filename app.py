import os
import requests
from flask import Flask, render_template, send_from_directory, request, jsonify, Response
from duckduckgo_search import DDGS
from groq import Groq

app = Flask(__name__)

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
# 1. VIDEO & MOTOR ROUTES
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

# ---------------------------------------------------------
# 2. ELEVENLABS TTS ROUTE
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
            return jsonify({"error": response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------
# 3. DUCKDUCKGO SEARCH + GROQ AI BRAIN
# ---------------------------------------------------------
@app.route('/api/ask_ai', methods=['POST'])
def ask_ai():
    data = request.get_json() or {}
    user_query = data.get('query', '')

    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        return jsonify({"reply": "System Error: GROQ_API_KEY missing."})

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
        print(f"[DDG ERROR]: {str(e)}")

    try:
        client = Groq(api_key=groq_api_key)
        
        system_prompt = f"""You are TiTaN, an advanced robotic AI assistant engineered by Malhar Deshmukh.
        Use the live internet data below to answer accurately if relevant.
        If spoken to in Marathi, reply entirely in fluent Marathi Devanagari. If in Hindi, reply in Hindi. If in English, reply in English.
        Keep responses crisp and direct.
        
        === LIVE INTERNET DATA ===
        {live_context}
        ==========================
        """

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            model="llama-3.3-70b-versatile",
            max_tokens=256,
            temperature=0.4
        )
        
        ai_answer = chat_completion.choices[0].message.content
        return jsonify({"reply": ai_answer})

    except Exception as e:
        return jsonify({"reply": f"AI Error: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
