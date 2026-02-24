# saas-token-detection

## How To Run

From the project root:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Expected outputs:

- `data/raw_logs/api_logs.jsonl`
- `data/normalized_logs/api_logs_normalized.csv`

## Run Locally (without Docker)

From the project root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r ingestion/requirements.txt -r simulator/requirements.txt
python simulator/log_generator.py --tokens 10 --seed 42
python ingestion/normalize.py
```

Expected outputs:

- `data/raw_logs/api_logs.jsonl`
- `data/normalized_logs/api_logs_normalized.csv`

## Normalized API Log Schema (v1)

- event_time (ISO 8601 string)
- tenant_id (string)
- token_id (string)
- endpoint (string, normalized)
- http_method (string)
- status_code (int)
- ip_address (string)
- geo_country (string)
- auth_method (string, e.g., "api_token")

- Data source: synthetic simulator (Phase 1.3)
- Out-of-band: pipeline runs in Docker lab, not in production path

## How Simulation Works

The simulator generates per-token baseline behavior (normal traffic) and then injects anomalies in the same run:

- Normal traffic per token:
  - stable tenant/token pairing
  - common endpoint set for each token
  - common country set for each token
  - mixed HTTP methods and mostly-success status codes
- Anomaly injection:
  - `rate_spike`: short burst of many requests from one token
  - `new_country`: same token appears from a country outside its baseline
  - `new_endpoint`: same token calls an endpoint outside its baseline

Output format is JSON Lines (one JSON object per line) appended to `data/raw_logs/api_logs.jsonl`.

## Sample Anomaly Examples

- `rate_spike` example:
  - token `tok_acme_000` usually sends low/steady volume, then emits dozens of events in ~2 minutes.
- `new_country` example:
  - token with baseline countries `US`/`GB` suddenly authenticates from `RU`.
- `new_endpoint` example:
  - token normally using `/v1/users` and `/v1/projects` calls `/v1/admin/export`.
