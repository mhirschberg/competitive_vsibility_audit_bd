"""Normalize parsed-light SERP records without notebook globals."""


def find_parsed_organic_results(data):
    """Locate organic records across the supported parsed response shapes."""
    if isinstance(data, list):
        for item in data:
            found = core_find_parsed_organic_results(item)
            if found:
                return found
        return []
    if not isinstance(data, dict):
        return []

    for field_name in (
        "organic", "organic_results", "results", "web_results", "webPages"
    ):
        value = data.get(field_name)
        if field_name == "webPages" and isinstance(value, dict):
            value = value.get("value", [])
        if isinstance(value, list) and value:
            return value

    for value in data.values():
        if isinstance(value, (dict, list)):
            found = core_find_parsed_organic_results(value)
            if found:
                return found
    return []


core_find_parsed_organic_results = find_parsed_organic_results


def normalize_parsed_serp_records(
    data, query, engine, debug=False, *, get_root_domain,
    log=None, extract_result_url=None, extract_result_domain=None,
):
    """Convert parsed-light records to the audit's common SERP shape."""
    organic = core_find_parsed_organic_results(data)
    results = []
    for position, item in enumerate(organic, start=1):
        if not isinstance(item, dict):
            continue
        result_url = (
            extract_result_url(item)
            if extract_result_url is not None
            else str(
                item.get("link") or item.get("url") or item.get("href") or ""
            ).strip()
        )
        domain = (
            extract_result_domain(item, result_url)
            if extract_result_domain is not None
            else get_root_domain(result_url or item.get("domain") or "")
        )
        if not result_url and domain:
            result_url = f"https://{domain}/"
        if debug and not domain and log is not None:
            log(
                f"{engine.title()} result had no domain. Query={query!r}; "
                f"fields={list(item.keys())}; record={str(item)[:600]}",
                "yellow",
            )

        raw_rank = (
            item.get("rank") or item.get("position")
            or item.get("global_rank") or item.get("ranking") or position
        )
        try:
            rank = int(raw_rank)
        except Exception:
            rank = position
        results.append({
            "rank": rank,
            "title": str(
                item.get("title") or item.get("name")
                or item.get("headline") or ""
            ).strip(),
            "url": result_url,
            "domain": domain,
            "description": str(
                item.get("description") or item.get("snippet")
                or item.get("text") or item.get("caption") or ""
            ).strip(),
        })
    return {
        "query": query,
        "engine": engine,
        "results": results,
        "raw_result_count": len(organic),
    }
