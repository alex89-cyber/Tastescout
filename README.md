# TasteScout 🧭

**Live demo:** https://tastescout-adiof9vm6xlqkuungpetrq.streamlit.app

An AI agent for small businesses. Tell it your business and your neighborhood; it
queries Qloo's Taste AI™ to map what people around you love (places, brands,
music, podcasts) and turns that into a concrete plan: what to sell, who to
partner with, and how to talk to your audience. Built for the Qloo Agentic Hackathon.

## How it works

1. The user enters a business type, a location, optional reference tastes
   (e.g. "Bad Bunny, Blue Bottle Coffee") and a goal.
2. An LLM agent with tool calling decides what to query and calls two tools:
   - `search_entities` → `GET /search` (resolves "Bad Bunny" to a Qloo entity ID)
   - `get_insights` → `GET /v2/insights` (places, brands, artists, podcasts… with
     affinity scores, using the location and reference IDs as signals; places are
     filtered to the neighborhood with `filter.location.query`)
3. The agent writes a plan grounded only in Qloo results: audience profile,
   3 things to sell, partnerships, social media tone, and the Qloo data used.
   Its own interpretations are labeled "(sugerencia)".
4. The UI shows every agent step and the exact Qloo API calls, so nothing is a black box.

The UI and generated plans are in Spanish (target users are small businesses in
Mexico City); the agent answers in the user's language.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your Qloo key and an LLM key
streamlit run app.py
```

Without `QLOO_API_KEY` the app runs in demo mode with fake sample data
(`mock_data.json`) so you can try the interface.

### Configuration (`.streamlit/secrets.toml`)

| Key | Description |
|---|---|
| `QLOO_API_KEY` | Qloo hackathon API key |
| `QLOO_BASE_URL` | Defaults to `https://hackathon.api.qloo.com` |
| `LLM_API_KEY` | Key for any OpenAI-compatible LLM provider |
| `LLM_BASE_URL` | e.g. Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/` (empty = OpenAI) |
| `LLM_MODEL` | e.g. `gemini-flash-latest` |
| `LLM_FALLBACK_MODEL` | Optional backup model used if the main one returns 429/5xx |

## Deploy on Streamlit Community Cloud

1. Fork this repo. Never commit `secrets.toml` (it is in `.gitignore`).
2. Go to https://share.streamlit.io → **Create app** → pick the repo and `app.py`.
3. In **Advanced settings → Secrets**, paste your `secrets.toml` contents.
4. Deploy.

## Project structure

- `app.py` — Streamlit UI
- `agent.py` — tool-calling agent loop and system prompt
- `qloo_client.py` — minimal Qloo API client (server-side key, call log)
- `mock_data.json` — fake data for demo mode

## License

MIT — see [LICENSE](LICENSE).
