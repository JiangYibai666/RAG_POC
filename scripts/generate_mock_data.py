from __future__ import annotations

import json
from pathlib import Path
from random import Random

DATA_DIR = Path(__file__).resolve().parent.parent / "mock_data"


def _market_records() -> list[dict]:
    return [
        {
            "asset_id": "tesla_model_x_2024",
            "asset_name": "Tesla Model X 2024",
            "category": "luxury_vehicle",
            "price_range": {"min": 79990, "max": 119990, "currency": "USD"},
            "historical_mean": 95000,
            "historical_stddev": 12000,
            "description": "All-electric luxury SUV.",
        },
        {
            "asset_id": "tesla_model_s_2024",
            "asset_name": "Tesla Model S 2024",
            "category": "luxury_vehicle",
            "price_range": {"min": 74990, "max": 109990, "currency": "USD"},
            "historical_mean": 89000,
            "historical_stddev": 10000,
            "description": "Premium electric sedan.",
        },
        {
            "asset_id": "porsche_911_turbo",
            "asset_name": "Porsche 911 Turbo",
            "category": "luxury_vehicle",
            "price_range": {"min": 170000, "max": 240000, "currency": "USD"},
            "historical_mean": 205000,
            "historical_stddev": 18000,
            "description": "High performance sports car.",
        },
        {
            "asset_id": "rolex_daytona_2024",
            "asset_name": "Rolex Daytona 2024",
            "category": "luxury_watch",
            "price_range": {"min": 25000, "max": 60000, "currency": "USD"},
            "historical_mean": 41000,
            "historical_stddev": 9000,
            "description": "Luxury mechanical watch.",
        },
        {
            "asset_id": "hermes_birkin_30",
            "asset_name": "Hermes Birkin 30",
            "category": "luxury_goods",
            "price_range": {"min": 12000, "max": 38000, "currency": "USD"},
            "historical_mean": 22000,
            "historical_stddev": 5000,
            "description": "High-end handbag with collector demand.",
        },
    ]


def _transactions() -> list[dict]:
    rng = Random(42)
    rows = []
    for i in range(1, 220):
        user_idx = rng.randint(1, 20)
        cp_idx = rng.randint(1000, 9999)
        amount = round(rng.uniform(3000, 120000), 2)
        rows.append(
            {
                "tx_id": f"tx_{i:05d}",
                "timestamp": f"2026-04-{(i % 28) + 1:02d}T0{(i % 9)}:12:00Z",
                "user_id": f"U{user_idx:03d}",
                "counterparty_id": f"C{cp_idx}",
                "asset_id": "tesla_model_x_2024" if i % 5 == 0 else "other_asset",
                "amount_usd": amount,
                "type": "sale" if i % 3 == 0 else "transfer",
                "counterparty_account_age_days": rng.randint(1, 365),
            }
        )

    rows.extend(
        [
            {
                "tx_id": "tx_aml_0001",
                "timestamp": "2026-05-01T09:23:11Z",
                "user_id": "U002",
                "counterparty_id": "C9821",
                "asset_id": "tesla_model_x_2024",
                "amount_usd": 1000000,
                "type": "sale",
                "counterparty_account_age_days": 3,
            },
            {
                "tx_id": "tx_aml_0002",
                "timestamp": "2026-04-28T12:10:05Z",
                "user_id": "U002",
                "counterparty_id": "C1122",
                "asset_id": "tesla_model_x_2024",
                "amount_usd": 960000,
                "type": "sale",
                "counterparty_account_age_days": 2,
            },
            {
                "tx_id": "tx_aml_0003",
                "timestamp": "2026-04-24T14:41:45Z",
                "user_id": "U002",
                "counterparty_id": "C4455",
                "asset_id": "tesla_model_x_2024",
                "amount_usd": 980000,
                "type": "sale",
                "counterparty_account_age_days": 6,
            },
        ]
    )

    return rows


def _test_cases() -> list[dict]:
    return [
        {"id": "case_01", "query": "User U002 sold a Tesla Model X for $1,000,000"},
        {"id": "case_02", "query": "Check whether user U003 may be structuring transfers"},
        {"id": "case_03", "query": "User U010 sold Rolex Daytona for $70,000"},
    ]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    market_path = DATA_DIR / "market_knowledge.jsonl"
    with market_path.open("w", encoding="utf-8") as f:
        for row in _market_records():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    (DATA_DIR / "transactions.json").write_text(
        json.dumps(_transactions(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (DATA_DIR / "test_cases.json").write_text(
        json.dumps(_test_cases(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Mock data generated in ./mock_data")


if __name__ == "__main__":
    main()
