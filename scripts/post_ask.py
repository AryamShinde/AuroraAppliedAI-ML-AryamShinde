import httpx

q = 'When is Layla planning her trip to London?'
resp = httpx.post('http://localhost:8110/ask', json={'question': q}, timeout=60)
print('Status:', resp.status_code)
print('Body:', resp.text)