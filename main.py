from __future__ import annotations

import multiprocessing as mp
import socket
import time

import uvicorn
from dotenv import load_dotenv

from storage.task_store import init_db


def _serve(app_import_str: str, port: int) -> None:
    uvicorn.run(app_import_str, host="127.0.0.1", port=port, log_level="warning")


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
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
    labels = ["HostAgent", "MarketAgent", "TransactionAgent"]

    # Fail fast if any port is already occupied by a previous run
    blocked = [
        (label, port)
        for (_, port), label in zip(configs, labels)
        if not _is_port_free(port)
    ]
    if blocked:
        for label, port in blocked:
            print(f"✗ Port {port} ({label}) is already in use — stop the previous run first.")
        return

    processes = [
        mp.Process(target=_serve, args=(app_str, port), daemon=True)
        for app_str, port in configs
    ]

    for proc in processes:
        proc.start()

    for proc, (_, port), label in zip(processes, configs, labels):
        ok = _wait_for_port(port)
        alive = proc.is_alive()
        if ok and alive:
            print(f"✓ {label} listening on http://localhost:{port}")
        elif ok and not alive:
            print(f"✗ {label}: process exited unexpectedly (port {port} may be taken by another process)")
        else:
            print(f"⚠  {label}: did not respond on port {port}")

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
