import os
import httpx
from groq import Groq

# Initialize Groq with explicit HTTP client and timeout settings
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()

def get_groq_client():
    if not GROQ_KEY:
        return None
    # Use httpx client with SSL verification and explicit timeout
    http_client = httpx.Client(timeout=15.0, verify=True)
    return Groq(api_key=GROQ_KEY, http_client=http_client)

@app.route('/api/ask_ai', methods=['POST'])
def ask_ai():
    data = request.get_json() or {}
    user_query = data.get('query', '').strip()

    if not user_query:
        return jsonify({"reply": "No query received."})

    client = get_groq_client()
    if not client:
        return jsonify({"reply": "Groq API Key is missing in Render Environment Variables."})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """You are TiTaN, an advanced robotic AI assistant engineered for automation and mechatronics systems by Malhar Deshmukh at TiTaN Labs Of iNNvovention.
                    If spoken to in Marathi (or Devanagari script), reply completely in fluent, clean Marathi text in Devanagari script. If in Hindi, reply in Hindi. If in English, reply in English.
                    Keep responses direct, crisp, and conversational for audio speech output."""
                },
                {"role": "user", "content": user_query}
            ],
            max_tokens=512,
            temperature=0.6
        )
        ai_answer = response.choices[0].message.content.strip()
        return jsonify({"reply": ai_answer})
    except Exception as e:
        print(f"[AI CONNECTION ERROR] {e}")
        return jsonify({"reply": f"AI Engine Connection Error: {str(e)}"})
