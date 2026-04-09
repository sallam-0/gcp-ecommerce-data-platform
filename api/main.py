import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException

try:
    import google.auth
except Exception as exc:  # pragma: no cover - import availability depends on runtime image
    google = None
    GOOGLE_AUTH_IMPORT_ERROR = exc
else:
    GOOGLE_AUTH_IMPORT_ERROR = None

try:
    from google.cloud import pubsub_v1
except Exception as exc:  # pragma: no cover - import availability depends on runtime image
    pubsub_v1 = None
    PUBSUB_IMPORT_ERROR = exc
else:
    PUBSUB_IMPORT_ERROR = None

try:
    from google.cloud import bigquery
except Exception as exc:  # pragma: no cover - import availability depends on runtime image
    bigquery = None
    BIGQUERY_IMPORT_ERROR = exc
else:
    BIGQUERY_IMPORT_ERROR = None

from api.schemas import SearchRequest, SearchResponse
from scrappers import (
    ScrapeJobConfig,
    infer_site_from_url,
    load_proxies,
    resolve_sites,
    run_with_proxy_fallback,
    summarize_attempt_metrics,
)

app = FastAPI(title="E-Commerce Scraper API", version="1.1.0")
PLACEHOLDER_NULL_STRINGS = {"", "string", "none", "null"}
PUBSUB_TOPIC_ID = os.getenv("PUBSUB_TOPIC_ID", "ecommerce-raw")
PUBSUB_PUBLISHER = None
PUBSUB_TOPIC_PATH: Optional[str] = None

BQ_CLIENT = None
BQ_PROJECT_ID = None
BQ_DATASET = None
BQ_TABLE = None


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


def _resolve_target_sites(request: SearchRequest) -> List[str]:
    if request.site == "all":
        if request.query:
            return resolve_sites(["all"])
        inferred = infer_site_from_url(request.search_url or request.product_url or "")
        if inferred:
            return [inferred]
        raise ValueError("site='all' is only supported for query mode, or URLs with a clearly inferable site.")

    if request.site:
        return [request.site]

    inferred_site = infer_site_from_url(request.search_url or request.product_url or "")
    if inferred_site:
        return [inferred_site]

    if request.query:
        return ["amazon"]

    raise ValueError("Site is required when target URL cannot be inferred.")


def _get_pubsub_publisher():
    global PUBSUB_PUBLISHER

    if PUBSUB_PUBLISHER is not None:
        return PUBSUB_PUBLISHER

    if PUBSUB_IMPORT_ERROR is not None or pubsub_v1 is None:
        raise RuntimeError(
            "google-cloud-pubsub is not installed. Install dependencies from api/requirements.txt."
        ) from PUBSUB_IMPORT_ERROR

    PUBSUB_PUBLISHER = pubsub_v1.PublisherClient()
    return PUBSUB_PUBLISHER


def _get_bigquery_client():
    global BQ_CLIENT
    if BQ_CLIENT is not None:
        return BQ_CLIENT

    if BIGQUERY_IMPORT_ERROR is not None or bigquery is None:
        raise RuntimeError(
            "google-cloud-bigquery is not installed. Install dependencies from api/requirements.txt."
        ) from BIGQUERY_IMPORT_ERROR

    BQ_CLIENT = bigquery.Client()
    return BQ_CLIENT


def _get_pubsub_topic_path() -> str:
    global PUBSUB_TOPIC_PATH

    if PUBSUB_TOPIC_PATH:
        return PUBSUB_TOPIC_PATH

    publisher = _get_pubsub_publisher()
    project_id = _sanitize_optional_text(os.getenv("GCP_PROJECT_ID")) or _sanitize_optional_text(
        os.getenv("GOOGLE_CLOUD_PROJECT")
    )

    if not project_id:
        if GOOGLE_AUTH_IMPORT_ERROR is not None or google is None:
            raise RuntimeError(
                "google-auth is not installed and project ID is not set. Set GCP_PROJECT_ID/GOOGLE_CLOUD_PROJECT."
            ) from GOOGLE_AUTH_IMPORT_ERROR
        try:
            _, inferred_project_id = google.auth.default()
            project_id = _sanitize_optional_text(inferred_project_id)
        except Exception as exc:
            raise RuntimeError(
                "Failed to resolve GCP project ID. Set GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT."
            ) from exc

    if not project_id:
        raise RuntimeError("GCP project ID is empty. Set GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT.")

    PUBSUB_TOPIC_PATH = publisher.topic_path(project_id, PUBSUB_TOPIC_ID)
    return PUBSUB_TOPIC_PATH


def _extract_payload_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _publish_to_pubsub(job_id: str, site: str, payload: Any) -> int:
    publisher = _get_pubsub_publisher()
    topic_path = _get_pubsub_topic_path()
    items = _extract_payload_items(payload)
    if not items:
        print(f"[Job {job_id}] No records to publish to Pub/Sub.")
        return 0

    futures = []
    published_at = datetime.now(timezone.utc).isoformat()

    for item in items:
        message_payload = dict(item)
        message_payload["job_id"] = job_id
        message_payload.setdefault("site", site)
        message_payload["published_at"] = published_at
        data_bytes = json.dumps(message_payload, ensure_ascii=False).encode("utf-8")

        future = publisher.publish(
            topic_path,
            data=data_bytes,
            job_id=job_id,
            site=site,
        )
        futures.append(future)

    for future in futures:
        future.result()

    return len(futures)


def _get_cached_best_match(search_term: str) -> Optional[Dict[str, Any]]:
    if not search_term:
        return None

    client = _get_bigquery_client()
    global BQ_PROJECT_ID, BQ_DATASET, BQ_TABLE
    if BQ_PROJECT_ID is None:
        BQ_PROJECT_ID = _sanitize_optional_text(
            os.getenv("BQ_PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        )
    if BQ_DATASET is None:
        BQ_DATASET = _sanitize_optional_text(os.getenv("BQ_DATASET")) or "ecommerce_prod"
    if BQ_TABLE is None:
        BQ_TABLE = _sanitize_optional_text(os.getenv("BQ_TABLE")) or "mart_best_price"

    if not BQ_PROJECT_ID:
        raise RuntimeError("BQ_PROJECT_ID (or GCP_PROJECT_ID) is not set.")

    query = f"""
        SELECT product_url, product_name, current_price, rating, image_url
        FROM `{BQ_PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}`
        WHERE LOWER(product_name) LIKE @search_term
        AND published_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY current_price ASC
        LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("search_term", "STRING", f"%{search_term.lower()}%")
        ]
    )

    query_job = client.query(query, job_config=job_config)
    rows = list(query_job)
    if not rows:
        return None
    return dict(rows[0])


def run_scraper_locally(job_id: str, request_payload: Dict[str, Any]) -> None:
    try:
        request = SearchRequest(**_sanitize_request_payload(request_payload))
        _validate_target_mode(request)
        target_sites = _resolve_target_sites(request)
        target_value = request.product_url or request.search_url or request.query
        print(f"\n[Job {job_id}] STARTING: target={target_value!r}, sites={target_sites}")

        proxy_pool = load_proxies(
            proxy=request.proxy,
            proxy_file=request.proxy_file,
            proxy_scheme=request.proxy_scheme,
        )

        max_retries = request.max_retries
        request_timeout = request.request_timeout
        min_delay = request.min_delay
        max_delay = request.max_delay
        if request.fast_mode:
            max_retries = min(max_retries, 1)
            request_timeout = min(request_timeout, 12)
            min_delay = min(min_delay, 0.6)
            max_delay = min(max_delay, 1.2)

        total_items = 0
        total_published = 0
        total_attempts = 0
        for target_site in target_sites:
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
                max_retries=max_retries,
                request_timeout=request_timeout,
                min_delay=min_delay,
                max_delay=max_delay,
                proxy_pool=proxy_pool,
            )

            result = run_with_proxy_fallback(job)
            payload = result.payload
            metrics = result.attempt_metrics
            summary = summarize_attempt_metrics(metrics)

            published_count = _publish_to_pubsub(job_id=job_id, site=target_site, payload=payload)
            if isinstance(payload, list):
                item_count = len(payload)
            elif isinstance(payload, dict) and payload:
                item_count = 1
            else:
                item_count = 0

            total_items += item_count
            total_published += published_count
            total_attempts += len(summary["attempts"])
            print(
                f"[Job {job_id}] {target_site} SUCCESS: captured {item_count} item(s), "
                f"published {published_count} message(s), attempts={len(summary['attempts'])}"
            )

        print(
            f"[Job {job_id}] SUCCESS: sites={target_sites}, captured {total_items} item(s), "
            f"published {total_published} message(s), attempts={total_attempts}"
        )

    except Exception as exc:
        print(f"[Job {job_id}] FAILED: {exc}")


@app.post("/search", response_model=SearchResponse)
async def trigger_scrape(request: SearchRequest, background_tasks: BackgroundTasks) -> SearchResponse:
    try:
        normalized_payload = _sanitize_request_payload(_model_to_dict(request))
        normalized_request = SearchRequest(**normalized_payload)

        _validate_target_mode(normalized_request)
        target_sites = _resolve_target_sites(normalized_request)
        target_value = normalized_request.product_url or normalized_request.search_url or normalized_request.query

        # Validate proxy configuration up front so bad input returns 422 immediately.
        load_proxies(
            proxy=normalized_request.proxy,
            proxy_file=normalized_request.proxy_file,
            proxy_scheme=normalized_request.proxy_scheme,
        )
        _get_pubsub_topic_path()

        # Cache check in BigQuery (best-effort).
        if target_value:
            try:
                best_match = _get_cached_best_match(target_value)
            except Exception as exc:
                print(f"Warning: BigQuery cache check failed: {exc}")
                best_match = None

            if best_match:
                print(f"Cache HIT for '{target_value}'. Returning BigQuery result.")
                return SearchResponse(
                    job_id="cached-result",
                    status="completed",
                    message="Found fresh data in historical cache.",
                    best_match=best_match,
                )
            print(f"Cache MISS for '{target_value}'. Proceeding to scrape.")

        job_id = str(uuid.uuid4())
        background_tasks.add_task(run_scraper_locally, job_id, normalized_payload)

        return SearchResponse(
            job_id=job_id,
            status="accepted",
            message=(
                f"Scraping job accepted for sites {target_sites} with target '{target_value}'. "
                f"Results will be published to Pub/Sub topic '{PUBSUB_TOPIC_ID}'. "
                "This is an async job and may take several minutes."
            ),
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
