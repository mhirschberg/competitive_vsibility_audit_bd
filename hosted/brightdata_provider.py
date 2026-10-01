"""Service-side Bright Data snapshot client built from shared transports.

This is the first provider adapter extracted for the service-native runner.
It owns credentials, result accounting, and the effective snapshot operations;
it deliberately does not import or execute the generated notebook.
"""

import json

from audit_core.brightdata_transport import (
    CHATGPT_DATASET_ID,
    COPILOT_DATASET_ID,
    FAILED_STATUSES,
    GEMINI_DATASET_ID,
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
from audit_core.brightdata_usage import BrightDataUsageLedger
from audit_core.ai_visibility_race import race_ai_visibility_core
from audit_core.ai_localization import (
    AI_LOCALIZATION_RACE_ATTEMPTS,
    STRICT_AI_COUNTRY_VALIDATION,
    annotate_country_transport,
    apply_compatible_country_payload,
    country_details,
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
        parse_bing_markdown=None, remove_ai_boilerplate=None,
    ):
        super().__init__()
        self.token = str(token or "").strip()
        self.serp_zone = str(serp_zone or "").strip()
        self.country = str(country or "US").strip().upper()
        self.debug = bool(debug)
        self._logger = logger or (lambda _message, _style="dim": None)
        self._parse_bing_markdown = parse_bing_markdown
        self._remove_ai_boilerplate = remove_ai_boilerplate or (lambda text: text)
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

    def generate_chatgpt_report(self, prompt, timeout_seconds=600):
        """Generate the final narrative through the same counted snapshot API."""
        dataset_id, payload = self._engine_payload(
            "chatgpt", prompt, request_index=1, web_search=False
        )
        snapshot_id = self.trigger_dataset(dataset_id, payload)
        records = self.wait_for_snapshot(
            snapshot_id, timeout_seconds=timeout_seconds
        )
        for record in records:
            answer = self.answer_text(record)
            if answer:
                return {
                    "snapshot_id": snapshot_id,
                    "answer": self._remove_ai_boilerplate(answer),
                    "record": record,
                }
        raise BrightDataAPIError(
            "Final ChatGPT snapshot returned no report text."
        )

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
