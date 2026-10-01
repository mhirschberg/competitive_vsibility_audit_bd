"""Service-side Bright Data snapshot client built from shared transports.

This is the first provider adapter extracted for the service-native runner.
It owns credentials, result accounting, and the effective snapshot operations;
it deliberately does not import or execute the generated notebook.
"""

import asyncio
import json

from audit_core.brightdata_transport import (
    CHATGPT_DATASET_ID,
    COPILOT_DATASET_ID,
    FAILED_STATUSES,
    GEMINI_DATASET_ID,
    GOOGLE_AI_MODE_DATASET_ID,
    GOOGLE_AI_OUTPUT_FIELDS,
    BD_PROGRESS_URL,
    BD_REQUEST_URL,
    BD_SCRAPE_URL,
    BD_SNAPSHOT_URL,
    BD_TRIGGER_URL,
    BrightDataAPIError,
    SnapshotTimeoutError,
    reliable_download_snapshot,
    reliable_scrape_dataset,
    reliable_snapshot_status,
    reliable_trigger_dataset,
    wait_for_snapshot,
)
from audit_core.serp_transport import search_result_quality
from audit_core.brightdata_usage import BrightDataUsageLedger
from audit_core.ai_visibility_race import race_ai_visibility_core
from audit_core.ai_localization import (
    AI_LOCALIZATION_RACE_ATTEMPTS,
    STRICT_AI_COUNTRY_VALIDATION,
    annotate_country_transport,
    apply_compatible_country_payload,
    country_details,
    localize_google_ai_prompt_core,
    race_localized_ai_visibility,
)
from audit_core.domains import canonical_source_url, get_root_domain
from audit_core.serp_parsing import normalize_parsed_serp_records
from audit_core.serp_selection import choose_search_engine_core, search_serp_core
from audit_core.serp_transport import run_resilient_serp_request


class BrightDataProviderClient(BrightDataUsageLedger):
    """Credential-bearing provider adapter with shared usage accounting."""

    def __init__(
        self, token, serp_zone, country="US", debug=False, logger=None,
        parse_bing_markdown=None,
    ):
        super().__init__()
        self.token = str(token or "").strip()
        self.serp_zone = str(serp_zone or "").strip()
        self.country = str(country or "US").strip().upper()
        self.debug = bool(debug)
        self._logger = logger or (lambda _message, _style="dim": None)
        self._parse_bing_markdown = parse_bing_markdown
        self._serp_cache = {}
        self._search_state = {"engine": None, "status": "unavailable"}
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.active_search_engine = None

    def log(self, message, style="dim"):
        if self.debug:
            self._logger(message, style)

    @staticmethod
    def normalize_records(data):
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "results", "records"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        return []

    @staticmethod
    def answer_text(record):
        if not isinstance(record, dict):
            return str(record or "").strip()
        value = (
            record.get("answer_text_markdown")
            or record.get("answer_text")
            or record.get("answer_markdown")
            or record.get("answer")
            or record.get("response")
            or record.get("text")
            or ""
        )
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value or "").strip()

    def google_ai_mode_measured(self, prompt, timeout_seconds=720):
        """Request a measured Google AI Mode answer through this provider."""
        localized_prompt = localize_google_ai_prompt_core(
            prompt, country_details(self.country),
        )
        payload = {
            "input": [{
                "url": "https://google.com/aimode",
                "prompt": localized_prompt,
                "country": self.country,
            }]
        }
        records = self.scrape_dataset(
            dataset_id=GOOGLE_AI_MODE_DATASET_ID,
            payload=payload,
            timeout_seconds=timeout_seconds,
            custom_output_fields=GOOGLE_AI_OUTPUT_FIELDS,
        )
        for record in records:
            if self.answer_text(record):
                return record
        raise BrightDataAPIError(
            "Google AI Mode returned no answer text."
        )

    def _engine_payload(self, engine, prompt, request_index, web_search=True):
        item = {
            "prompt": prompt,
            "country": self.country,
            "index": request_index,
        }
        if engine == "chatgpt":
            item.update({"url": "https://chatgpt.com/", "web_search": web_search})
            dataset_id, payload = CHATGPT_DATASET_ID, [item]
        elif engine == "gemini":
            item["url"] = "https://gemini.google.com/"
            dataset_id, payload = GEMINI_DATASET_ID, {"input": [item]}
        elif engine == "copilot":
            item["url"] = "https://copilot.microsoft.com/chats"
            dataset_id, payload = COPILOT_DATASET_ID, [item]
        else:
            raise ValueError(f"Unknown AI engine: {engine}")
        apply_compatible_country_payload(payload, engine, self.country)
        return dataset_id, payload

    def race_ai_engine(
        self, engine, prompt, redundancy=3, timeout_seconds=600,
    ):
        def race_once(client, selected_engine, localized_prompt, count, timeout):
            return race_ai_visibility_core(
                client, selected_engine, localized_prompt, count, timeout,
                failed_statuses=FAILED_STATUSES,
                canonical_source_url=canonical_source_url,
            )

        result = race_localized_ai_visibility(
            self, engine, prompt, redundancy, timeout_seconds,
            race_once=race_once,
            details=country_details(self.country),
            attempts=AI_LOCALIZATION_RACE_ATTEMPTS,
            strict=STRICT_AI_COUNTRY_VALIDATION,
        )
        return annotate_country_transport(result, engine, self.country)

    def normalize_serp_records(self, data, query, engine, debug=False):
        return normalize_parsed_serp_records(
            data, query, engine, debug,
            get_root_domain=get_root_domain,
            log=self.log,
        )

    def markdown_serp(self, query, engine, language="en", num_results=20):
        if engine == "bing" and self._parse_bing_markdown is None:
            raise RuntimeError(
                "Bing Markdown parser must be supplied by the service adapter."
            )
        return run_resilient_serp_request(
            self, query, engine, language, num_results,
            normalize_serp_records=self.normalize_serp_records,
            parse_bing_markdown=self._parse_bing_markdown,
        )

    async def run_keyword_serp_task(
        self, keyword, semaphore, num_results=20, search_engine=None,
    ):
        """Measure one keyword with the audit's outer SERP quality retry."""
        async with semaphore:
            engine = str(search_engine or "").lower()
            max_attempts = 2 if engine == "google" else 1
            last_error = None
            attempt = 0

            for attempt in range(1, max_attempts + 1):
                try:
                    response = await asyncio.to_thread(
                        self.search_serp,
                        keyword,
                        engine,
                        "en",
                        num_results,
                    )
                    if search_result_quality(response, engine) != "available":
                        raise BrightDataAPIError(
                            f"{engine.title()} returned no usable organic results."
                        )
                    return {
                        "keyword": keyword,
                        "engine": engine,
                        "success": True,
                        "results": response.get("results", []),
                        "raw_result_count": response.get("raw_result_count", 0),
                        "requested_country": response.get("requested_country"),
                        "observed_country": response.get("observed_country"),
                        "localization_warning": response.get(
                            "localization_warning", False,
                        ),
                        "attempt": attempt,
                        "error": None,
                    }
                except Exception as exc:
                    last_error = exc
                    self.log(
                        f"{engine.title()} attempt {attempt}/{max_attempts} "
                        f"failed for {keyword!r}: {exc}",
                        "yellow",
                    )
                    if getattr(exc, "selector_timeout", False):
                        break
                    if engine == "google" and attempt < max_attempts:
                        self.log(f"Waiting 5 seconds before retrying {keyword!r}")
                        await asyncio.sleep(5)

            return {
                "keyword": keyword,
                "engine": engine,
                "success": False,
                "results": [],
                "raw_result_count": 0,
                "attempt": attempt,
                "error": str(last_error),
            }

    def choose_search_engine(self, test_query, requested_engine="auto"):
        return choose_search_engine_core(
            self, test_query, requested_engine,
            cache=self._serp_cache, state=self._search_state,
        )

    def search_serp(self, query, engine=None, language="en", num_results=20):
        return search_serp_core(
            self, query, engine, language, num_results, cache=self._serp_cache,
        )

    snapshot_status = reliable_snapshot_status
    download_snapshot = reliable_download_snapshot
    trigger_dataset = reliable_trigger_dataset
    scrape_dataset = reliable_scrape_dataset
    wait_for_snapshot = wait_for_snapshot


__all__ = [
    "BD_PROGRESS_URL",
    "BD_REQUEST_URL",
    "BD_SCRAPE_URL",
    "BD_SNAPSHOT_URL",
    "BD_TRIGGER_URL",
    "BrightDataAPIError",
    "BrightDataProviderClient",
    "SnapshotTimeoutError",
]
