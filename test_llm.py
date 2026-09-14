import requests

def test_model(model_name):
    url = "http://localhost:20128/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-3742de8df1c28170-qzbn8y-cc6268ad"
    }
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Say 'hello' in exactly one word."}],
        "max_tokens": 10
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=90)
        r.raise_for_status()
        print(f"[{model_name}] SUCCESS: {r.json()['choices'][0]['message']['content'].strip()}")
    except Exception as e:
        print(f"[{model_name}] FAILED: {e}")

test_model("cl/google/gemini-3.5-flash")
test_model("cl/deepseek-ai/deepseek-v4-flash")
test_model("cl/z-ai/glm-5.3-flash")
