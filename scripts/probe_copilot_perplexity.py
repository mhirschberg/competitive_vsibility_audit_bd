"""Small, reproducible live check of Bright Data's two answer-engine scrapers.

Only public prompts and returned answers are saved. The API token is never logged.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import requests

from probe_research_providers import token_from_env


BASE = "https://api.brightdata.com/datasets/v3"
PROVIDERS = {
    "perplexity": {
        "dataset_id": "gd_m7dhdot1vw9a7gc1n",
        "url": "https://www.perplexity.ai",
    },
    "copilot": {
        "dataset_id": "gd_m7di5jy6s9geokz8w",
        "url": "https://copilot.microsoft.com/chats",
    },
}
CASES = {
    "simple_control": {
        "country": "",
        "prompt": "What is the capital of Germany? Cite one source.",
    },
    "smartphones_us": {
        "country": "US",
        "prompt": (
            "Which premium smartphones should a buyer in the United States "
            "compare right now? Explain the main trade-offs and cite sources."
        ),
    },
    "automation_de": {
        "country": "DE",
        "prompt": (
            "Which providers of machine tool automation should a midsize "
            "manufacturer in Germany compare? Explain the differences and cite sources."
        ),
    },
    "used_cars_de": {
        "country": "DE",
        "prompt": (
            "Where can someone in Germany buy or sell a used car online? "
            "Compare the main options and cite sources."
        ),
    },
}


def records_from_snapshot(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    return []


def compact_record(record):
    plain_answer = record.get("answer_text") or ""
    answer = record.get("answer_text_markdown") or plain_answer
    sources = record.get("sources") or record.get("citations") or []
    if not isinstance(sources, list):
        sources = []
    return {
        "url": record.get("url"),
        "country": record.get("country"),
        "timestamp": record.get("timestamp"),
        "answer": answer,
        "answer_chars": len(answer),
        "plain_answer": plain_answer,
        "plain_answer_chars": len(plain_answer),
        "sources": [
            {
                "url": source.get("url"),
                "title": source.get("title"),
                "cited": source.get("cited"),
                "position": source.get("position"),
            }
            for source in sources
            if isinstance(source, dict)
        ],
        "error": record.get("error") or record.get("error_message"),
        "record_keys": sorted(record),
    }


def run_one(provider, case_name, session, timeout):
    config = PROVIDERS[provider]
    case = CASES[case_name]
    started = time.monotonic()
    result = {
        "provider": provider,
        "case": case_name,
        "country_requested": case["country"],
        "prompt": case["prompt"],
    }
    try:
        response = session.post(
            f"{BASE}/trigger",
            params={"dataset_id": config["dataset_id"], "format": "json", "include_errors": "true"},
            json=[{"url": config["url"], "prompt": case["prompt"], "country": case["country"], "index": 1}],
            timeout=60,
        )
        result["trigger_http_status"] = response.status_code
        response.raise_for_status()
        snapshot_id = response.json().get("snapshot_id")
        if not snapshot_id:
            result["error"] = "No snapshot_id in trigger response"
            result["trigger_response"] = response.text[:1000]
            return result
        result["snapshot_id"] = snapshot_id
        print(f"{provider}/{case_name}: triggered {snapshot_id}", flush=True)
        while time.monotonic() - started < timeout:
            response = session.get(f"{BASE}/progress/{snapshot_id}", timeout=30)
            response.raise_for_status()
            status = response.json().get("status")
            result["status"] = status
            if status == "ready":
                response = session.get(
                    f"{BASE}/snapshot/{snapshot_id}",
                    params={"format": "json"}, timeout=90,
                )
                result["snapshot_http_status"] = response.status_code
                response.raise_for_status()
                records = records_from_snapshot(response.json())
                result["records"] = [compact_record(record) for record in records if isinstance(record, dict)]
                break
            if status in {"failed", "canceled"}:
                break
            time.sleep(5)
        else:
            result["status"] = "pending_at_timeout"
    except (requests.RequestException, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 1)
        first = (result.get("records") or [{}])[0]
        print(
            f"{provider}/{case_name}: {result.get('status', 'error')} "
            f"in {result['elapsed_seconds']}s; "
            f"answer_chars={first.get('answer_chars', 0)}; "
            f"sources={len(first.get('sources', []))}",
            flush=True,
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="+", choices=sorted(CASES), default=[
        "smartphones_us", "automation_de", "used_cars_de",
    ])
    parser.add_argument("--providers", nargs="+", choices=sorted(PROVIDERS), default=list(PROVIDERS))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (
        Path(__file__).resolve().parents[1]
        / "local-runs" / f"copilot-perplexity-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    )
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token_from_env()}",
        "Content-Type": "application/json",
    })
    tasks = [(provider, case) for case in args.cases for provider in args.providers]
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = [pool.submit(run_one, provider, case, session, args.timeout) for provider, case in tasks]
        results = [future.result() for future in as_completed(futures)]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Results saved to {output}", flush=True)


if __name__ == "__main__":
    main()
