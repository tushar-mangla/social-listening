from listening_loop.config import ensure_dotenv_loaded, get_provider_api_key
from listening_loop.qualification import _provider_headers, _provider_url
import requests

ensure_dotenv_loaded()
headers = _provider_headers()
url = _provider_url()
payload = {
    "model": "deepseek/deepseek-v4.1-flash",
    "messages": [{"role": "user", "content": "hello"}]
}
print(f"URL: {url}")
print(f"Headers: {headers}")
try:
    resp = requests.post(url, headers=headers, json=payload)
    print("Status:", resp.status_code)
    print("Body:", resp.text)
except Exception as e:
    print(e)
