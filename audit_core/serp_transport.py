"""Shared Bright Data SERP request and coverage decisions."""

import time
from urllib.parse import quote_plus

import requests

# SERVICE-ONLY-IMPORTS: start
from .brightdata_transport import (
    BD_REQUEST_URL, BrightDataAPIError, decode_bright_data_response,
)
# SERVICE-ONLY-IMPORTS: end


def run_resilient_serp_request(
    client, query, engine, language="en", num_results=20, *,
    normalize_serp_records, parse_bing_markdown,
):
    """Use parsed Google or Markdown Bing results; retry empty responses."""
    engine = str(engine or "").strip().lower()
    if engine not in {"google", "bing"}:
        raise ValueError(f"Unsupported search engine: {engine}")

    country = str(client.country or "US").strip().lower()
    language = str(language or "en").strip().lower()
    search_url = (
        f"https://www.{engine}.com/search"
        f"?q={quote_plus(query)}&hl={language}&gl={country}"
    )
    last_error = None

    for attempt in range(1, 4):
        operation_id = client.start_usage_operation(
            f"{engine.title()} SERP", input_count=1
        )
        response = None
        try:
            payload = {
                "zone": client.serp_zone,
                "url": search_url,
                "format": "raw",
                "method": "GET",
            }
            if engine == "google":
                payload["data_format"] = "parsed_light"
            response = requests.post(
                BD_REQUEST_URL,
                json=payload,
                headers=client.headers,
                timeout=120,
            )
            if not response.ok:
                raise BrightDataAPIError(
                    f"{engine.title()} SERP HTTP {response.status_code}: "
                    f"{response.text[:1000]}"
                )
            if not str(response.text or "").strip():
                headers = getattr(response, "headers", {}) or {}
                error_code = headers.get("x-brd-error-code", "")
                error_detail = headers.get("x-brd-error", "")
                provider_error = BrightDataAPIError(
                    f"{engine.title()} SERP empty HTTP 200; "
                    f"Bright Data error: {error_code} {error_detail}"
                )
                provider_error.selector_timeout = (
                    engine == "google"
                    and "expect_element" in f"{error_code} {error_detail}".lower()
                    and "#main" in f"{error_code} {error_detail}".lower()
                )
                raise provider_error
            if engine == "google":
                data = decode_bright_data_response(
                    response, context=f"Google SERP request for {query!r}"
                )
                parsed = normalize_serp_records(
                    data=data, query=query, engine=engine, debug=client.debug
                )
            else:
                parsed = parse_bing_markdown(
                    markdown=response.text,
                    query=query,
                    num_results=num_results,
                    requested_country=country.upper(),
                )
            parsed["results"] = [
                item for item in parsed["results"]
                if item.get("domain")
                and str(item.get("url") or "").startswith(("https://", "http://"))
                and item["domain"] not in {
                    "google.com", "bing.com", "microsoft.com"
                }
            ][:num_results]
            if not parsed["results"]:
                raise BrightDataAPIError(
                    f"{engine.title()} SERP returned no usable organic results."
                )
        except (BrightDataAPIError, requests.RequestException) as exc:
            client.update_usage_operation(operation_id, status="failed")
            last_error = exc
            if getattr(exc, "selector_timeout", False):
                break
            if response is not None and not response.ok and (
                response.status_code < 500 and response.status_code != 429
            ):
                raise
            if attempt == 3:
                break
            if client.debug:
                client.log(
                    f"{engine.title()} SERP attempt {attempt}/3 failed: "
                    f"{exc}; retrying.",
                    "yellow",
                )
            time.sleep(attempt * 2)
            continue

        parsed["search_url"] = search_url
        parsed.setdefault(
            "parser", "parsed_light" if engine == "google" else "bing_markdown"
        )
        client.update_usage_operation(
            operation_id, status="success", result_count=1
        )
        return parsed

    if getattr(last_error, "selector_timeout", False):
        raise last_error

    raise BrightDataAPIError(
        f"{engine.title()} SERP failed after 3 attempts: {last_error}"
    )


def search_result_quality(result, engine):
    """Require five organic Google results or one organic Bing result."""
    if not isinstance(result, dict):
        return "unavailable"
    usable_results = [
        item for item in result.get("results", [])
        if item.get("domain") and item.get("rank") is not None
    ]
    result_count = len(usable_results)
    engine = str(engine or "").lower()
    if engine == "google":
        return "available" if result_count >= 5 else "unavailable"
    if engine == "bing":
        return "available" if result_count >= 1 else "unavailable"
    return "unavailable"
