"""Engine selection with explicit state and one-use SERP result cache."""

import time

import requests

# SERVICE-ONLY-IMPORTS: start
from .serp_transport import search_result_quality
from .brightdata_transport import BrightDataAPIError
# SERVICE-ONLY-IMPORTS: end


def choose_search_engine_core(
    self,
    test_query,
    requested_engine="auto",
    *, cache, state,
):
    """
    Select one engine for the complete audit.

    Google:
    - Up to two health checks, each with bounded transport retries

    Bing:
    - One health check with bounded transport retries
    - Either timeout/failure or a valid response
    """
    requested_engine = str(
        requested_engine
        or "auto"
    ).strip().lower()

    if requested_engine not in {
        "auto",
        "google",
        "bing",
        "none",
    }:
        raise ValueError(
            "SEARCH_ENGINE must be auto, "
            "google, bing, or none."
        )

    if requested_engine == "none":
        state["engine"] = None
        state["status"] = (
            "unavailable"
        )

        self.active_search_engine = (
            None
        )

        self.log(
            "Traditional search disabled"
        )

        return None

    # --------------------------------------------------------
    # Google: up to two health checks
    # --------------------------------------------------------

    if requested_engine in {
        "auto",
        "google",
    }:
        total_attempts = 2

        for attempt in range(
            1,
            total_attempts + 1,
        ):
            self.log(
                f"Testing Google SERP "
                f"attempt {attempt}/"
                f"{total_attempts}"
            )

            try:
                result = self.markdown_serp(
                    query=test_query,
                    engine="google",
                    num_results=20,
                )

                quality = (
                    search_result_quality(
                        result,
                        "google",
                    )
                )

                result_count = len(
                    result.get(
                        "results",
                        [],
                    )
                )

                self.log(
                    f"Google parser found "
                    f"{result_count} organic "
                    f"results; status={quality}"
                )

                if quality == "available":
                    cache[
                        (
                            "google",
                            test_query,
                        )
                    ] = result

                    state["engine"] = (
                        "google"
                    )

                    state["status"] = (
                        "available"
                    )

                    self.active_search_engine = (
                        "google"
                    )

                    self.log(
                        "Search engine selected: "
                        "Google"
                    )

                    return "google"

                self.log(
                    "Google response was incomplete "
                    "or could not be parsed.",
                    "yellow",
                )

            except Exception as exc:
                self.log(
                    f"Google attempt {attempt}/"
                    f"{total_attempts} failed: "
                    f"{exc}",
                    "yellow",
                )

            if attempt < total_attempts:
                self.log(
                    "Waiting 5 seconds before "
                    "retrying Google"
                )

                time.sleep(5)

        if requested_engine == "google":
            state["engine"] = None
            state["status"] = (
                "unavailable"
            )

            self.active_search_engine = (
                None
            )

            self.log(
                "Google unavailable after "
                "two health checks. Continuing without "
                "traditional search.",
                "yellow",
            )

            return None

    # --------------------------------------------------------
    # Bing: one request only
    # --------------------------------------------------------

    self.log(
        "Testing Bing SERP search"
    )

    try:
        result = self.markdown_serp(
            query=test_query,
            engine="bing",
            num_results=20,
        )

        quality = (
            search_result_quality(
                result,
                "bing",
            )
        )

        result_count = len(
            result.get(
                "results",
                [],
            )
        )

        self.log(
            f"Bing parser found "
            f"{result_count} organic "
            f"results; status={quality}"
        )

        if quality == "available":
            cache[
                (
                    "bing",
                    test_query,
                )
            ] = result

            state["engine"] = (
                "bing"
            )

            state["status"] = (
                "available"
            )

            self.active_search_engine = (
                "bing"
            )

            self.log(
                "Search engine selected: "
                "Bing"
            )

            return "bing"

        self.log(
            "Bing responded, but no classic "
            "organic results could be parsed.",
            "yellow",
        )

    except requests.Timeout:
        self.log(
            "Bing request timed out.",
            "yellow",
        )

    except Exception as exc:
        self.log(
            f"Bing request failed: {exc}",
            "yellow",
        )

    state["engine"] = None
    state["status"] = (
        "unavailable"
    )

    self.active_search_engine = None

    self.log(
        "Traditional search unavailable. "
        "Continuing with AI visibility "
        "and source analysis.",
        "yellow",
    )

    return None


def search_serp_core(
    self,
    query,
    engine=None,
    language="en",
    num_results=20,
    *, cache,
):
    selected_engine = str(
        engine
        or getattr(
            self,
            "active_search_engine",
            "",
        )
    ).strip().lower()

    if not selected_engine:
        raise BrightDataAPIError(
            "No search engine is active."
        )

    cache_key = (
        selected_engine,
        query,
    )

    if cache_key in (
        cache
    ):
        return (
            cache.pop(
                cache_key
            )
        )

    return self.markdown_serp(
        query=query,
        engine=selected_engine,
        language=language,
        num_results=num_results,
    )
