import json
import argparse
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
AB_TASTY_COLUMNS = {
    "Timestamp",
    "Unix_Timestamp",
    "Visitor_ID",
    "Campaign_ID",
    "Variation_ID",
    "Hit_Type",
    "URL",
    "IP_Address",
    "Location",
    "User_Agent",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def input_path() -> Path:
    return project_root() / "data" / "raw_logs" / "api_logs.jsonl"


def output_path() -> Path:
    return project_root() / "data" / "normalized_logs" / "api_logs_normalized.csv"


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "t"}
    return False


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
    if raw_ts is None:
        return None
    if isinstance(raw_ts, (int, float)):
        try:
            parsed = pd.to_datetime(raw_ts, unit="s", utc=True)
        except (TypeError, ValueError):
            return None
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime().replace(microsecond=0).isoformat().replace("+00:00", "Z")
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
        normalized["is_injected_anomaly"] = parse_bool(row.get("is_injected_anomaly"))
    if "anomaly_type" in row:
        value = row.get("anomaly_type")
        normalized["anomaly_type"] = str(value).strip() if value is not None else "none"
    return normalized


def normalize_jsonl_file(source: Path) -> List[Dict[str, object]]:
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


def is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value))


def looks_like_ab_tasty_csv(columns: List[str]) -> bool:
    return AB_TASTY_COLUMNS.issubset(set(columns))


def map_ab_tasty_row(row: Dict[str, object]) -> Dict[str, object]:
    timestamp = row.get("Timestamp")
    if is_missing(timestamp):
        timestamp = row.get("Unix_Timestamp")

    campaign_id = row.get("Campaign_ID")
    variation_id = row.get("Variation_ID")
    hit_type = str(row.get("Hit_Type")).strip().upper() if not is_missing(row.get("Hit_Type")) else ""
    user_agent = str(row.get("User_Agent")).strip() if not is_missing(row.get("User_Agent")) else "unknown"
    tenant_id = str(campaign_id).strip() if not is_missing(campaign_id) else "unknown_campaign"
    token_id = str(variation_id).strip() if not is_missing(variation_id) else str(row.get("Visitor_ID")).strip()
    return {
        "event_time": timestamp,
        "tenant_id": tenant_id,
        # Variation ID is a stable identity across events in this synthetic dataset.
        "token_id": token_id,
        "endpoint": row.get("URL"),
        # Approximate method from event category to keep analyzer features useful.
        "http_method": "POST" if hit_type == "TRANSACTION" else "GET",
        "status_code": 200,
        "ip_address": row.get("IP_Address"),
        "geo_country": row.get("Location"),
        "auth_method": user_agent.lower(),
    }


def normalize_csv_file(source: Path) -> List[Dict[str, object]]:
    frame = pd.read_csv(source)
    rows = frame.to_dict(orient="records")
    normalized_rows: List[Dict[str, object]] = []
    columns = frame.columns.tolist()
    ab_tasty_mode = looks_like_ab_tasty_csv(columns)

    for row in rows:
        candidate = map_ab_tasty_row(row) if ab_tasty_mode else row
        normalized = normalize_row(candidate)
        if normalized is not None:
            normalized_rows.append(normalized)

    normalized_rows.sort(key=lambda row: row["event_time"])
    return normalized_rows


def normalize_file(source: Path) -> List[Dict[str, object]]:
    suffix = source.suffix.lower()
    if suffix in {".jsonl", ".json"}:
        return normalize_jsonl_file(source)
    if suffix == ".csv":
        return normalize_csv_file(source)
    raise ValueError(f"Unsupported input format: {source}. Use .jsonl, .json, or .csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize raw logs into canonical CSV.")
    parser.add_argument(
        "--input",
        default=str(input_path()),
        help="Raw input file (.jsonl/.json/.csv).",
    )
    parser.add_argument(
        "--output",
        default=str(output_path()),
        help="Normalized CSV output path.",
    )
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
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
