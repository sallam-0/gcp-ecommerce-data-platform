import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.schemas import SearchRequest, SearchResponse
from scrappers import (
    ScrapeJobConfig,
    infer_site_from_url,
    load_proxies,
    run_with_proxy_fallback,
    summarize_attempt_metrics,
)

app = FastAPI(title="E-Commerce Scraper API (Local Mode)", version="1.0.0")
PLACEHOLDER_NULL_STRINGS = {"", "string", "none", "null"}


def _model_to_dict(model: SearchRequest) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _validate_target_mode(request: SearchRequest) -> None:
    selected_targets = [bool(request.query), bool(request.search_url), bool(request.product_url)]
    if sum(selected_targets) != 1:
        raise ValueError("Provide exactly one of query, search_url, or product_url.")


def _sanitize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.lower() in PLACEHOLDER_NULL_STRINGS:
        return None
    return cleaned


def _sanitize_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    normalized["site"] = _sanitize_optional_text(normalized.get("site"))
    normalized["query"] = _sanitize_optional_text(normalized.get("query"))
    normalized["search_url"] = _sanitize_optional_text(normalized.get("search_url"))
    normalized["product_url"] = _sanitize_optional_text(normalized.get("product_url"))
    normalized["proxy_file"] = _sanitize_optional_text(normalized.get("proxy_file"))

    raw_proxy_values = normalized.get("proxy") or []
    cleaned_proxy_values = []
    for value in raw_proxy_values:
        cleaned = _sanitize_optional_text(value)
        if cleaned:
            cleaned_proxy_values.append(cleaned)
    normalized["proxy"] = cleaned_proxy_values
    return normalized


def _resolve_target_site(request: SearchRequest) -> str:
    if request.site:
        return request.site

    inferred_site = infer_site_from_url(request.search_url or request.product_url or "")
    if inferred_site:
        return inferred_site

    if request.query:
        return "amazon"

    raise ValueError("Site is required when target URL cannot be inferred.")


def run_scraper_locally(job_id: str, request_payload: Dict[str, Any]) -> None:
    try:
        request = SearchRequest(**_sanitize_request_payload(request_payload))
        _validate_target_mode(request)
        target_site = _resolve_target_site(request)
        target_value = request.product_url or request.search_url or request.query
        print(f"\n[Job {job_id}] STARTING: target={target_value!r}, site={target_site}")

        proxy_pool = load_proxies(
            proxy=request.proxy,
            proxy_file=request.proxy_file,
            proxy_scheme=request.proxy_scheme,
        )

        job = ScrapeJobConfig(
            site=target_site,
            query=request.query,
            search_url=request.search_url,
            product_url=request.product_url,
            country_code=request.country_code,
            locale=request.locale,
            impersonate=request.impersonate,
            max_pages=request.max_pages,
            max_products=request.max_products,
            max_proxy_attempts=request.max_proxy_attempts,
            rotate_every=request.rotate_every,
            max_retries=request.max_retries,
            request_timeout=request.request_timeout,
            min_delay=request.min_delay,
            max_delay=request.max_delay,
            proxy_pool=proxy_pool,
        )

        result = run_with_proxy_fallback(job)
        payload = result.payload
        metrics = result.attempt_metrics

        data_path = Path(f"local_test_{job_id}.json")
        metrics_path = Path(f"local_test_{job_id}_metrics.json")
        data_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

        summary = summarize_attempt_metrics(metrics)
        if isinstance(payload, list):
            item_count = len(payload)
        elif isinstance(payload, dict) and payload:
            item_count = 1
        else:
            item_count = 0

        print(f"[Job {job_id}] SUCCESS: captured {item_count} item(s).")
        print(f"[Job {job_id}] DATA FILE: {data_path}")
        print(f"[Job {job_id}] METRICS FILE: {metrics_path}")
        print(f"[Job {job_id}] ATTEMPTS: {len(summary['attempts'])}")

    except Exception as exc:
        print(f"[Job {job_id}] FAILED: {exc}")


@app.post("/search", response_model=SearchResponse)
async def trigger_scrape(request: SearchRequest, background_tasks: BackgroundTasks) -> SearchResponse:
    try:
        normalized_payload = _sanitize_request_payload(_model_to_dict(request))
        normalized_request = SearchRequest(**normalized_payload)

        _validate_target_mode(normalized_request)
        target_site = _resolve_target_site(normalized_request)
        target_value = normalized_request.product_url or normalized_request.search_url or normalized_request.query

        # Validate proxy configuration up front so bad input returns 422 immediately.
        load_proxies(
            proxy=normalized_request.proxy,
            proxy_file=normalized_request.proxy_file,
            proxy_scheme=normalized_request.proxy_scheme,
        )

        job_id = str(uuid.uuid4())
        background_tasks.add_task(run_scraper_locally, job_id, normalized_payload)

        return SearchResponse(
            job_id=job_id,
            status="accepted",
            message=f"Local scraping job started for {target_site} with target '{target_value}'.",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
