# Member Messages Q&A API

A minimal FastAPI service that answers natural‑language questions using the public member messages feed as context.

- Live URL: https://aurora-member-qa.onrender.com
- Interactive docs: `GET /docs`
- Primary endpoint: `POST /ask` with body `{ "question": "..." }`

## Quick Start

### Local
1. Create `.env` next to `qa_app.py`:
   - `OPENAI_API_KEY=...`
   - `MESSAGES_API_URL=https://november7-730026606190.europe-west1.run.app/messages/`  (note trailing slash)
2. Install deps and run:
   ```bash
   pip install -r requirements.txt
   python -m uvicorn qa_app:app --host 0.0.0.0 --port 8100
   ```
3. Test:
   ```bash
   curl -s -X POST -H "Content-Type: application/json" \
     -d '{"question":"When is Layla planning her trip to London?"}' \
     http://localhost:8100/ask
   ```

### Render (Docker)
- Containerized via `Dockerfile`; deploy with the included `render.yaml`.
- Environment variables to set in the Render service:
  - `OPENAI_API_KEY` (required)
  - `MESSAGES_API_URL` (defaults to the dataset URL above)
  - Optional: `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_MAX_TOKENS`

## Endpoints
- `GET /` — Landing JSON (service info and links)
- `GET /health` — Health probe
- `POST /ask` — Body `{ "question": "..." }` → `{ "answer": "..." }`
- `GET /docs` — Swagger UI

## How It Works
1. Fetches JSON from `MESSAGES_API_URL` (`items: [{ user_name, message, timestamp, ...}]`).
2. Builds a compact textual context from the items (trimmed to ~6k chars).
3. Sends a constrained prompt to the OpenAI Chat Completions API.
4. Returns the model’s reply as `{ "answer": "..." }`.

## Design Notes (Alternatives Considered)

This section outlines multiple approaches evaluated for building the Q&A system and trade‑offs for each.

1. Direct Prompting over Raw Messages (chosen for MVP)
   - Approach: Concatenate recent or trimmed messages and ask a chat model to answer.
   - Pros: Fast to build, minimal infra, small code surface.
   - Cons: Susceptible to hallucinations, sensitive to prompt, limited by context length.

2. Retrieval‑Augmented Generation (RAG) with Local Embeddings
   - Approach: Embed messages (e.g., using sentence-transformers), index (FAISS), retrieve top‑k relevant lines per question, then prompt the model with only retrieved snippets.
   - Pros: Lower hallucinations, better scaling to large datasets, cheaper per query.
   - Cons: Additional infra and ops (index building, updates), more moving parts.

3. Vector Database (Managed) for Retrieval
   - Approach: Use Pinecone/Weaviate/PGVector instead of local FAISS.
   - Pros: Managed scaling, metadata filtering, hybrid search.
   - Cons: External dependency, cost, provisioning.

4. Rule‑Based/Heuristic Extraction for Structured Questions
   - Approach: For certain patterns (e.g., counts, dates, contact updates) use regex/heuristics to extract deterministically; only use LLM for residual questions.
   - Pros: Deterministic for well‑formed facts (e.g., “How many cars …”).
   - Cons: Narrow coverage and brittle for phrasing variations.

5. Strict Grounding with Citations
   - Approach: Require the model to produce an answer only if accompanied by at least one exact source line; otherwise return a fixed fallback (“I don't have enough information…”).
   - Pros: Reduces unsupported answers, adds auditability.
   - Cons: Slightly more complex prompt/validation and output handling.

6. Streaming + UI
   - Approach: Stream tokens to a front‑end client and show citations.
   - Pros: Better UX, user trust via evidence.
   - Cons: Not necessary for the API requirement; adds complexity.

7. Deployment Options
   - Containers on Render (chosen) vs. serverless functions or a VM. Containers provide a consistent runtime and easy env management.

### Why the current design
- Minimal code, containerized, deployable in minutes.
- Satisfies “publicly accessible API” requirement.
- Leaves room to layer retrieval, citations, and auth later without rewriting the core.

### Known Limitations (and Planned Mitigations)
- Possible hallucinations if the answer is not explicitly present in the data.
  - Mitigate by: adding keyword gating + retrieval + citation checks.
- No auth/rate limits: anyone can call the API.
  - Mitigate by: header‑key auth and per‑IP rate limiting.
- No caching: repeated questions incur repeated model calls.
  - Mitigate by: short TTL in‑memory cache keyed by normalized question.

## Data Insights (Anomalies & Inconsistencies)

Observations are based on the dataset at
`https://november7-730026606190.europe-west1.run.app/messages/` (example slice provided in the prompt) and spot checks.

1. Personally Identifiable Information (PII) in Messages
   - Phone numbers (e.g., `555-349-7841`, `987-654-3210`, `212-555-6051`) and membership/ID‑like values are embedded directly in `message` text.
   - Implication: Downstream answers should avoid exposing or transforming PII inadvertently; consider redaction policies or guardrails.

2. Mixed Message Semantics
   - Messages include both requests ("book…", "please arrange…") and non‑factual statements ("thank you", sentiment). Not every line is a ground‑truth fact.
   - Implication: Answering requires filtering for factual, sourceable lines and ignoring gratitude/feedback chatter.

3. Temporal Ambiguity vs. Timestamps
   - Many messages reference relative time ("this Friday", "next month", "first week of December") while `timestamp` is absolute.
   - Implication: Answers about timing should prefer explicit dates in text; otherwise clarify ambiguity or respond with the fallback.

4. Future‑Dated Timestamps
   - Numerous entries are in the future relative to some queries (e.g., later in 2025). This is acceptable but means the dataset mixes plans and past events.
   - Implication: Treat future plans differently from completed actions when answering.

5. Encoding/Normalization Considerations
   - Non‑ASCII characters and punctuation (e.g., `Müller`, `O'Sullivan`) and various phone formats.
   - Implication: Ensure Unicode safety, normalize tokens for retrieval, and use robust regexes.

6. Possible Missing Facts (example: Vikram car count)
   - In the provided slice, there is no explicit line stating a numeric car count for Vikram; only general car/service mentions.
   - Implication: The API must reply with the fallback when a direct fact is absent to avoid incorrect answers.

7. Duplicates/Integrity Checks (recommended)
   - No duplicates were observed in the sample snippet, but with `total ≈ 3349` a full scan should enforce:
     - Unique `id`
     - Non‑empty `user_name`, `message`, `timestamp`
     - Parseable ISO‑8601 timestamps

### Reproducing Insight Checks

PowerShell (quick sampling):
```powershell
# Raw fetch
$data = Invoke-RestMethod -Uri https://november7-730026606190.europe-west1.run.app/messages/
$items = $data.items

# Per-user counts
$items | Group-Object user_name | Sort-Object Count -Descending |
  Select-Object Name, Count

# Basic integrity checks
$missing = $items | Where-Object { [string]::IsNullOrWhiteSpace($_.user_name) -or
                                   [string]::IsNullOrWhiteSpace($_.message) -or
                                   [string]::IsNullOrWhiteSpace($_.timestamp) }
"missing_count=$($missing.Count)"

# Timestamp parse check
$bad = @(); foreach ($it in $items) { try { [void][DateTime]::Parse($it.timestamp) } catch { $bad += $it } }
"bad_ts_count=$($bad.Count)"
```

Python:
```python
import requests, collections, datetime
u = "https://november7-730026606190.europe-west1.run.app/messages/"
items = requests.get(u, timeout=60).json()["items"]
by_user = collections.Counter(m["user_name"] for m in items)
print(by_user.most_common(10))

# Validate timestamps
bad_ts = [m for m in items if not m.get("timestamp")]
print("missing_ts", len(bad_ts))
```

## Usage Examples

Curl:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"question":"When is Layla planning her trip to London?"}' \
  https://aurora-member-qa.onrender.com/ask
```

PowerShell:
```powershell
$body = @{ question = "Which members mention private jets?" } | ConvertTo-Json
Invoke-RestMethod -Uri https://aurora-member-qa.onrender.com/ask -Method POST -Body $body -ContentType 'application/json'
```

## Roadmap
- Grounding guardrails: keyword gating, retrieval, and citations; strict fallback when evidence absent.
- Basic auth & rate limiting to control external usage.
- Caching of identical questions.
- Optional filtered data endpoints (e.g., `/messages/by-user?name=...`).
