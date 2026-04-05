from .factory import SUPPORTED_SITES, create_scraper, get_scraper
from .service import (
    ScrapeExecutionResult,
    ScrapeJobConfig,
    infer_site_from_url,
    load_proxies,
    normalize_result_payload,
    resolve_sites,
    run_with_proxy_fallback,
    summarize_attempt_metrics,
)

__all__ = [
    "SUPPORTED_SITES",
    "create_scraper",
    "get_scraper",
    "ScrapeExecutionResult",
    "ScrapeJobConfig",
    "infer_site_from_url",
    "load_proxies",
    "normalize_result_payload",
    "resolve_sites",
    "run_with_proxy_fallback",
    "summarize_attempt_metrics",
]
