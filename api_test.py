import requests

API_KEY = "AIzaSyDuxT78Cklcuziplt3K1UyZEfsWMhf8NYA"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

payload = {
    "contents": [{"parts": [{"text": "Is this API key working?"}]}]
}

try:
    response = requests.post(URL, json=payload)
    if response.status_code == 200:
        print("✅ Success! Your API key is working.")
    else:
        print(f"❌ Failed. Status Code: {response.status_code}")
        print(f"Error Message: {response.text}")
except Exception as e:
    print(f"An error occurred: {e}")