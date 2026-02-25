import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit

import pandas as pd
from dateutil import parser as date_parser
from dateutil import tz


REQUIRED_FIELDS = [
    "event_time",
    "tenant_id",
    "token_id",
    "endpoint",
    "http_method",
    "status_code",
    "ip_address",
    "geo_country",
    "auth_method",
]
OPTIONAL_FIELDS = ["is_injected_anomaly", "anomaly_type"]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def input_path() -> Path:
    return project_root() / "data" / "raw_logs" / "api_logs.jsonl"


def output_path() -> Path:
    return project_root() / "data" / "normalized_logs" / "api_logs_normalized.csv"


def normalize_endpoint(raw_endpoint: object) -> Optional[str]:
    if not isinstance(raw_endpoint, str):
        return None

    value = raw_endpoint.strip()
    if not value:
        return None

    split = urlsplit(value)
    endpoint = split.path or value
    endpoint = endpoint.strip().lower().replace("\\", "/")

    while "//" in endpoint:
        endpoint = endpoint.replace("//", "/")

    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"

    if len(endpoint) > 1 and endpoint.endswith("/"):
        endpoint = endpoint.rstrip("/")

    return endpoint


def normalize_timestamp(raw_ts: object) -> Optional[str]:
    if not isinstance(raw_ts, str) or not raw_ts.strip():
        return None
    try:
        parsed = date_parser.isoparse(raw_ts)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz.UTC)
    else:
        parsed = parsed.astimezone(tz.UTC)

    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def coerce_status_code(raw_code: object) -> Optional[int]:
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        return None

    if 100 <= code <= 599:
        return code
    return None


def row_has_required_fields(row: Dict[str, object]) -> bool:
    for field in REQUIRED_FIELDS:
        if field not in row:
            return False
        value = row[field]
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def normalize_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    if not row_has_required_fields(row):
        return None

    event_time = normalize_timestamp(row["event_time"])
    endpoint = normalize_endpoint(row["endpoint"])
    status_code = coerce_status_code(row["status_code"])

    if not event_time or not endpoint or status_code is None:
        return None

    normalized: Dict[str, object] = {
        "event_time": event_time,
        "tenant_id": str(row["tenant_id"]).strip(),
        "token_id": str(row["token_id"]).strip(),
        "endpoint": endpoint,
        "http_method": str(row["http_method"]).strip().upper(),
        "status_code": status_code,
        "ip_address": str(row["ip_address"]).strip(),
        "geo_country": str(row["geo_country"]).strip().upper(),
        "auth_method": str(row["auth_method"]).strip(),
    }
    if "is_injected_anomaly" in row:
        normalized["is_injected_anomaly"] = bool(row.get("is_injected_anomaly"))
    if "anomaly_type" in row:
        value = row.get("anomaly_type")
        normalized["anomaly_type"] = str(value).strip() if value is not None else "none"
    return normalized


def normalize_file(source: Path) -> List[Dict[str, object]]:
    normalized_rows: List[Dict[str, object]] = []

    with source.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                # Skip malformed JSON records to keep output clean.
                continue

            if not isinstance(payload, dict):
                continue

            normalized = normalize_row(payload)
            if normalized is not None:
                normalized_rows.append(normalized)

    normalized_rows.sort(key=lambda row: row["event_time"])
    return normalized_rows


def main() -> None:
    src = input_path()
    dst = output_path()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    rows = normalize_file(src)
    all_columns = REQUIRED_FIELDS + [
        field for field in OPTIONAL_FIELDS if any(field in row for row in rows)
    ]
    frame = pd.DataFrame(rows, columns=all_columns)
    frame.to_csv(dst, index=False)

    print(f"Normalized {len(rows)} rows to {dst}")


if __name__ == "__main__":
    main()
