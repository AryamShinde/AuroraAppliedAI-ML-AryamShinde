import httpx

q = 'When is Layla planning her trip to London?'
url = 'http://localhost:8114/ask'
resp = httpx.post(url, json={'question': q}, timeout=90)
print('Status:', resp.status_code)
print('Body:', resp.text)