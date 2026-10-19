# Local backend

Requires Python 3.11 or newer. Original workshop scripts and frontend are unchanged.

From `backend` (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation: `http://127.0.0.1:8000/docs`. The API prefix is `/api/v1`. Run one worker for consistent process-local preferences. This is an unauthenticated **local single-user** service, not an internet-facing deployment. Do not bind to `0.0.0.0`, expose via a tunnel, or grant untrusted frontend origins without adding authentication and deployment-level rate limits.

## Configuration and data

- Edit backend `.env`; list settings use JSON arrays. Restart after config changes. Runtime `/settings` edits only safe UI preferences, held in memory and reset on restart; credentials and security policy cannot be changed through the API.
- `WORKSHOP_DATA_DIR` defaults to `backend/data`. SQLite is persistent in `workshop.sqlite3`, with foreign keys enabled. Data is not encrypted. Back up the data directory only while the application is stopped. Table creation is automatic; future schema changes will require migrations, not just `create_all`.
- Experiment history stores counts and safe status metadata, not raw VoiceMind prompts, audio, transcripts, or PricePilot URLs. History deletion removes the experiment row, not document/RAG assets owned by other modules. Exports include up to 5,000 rows, explicitly indicate truncation, and CSV neutralizes spreadsheet formulas.
- `GET /health` checks actual DB access and storage writes, reports installed dependency versions and whether optional feature routers exist. Groq configuration is not a connectivity claim: use `/health?check_provider=true` to make a real `/models` call and verify both configured model IDs. This sends credentials to Groq and is subject to its network/rate limits.

## PricePilot safety and limitations

Scraping is disabled by default. Add exact hostnames to `WORKSHOP_ALLOWED_HOSTS` (for example `["shop.example.com"]`), including every necessary redirect hostname. Confirm you have permission in each compare request. This confirmation and robots.txt are not substitutes for site terms or legal authorization.

All DNS answers must be public; sockets connect to a validated IP while TLS verifies the original hostname. Every redirect and robots request is independently validated, HTTPS downgrades are denied, and proxies, cookies and compressed responses are not used. A readable successful robots.txt is required: missing/error responses fail closed. Robots denial or crawl scheduling directives block scraping. Response bytes, hops, DNS concurrency and request time are bounded.

Provide selectors matching **one** title and **one** current price. Displayed amounts are exact decimal strings, never floats. Ambiguous symbols (`$`, `¥`), price ranges, multiple amounts, conflicting currencies and ambiguous grouping are rejected. Explicit ISO currency codes are supported; no exchange rates are inferred. Three/four-decimal currency separators that could instead be grouping are rejected rather than guessed. Prices are grouped by currency, with ties preserved. Product identity, variants, shipping, taxes, availability and discounts are **not verified**.

## VoiceMind

Set `WORKSHOP_GROQ_API_KEY` on the backend only. Chat and transcription call real Groq OpenAI-compatible endpoints with model IDs verified through `/models` before use. Model presence does not guarantee modality compatibility or account entitlement; provider errors remain sanitized. No fake fallback responses are generated. Text/audio sent to these endpoints leave your computer and are subject to Groq's policies, charges and rate limits.

Transcription accepts bounded multipart audio, checks extension, content type and file signatures, and sends a generated filename. Signature checking is not full audio decoding; Groq validates actual audio content. Raw audio is not persisted by this module.

`POST /voicemind/speech` returns a **browser Web Speech descriptor**, not audio. Completion means the descriptor was created, not that speech played. Browser support, voices and user-gesture permission vary; browser/OS synthesis may itself use a remote service.

## Integration and tests

See `CONTRACT.md` for exact shared Python and API interfaces. Other-agent routers are mounted when present; their absence is visible in startup logs and health diagnostics. Import errors inside an existing router are not silently swallowed. Document/RAG models register against the shared `Base` from `app/models/documents.py` before tables are created.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation -q
.\.venv\Scripts\python.exe -m compileall -q app
```

Foundation tests use isolated databases and mocked DNS/providers; they do not scrape websites, send real prompts/audio or consume Groq quota. Dependencies for other-agent features are outside this foundation's requirements unless separately agreed in `EXTRA_REQUIREMENTS.txt`.
