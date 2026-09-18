import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_dograh_call():
    dograh_url = os.getenv("DOGRAH_API_URL")
    flowra_secret = os.getenv("DOGRAH_SECRET")
    
    print(f"Testing Dograh API: {dograh_url}")
    print(f"Using Secret: {flowra_secret}")
    
    url = f"{dograh_url}/api/v1/telephony/initiate-call"
    headers = {
        "Content-Type": "application/json",
        "X-Flowra-Secret": flowra_secret,
    }
    payload = {
        "workflow_id": 1,
        "phone_number": "+917003249959",
        "metadata": {"flowra_source": "test_script"},
        "initial_context": {
            "system_prompt": "You are a test AI.",
            "first_message": "",
            "call_objective": "",
            "model_overrides": {
                "is_realtime": False,
                "tts": {"provider": "sarvam", "voice": "anushka", "language": "hi-IN"},
                "llm": {"provider": "groq", "model": "llama-3.3-70b-versatile"}
            }
        },
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload)
        print(f"Status Code: {resp.status_code}")
        print(f"Response Body: {resp.text}")
    except Exception as e:
        print(f"Error making request: {e}")

if __name__ == "__main__":
    test_dograh_call()
