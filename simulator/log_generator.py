import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

from faker import Faker


TENANTS = ["tenant-acme", "tenant-globex", "tenant-initech", "tenant-umbrella"]
HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]
BASE_ENDPOINTS = ["/v1/users", "/v1/billing", "/v1/projects", "/v1/tokens"]
BASE_COUNTRIES = ["US", "GB", "DE", "FR"]
ANOMALY_ENDPOINTS = ["/v1/admin/export", "/v1/internal/debug", "/v1/system/backup"]
ANOMALY_COUNTRIES = ["RU", "CN", "BR", "ZA"]


@dataclass
class TokenProfile:
    tenant_id: str
    token_id: str
    countries: List[str]
    endpoints: List[str]
    base_requests: int


def iso8601(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def choose_status_code(rng: random.Random) -> int:
    roll = rng.random()
    if roll < 0.90:
        return 200
    if roll < 0.96:
        return 201
    if roll < 0.985:
        return 400
    return 500


def build_profiles(token_count: int, rng: random.Random) -> List[TokenProfile]:
    profiles: List[TokenProfile] = []
    for i in range(token_count):
        tenant_id = TENANTS[i % len(TENANTS)]
        token_id = f"tok_{tenant_id.split('-')[1]}_{i:03d}"

        profiles.append(
            TokenProfile(
                tenant_id=tenant_id,
                token_id=token_id,
                countries=rng.sample(BASE_COUNTRIES, k=2),
                endpoints=rng.sample(BASE_ENDPOINTS, k=2),
                base_requests=rng.randint(45, 80),
            )
        )
    return profiles


def normal_event(
    profile: TokenProfile,
    faker: Faker,
    rng: random.Random,
    base_time: datetime,
) -> Dict[str, object]:
    ts = base_time + timedelta(seconds=rng.randint(0, 3600))
    return {
        "event_time": iso8601(ts),
        "tenant_id": profile.tenant_id,
        "token_id": profile.token_id,
        "endpoint": rng.choice(profile.endpoints),
        "http_method": rng.choice(HTTP_METHODS),
        "status_code": choose_status_code(rng),
        "ip_address": faker.ipv4_public(),
        "geo_country": rng.choice(profile.countries),
        "auth_method": "api_token",
        "is_injected_anomaly": False,
        "anomaly_type": "none",
    }


def anomaly_events(
    profile: TokenProfile,
    faker: Faker,
    rng: random.Random,
    base_time: datetime,
) -> List[Dict[str, object]]:
    events: List[Dict[str, object]] = []

    # 1) Rate spike: sudden burst from the same token in a short window.
    spike_start = base_time + timedelta(minutes=rng.randint(5, 50))
    for _ in range(rng.randint(25, 40)):
        ts = spike_start + timedelta(seconds=rng.randint(0, 120))
        events.append(
            {
                "event_time": iso8601(ts),
                "tenant_id": profile.tenant_id,
                "token_id": profile.token_id,
                "endpoint": rng.choice(profile.endpoints),
                "http_method": rng.choice(HTTP_METHODS),
                "status_code": choose_status_code(rng),
                "ip_address": faker.ipv4_public(),
                "geo_country": rng.choice(profile.countries),
                "auth_method": "api_token",
                "is_injected_anomaly": True,
                "anomaly_type": "volume_spike",
            }
        )

    # 2) New country: token appears from a previously unseen geo.
    new_country = rng.choice([c for c in ANOMALY_COUNTRIES if c not in profile.countries])
    ts_country = base_time + timedelta(minutes=rng.randint(10, 55))
    events.append(
        {
            "event_time": iso8601(ts_country),
            "tenant_id": profile.tenant_id,
            "token_id": profile.token_id,
            "endpoint": rng.choice(profile.endpoints),
            "http_method": rng.choice(HTTP_METHODS),
            "status_code": choose_status_code(rng),
            "ip_address": faker.ipv4_public(),
            "geo_country": new_country,
            "auth_method": "api_token",
            "is_injected_anomaly": True,
            "anomaly_type": "new_geo",
        }
    )

    # 3) New endpoint: token calls an endpoint outside its normal baseline.
    unseen_endpoint = rng.choice(
        [e for e in ANOMALY_ENDPOINTS if e not in profile.endpoints]
    )
    ts_endpoint = base_time + timedelta(minutes=rng.randint(15, 58))
    for _ in range(3):
        ts = ts_endpoint + timedelta(seconds=rng.randint(0, 120))
        events.append(
            {
                "event_time": iso8601(ts),
                "tenant_id": profile.tenant_id,
                "token_id": profile.token_id,
                "endpoint": unseen_endpoint,
                "http_method": rng.choice(HTTP_METHODS),
                "status_code": choose_status_code(rng),
                "ip_address": faker.ipv4_public(),
                "geo_country": rng.choice(profile.countries),
                "auth_method": "api_token",
                "is_injected_anomaly": True,
                "anomaly_type": "new_endpoint",
            }
        )

    return events


def generate_events(token_count: int, seed: int) -> List[Dict[str, object]]:
    faker = Faker()
    rng = random.Random(seed)
    Faker.seed(seed)

    profiles = build_profiles(token_count=token_count, rng=rng)
    run_start = datetime.now(timezone.utc)
    all_events: List[Dict[str, object]] = []

    for profile in profiles:
        for _ in range(profile.base_requests):
            all_events.append(normal_event(profile, faker, rng, run_start))

        all_events.extend(anomaly_events(profile, faker, rng, run_start))

    all_events.sort(key=lambda item: item["event_time"])
    return all_events


def resolve_output_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "raw_logs" / "api_logs.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic API token logs.")
    parser.add_argument("--tokens", type=int, default=10, help="Number of unique tokens.")
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible datasets.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing raw logs instead of overwriting.",
    )
    args = parser.parse_args()

    events = generate_events(token_count=args.tokens, seed=args.seed)
    output_path = resolve_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if args.append else "w"
    with output_path.open(mode, encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event))
            f.write("\n")

    action = "Appended" if args.append else "Wrote"
    print(f"{action} {len(events)} events to {output_path}")


if __name__ == "__main__":
    main()
