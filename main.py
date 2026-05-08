from __future__ import annotations

import multiprocessing as mp
import time

import uvicorn
from dotenv import load_dotenv

from storage.task_store import init_db


def _serve(app_import_str: str, port: int) -> None:
    uvicorn.run(app_import_str, host="127.0.0.1", port=port, log_level="warning")


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def main() -> None:
    load_dotenv()
    init_db()

    configs = [
        ("agents.host_agent.server:app", 10000),
        ("agents.market_agent.server:app", 10001),
        ("agents.transaction_agent.server:app", 10002),
    ]

    processes = [
        mp.Process(target=_serve, args=(app_str, port), daemon=True)
        for app_str, port in configs
    ]

    for proc in processes:
        proc.start()

    labels = ["HostAgent", "MarketAgent", "TransactionAgent"]
    for (_, port), label in zip(configs, labels):
        ok = _wait_for_port(port)
        status = "✓" if ok else "⚠"
        print(f"{status} {label} listening on http://localhost:{port}")

    print("✓ SQLite initialized at ./aml.db")

    from cli.chat import run_cli
    try:
        run_cli()
    finally:
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.join(timeout=2)


if __name__ == "__main__":
    main()
