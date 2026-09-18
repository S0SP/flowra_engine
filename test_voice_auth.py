import os
import requests

def test_dograh_call(secret):
    dograh_url = "https://bulk-hulk-carpenter.ngrok-free.dev"
    url = f"{dograh_url}/api/v1/telephony/initiate-call"
    headers = {
        "Content-Type": "application/json",
        "X-Flowra-Secret": secret,
    }
    payload = {
        "workflow_id": 1,
        "phone_number": "+917003249959",
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload)
        print(f"Testing with secret '{secret}': {resp.status_code}")
        if resp.status_code != 200:
            print(f"Response Body: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_dograh_call("sumit")
    test_dograh_call("change-me-in-production")
