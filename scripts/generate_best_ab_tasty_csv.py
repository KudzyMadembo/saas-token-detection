import argparse
import csv
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


CAMPAIGNS = ["123456", "234567", "345678", "456789", "567890", "678901"]
VARIATIONS = {
    "123456": ["111111", "222222", "999111"],
    "234567": ["333333", "444444", "999222"],
    "345678": ["555555", "666666", "999333"],
    "456789": ["777777", "888888", "999444"],
    "567890": ["101010", "202020", "303030"],
    "678901": ["404040", "505050", "606060"],
}
HIT_TYPES = ["PAGEVIEW", "EVENT", "CAMPAIGN", "TRANSACTION"]
URLS = [
    "/",
    "/home",
    "/products",
    "/cart",
    "/checkout",
    "/account",
    "/search?q=test",
    "/search?q=promo",
    "/api/v1/feature-flags",
    "/api/v1/recommendations",
]
ANOMALY_URLS = ["/admin/export", "/internal/debug", "/api/v1/system/backup"]
COUNTRIES = ["USA", "Canada", "France", "Germany", "India", "Brazil", "China"]
ANOMALY_COUNTRIES = ["North Korea", "Russia", "Iran"]
USER_AGENTS = ["Chrome", "Firefox", "Safari", "Edge", "Opera", "Bot"]
DEVICE_TYPES = ["web", "ios", "android", "server"]
PLANS = ["free", "pro", "enterprise"]
SEGMENTS = ["new_user", "returning", "high_value", "discount_hunter", "b2b"]
DECISION_GROUPS = ["pricing", "search", "checkout", "recommendation"]
ENVIRONMENTS = ["preprod", "prod"]
HTTP_METHODS = ["GET", "POST", "PUT"]
AUTH_METHODS = ["api_token", "sdk_server", "oauth2"]


def random_ip(rng: random.Random) -> str:
    return ".".join(str(rng.randint(1, 254)) for _ in range(4))


def random_visitor_id(rng: random.Random) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(rng.choice(alphabet) for _ in range(16))


def weighted_status(rng: random.Random, anomaly: bool) -> int:
    if anomaly:
        return rng.choices([200, 401, 403, 429, 500], weights=[30, 20, 20, 15, 15], k=1)[0]
    return rng.choices([200, 201, 204, 400, 404, 500], weights=[84, 6, 2, 4, 2, 2], k=1)[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate large enriched AB Tasty CSV dataset.")
    parser.add_argument("--rows", type=int, default=300000, help="Number of rows to generate.")
    parser.add_argument("--seed", type=int, default=77, help="Deterministic seed.")
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Time span in days before current UTC time.",
    )
    parser.add_argument(
        "--output",
        default="data/raw_logs/AB_Tasty_Best_90_Day_Logs.csv",
        help="Output CSV path.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rng = random.Random(args.seed)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parents[1] / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = datetime.now(timezone.utc) - timedelta(days=args.days)
    seconds_window = max(1, args.days * 24 * 60 * 60)

    header = [
        # AB Tasty-like columns
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
        # Canonical analysis columns
        "event_time",
        "tenant_id",
        "token_id",
        "endpoint",
        "http_method",
        "status_code",
        "ip_address",
        "geo_country",
        "auth_method",
        "is_injected_anomaly",
        "anomaly_type",
        # Extra enterprise context fields
        "Environment",
        "Device_Type",
        "Session_ID",
        "Bot_Flag",
        "QA_Flag",
        "Visitor_Consent",
        "Decision_Group",
        "Auth_Result",
        "Response_Time_ms",
        "Error_Code",
        "Revenue",
        "Segment",
        "Plan_Type",
        "Country_Risk",
        "Is_Premium",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)

        for _ in range(args.rows):
            campaign = rng.choice(CAMPAIGNS)
            variation = rng.choice(VARIATIONS[campaign])
            visitor_id = random_visitor_id(rng)
            ts = start + timedelta(seconds=rng.randint(0, seconds_window))
            ts_iso = ts.strftime("%Y-%m-%d %H:%M:%S")
            unix_ts = int(ts.timestamp())

            hit_type = rng.choice(HIT_TYPES)
            url = rng.choice(URLS)
            country = rng.choice(COUNTRIES)
            user_agent = rng.choice(USER_AGENTS)
            bot_flag = user_agent == "Bot"
            is_anomaly = rng.random() < 0.085
            anomaly_type = "none"

            if is_anomaly:
                anomaly_type = rng.choice(
                    ["volume_spike", "new_geo", "new_endpoint", "auth_drift", "error_spike"]
                )
                if anomaly_type == "new_geo":
                    country = rng.choice(ANOMALY_COUNTRIES)
                if anomaly_type == "new_endpoint":
                    url = rng.choice(ANOMALY_URLS)
                if anomaly_type == "auth_drift":
                    user_agent = rng.choice(["Bot", "UnknownClient", "Headless"])
                    bot_flag = user_agent == "Bot"

            method = "POST" if hit_type == "TRANSACTION" else rng.choice(HTTP_METHODS)
            status_code = weighted_status(rng, is_anomaly)
            auth_result = "success" if status_code < 400 else "failure"
            response_ms = rng.randint(40, 420) if not is_anomaly else rng.randint(180, 1800)
            error_code = "" if status_code < 400 else rng.choice(["AUTH_401", "FORBIDDEN_403", "RATE_429", "SRV_500"])
            revenue = f"{rng.uniform(12.0, 900.0):.2f}" if hit_type == "TRANSACTION" and status_code < 400 else ""
            consent = rng.random() > 0.08
            env = rng.choices(ENVIRONMENTS, weights=[20, 80], k=1)[0]
            device = rng.choice(DEVICE_TYPES)
            session_id = str(uuid.uuid4())
            qa_flag = rng.random() < 0.02
            decision_group = rng.choice(DECISION_GROUPS)
            segment = rng.choice(SEGMENTS)
            plan = rng.choice(PLANS)
            country_risk = "high" if country in ANOMALY_COUNTRIES else rng.choice(["low", "medium"])
            is_premium = plan in {"pro", "enterprise"}
            ip = random_ip(rng)

            # Canonical columns mapped from the same event context.
            event_time = ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            tenant_id = campaign
            token_id = variation
            endpoint = url
            auth_method = rng.choice(AUTH_METHODS)

            writer.writerow(
                [
                    ts_iso,
                    unix_ts,
                    visitor_id,
                    campaign,
                    variation,
                    hit_type,
                    url,
                    ip,
                    country,
                    user_agent,
                    event_time,
                    tenant_id,
                    token_id,
                    endpoint,
                    method,
                    status_code,
                    ip,
                    country,
                    auth_method,
                    "true" if is_anomaly else "false",
                    anomaly_type,
                    env,
                    device,
                    session_id,
                    "true" if bot_flag else "false",
                    "true" if qa_flag else "false",
                    "true" if consent else "false",
                    decision_group,
                    auth_result,
                    response_ms,
                    error_code,
                    revenue,
                    segment,
                    plan,
                    country_risk,
                    "true" if is_premium else "false",
                ]
            )

    print(f"Wrote {args.rows} rows to {output_path}")


if __name__ == "__main__":
    main()
