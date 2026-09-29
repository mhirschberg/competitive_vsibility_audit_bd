"""One-record live smoke test for the two Bright Data research providers."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import time

import requests


DATASETS = {
    "chatgpt": "gd_m7aof0k82r803d5bjm",
    "gemini": "gd_mbz66arm2mf9cu856y",
}
BASE = "https://api.brightdata.com/datasets/v3"


def token_from_env():
    token = os.environ.get("BRIGHTDATA_API_TOKEN")
    if token:
        return token
    env_path = Path(__file__).resolve().parents[1] / ".env.local"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRIGHTDATA_API_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("BRIGHTDATA_API_TOKEN is missing")


def trigger(provider, prompt, country, headers):
    item = {
        "url": "https://chatgpt.com/" if provider == "chatgpt" else "https://gemini.google.com/",
        "prompt": prompt,
        "country": country,
        "index": 1,
    }
    if provider == "chatgpt":
        item["web_search"] = True
    payload = [item] if provider == "chatgpt" else {"input": [item]}
    response = requests.post(
        f"{BASE}/trigger",
        headers=headers,
        params={"dataset_id": DATASETS[provider], "format": "json", "include_errors": "true"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["snapshot_id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    prompt = (
        "Research the current German market for electric passenger cars. "
        "Name three manufacturers with battery-electric cars sold in Germany, "
        "give their official domains and one specific model each. "
        "Use current public web information, not general memory."
    )
    headers = {"Authorization": f"Bearer {token_from_env()}", "Content-Type": "application/json"}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            provider: pool.submit(trigger, provider, prompt, "DE", headers)
            for provider in DATASETS
        }
        snapshots = {}
        for provider, future in futures.items():
            try:
                snapshots[provider] = future.result()
                print(f"{provider}: triggered {snapshots[provider]}", flush=True)
            except Exception as exc:
                print(f"{provider}: trigger failed ({type(exc).__name__})", flush=True)

    pending = dict(snapshots)
    while pending and time.monotonic() - started < args.timeout:
        for provider, snapshot_id in list(pending.items()):
            try:
                response = requests.get(f"{BASE}/progress/{snapshot_id}", headers=headers, timeout=30)
                response.raise_for_status()
                status = response.json().get("status")
                if status == "ready":
                    result = requests.get(
                        f"{BASE}/snapshot/{snapshot_id}", headers=headers,
                        params={"format": "json"}, timeout=90,
                    )
                    result.raise_for_status()
                    records = result.json()
                    if isinstance(records, dict):
                        records = records.get("data") or [records]
                    record = records[0] if records else {}
                    answer = record.get("answer_text") or record.get("answer_text_markdown") or ""
                    citations = record.get("citations") or record.get("links_attached") or []
                    print(
                        f"{provider}: ready after {time.monotonic() - started:.1f}s; "
                        f"records={len(records)}, answer_chars={len(answer)}, citations={len(citations)}",
                        flush=True,
                    )
                    pending.pop(provider)
                elif status in {"failed", "canceled"}:
                    print(f"{provider}: {status} after {time.monotonic() - started:.1f}s", flush=True)
                    pending.pop(provider)
            except requests.RequestException as exc:
                print(f"{provider}: temporary {type(exc).__name__}", flush=True)
        if pending:
            time.sleep(5)
    for provider in pending:
        print(f"{provider}: still pending after {args.timeout}s ({pending[provider]})", flush=True)


if __name__ == "__main__":
    main()
