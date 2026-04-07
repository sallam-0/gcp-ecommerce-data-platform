"""
Reusable orchestration helpers for running site scrapers in app code and CLI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from .core.proxy import SUPPORTED_PROXY_SCHEMES, load_proxy_pool, proxy_label
from .factory import SUPPORTED_SITES, create_scraper

ProxyConfig = Dict[str, str]


@dataclass
class ScrapeJobConfig:
    site: str
    query: Optional[str] = None
    search_url: Optional[str] = None
    product_url: Optional[str] = None
    country_code: str = "eg"
    locale: str = "egypt-en"
    impersonate: str = "chrome120"
    max_pages: int = 1
    max_products: int = 50
    max_proxy_attempts: int = 3
    rotate_every: int = 1
    max_retries: int = 3
    request_timeout: int = 25
    min_delay: float = 2.5
    max_delay: float = 4.0
    proxy_pool: List[ProxyConfig] = field(default_factory=list)

    def normalized_site(self) -> str:
        site_name = (self.site or "").strip().lower()
        if site_name not in SUPPORTED_SITES:
            supported = ", ".join(SUPPORTED_SITES)
            raise ValueError(f"Unsupported site '{self.site}'. Supported values: {supported}")
        return site_name

    def validate_target(self) -> None:
        selected_targets = [bool(self.query), bool(self.search_url), bool(self.product_url)]
        if sum(selected_targets) != 1:
            raise ValueError("Provide exactly one of query, search_url, or product_url.")


@dataclass
class ScrapeExecutionResult:
    site: str
    payload: Any
    attempt_metrics: List[Dict[str, Any]]


def load_proxies(
    proxy: Optional[Sequence[str]] = None,
    proxy_file: Optional[str] = None,
    proxy_scheme: str = "http",
) -> List[ProxyConfig]:
    scheme = (proxy_scheme or "").strip().lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        allowed = ", ".join(sorted(SUPPORTED_PROXY_SCHEMES))
        raise ValueError(f"Unsupported proxy scheme '{proxy_scheme}'. Supported: {allowed}")
    return load_proxy_pool(proxy_args=proxy, proxy_file=proxy_file, default_scheme=scheme)


def resolve_sites(site_args: Optional[Sequence[str]]) -> List[str]:
    if not site_args:
        return ["amazon"]

    lowered = [value.strip().lower() for value in site_args if value and value.strip()]
    if "all" in lowered:
        return list(SUPPORTED_SITES)

    unique: List[str] = []
    for site in lowered:
        if site not in SUPPORTED_SITES:
            supported = ", ".join(SUPPORTED_SITES)
            raise ValueError(f"Unsupported site '{site}'. Supported values: {supported}")
        if site not in unique:
            unique.append(site)
    return unique or ["amazon"]


def infer_site_from_url(url: str) -> Optional[str]:
    if not url:
        return None

    host = urlparse(url).netloc.lower()
    if "amazon." in host:
        return "amazon"
    if "noon.com" in host:
        return "noon"
    if "jumia." in host:
        return "jumia"
    return None


def run_with_proxy_fallback(job: ScrapeJobConfig) -> ScrapeExecutionResult:
    site = job.normalized_site()
    job.validate_target()

    attempts = max(1, int(job.max_proxy_attempts))
    configured_proxy_pool = list(job.proxy_pool or [])
    entry_proxies: List[Optional[ProxyConfig]] = configured_proxy_pool or [None]

    last_payload: Any = {} if job.product_url else []
    attempt_metrics: List[Dict[str, Any]] = []

    for attempt_index in range(attempts):
        entry_proxy = entry_proxies[attempt_index % len(entry_proxies)]
        scraper = _build_scraper(job, site, entry_proxy, configured_proxy_pool)
        raw_payload = _run_scrape(scraper, job)
        normalized_payload = normalize_result_payload(raw_payload, site)
        last_payload = normalized_payload

        attempt_metrics.append(
            {
                "attempt": attempt_index + 1,
                "site": site,
                "entry_proxy": proxy_label(entry_proxy) if entry_proxy else "direct",
                "session_stats": scraper.session.get_stats(),
            }
        )

        if _has_usable_payload(normalized_payload):
            return ScrapeExecutionResult(
                site=site,
                payload=normalized_payload,
                attempt_metrics=attempt_metrics,
            )

    return ScrapeExecutionResult(site=site, payload=last_payload, attempt_metrics=attempt_metrics)


def summarize_attempt_metrics(attempt_metrics: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    attempts_summary: List[Dict[str, Any]] = []
    per_proxy: Dict[str, Dict[str, float]] = {}

    for item in attempt_metrics:
        stats = item.get("session_stats", {})
        attempts_summary.append(
            {
                "attempt": item.get("attempt"),
                "entry_proxy": item.get("entry_proxy", "direct"),
                "requests_total": stats.get("requests_total", 0),
                "success_rate": stats.get("success_rate", 0.0),
                "captcha_rate": stats.get("captcha_rate", 0.0),
                "responses_non_200": stats.get("responses_non_200", 0),
                "network_errors": stats.get("network_errors", 0),
            }
        )

        for proxy_name, proxy_stats in stats.get("proxy_stats", {}).items():
            if proxy_name not in per_proxy:
                per_proxy[proxy_name] = {"requests": 0, "successes": 0, "captcha_blocks": 0}
            per_proxy[proxy_name]["requests"] += proxy_stats.get("requests", 0)
            per_proxy[proxy_name]["successes"] += proxy_stats.get("successes", 0)
            per_proxy[proxy_name]["captcha_blocks"] += proxy_stats.get("captcha_blocks", 0)

    for data in per_proxy.values():
        requests_total = data["requests"]
        data["success_rate"] = (data["successes"] / requests_total) if requests_total else 0.0
        data["captcha_rate"] = (data["captcha_blocks"] / requests_total) if requests_total else 0.0

    return {"attempts": attempts_summary, "per_proxy": per_proxy}


def normalize_result_payload(data: Any, site: str) -> Any:
    if isinstance(data, list):
        return [normalize_product_schema(item, site) for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return normalize_product_schema(data, site)
    return data


def normalize_product_schema(product: Dict[str, Any], site: str) -> Dict[str, Any]:
    normalized = dict(product)
    normalized["site"] = site

    if site == "amazon":
        asin = normalized.get("asin") or normalized.get("product_id")
        if asin:
            normalized["product_id"] = asin
    else:
        product_id = normalized.get("product_id") or normalized.get("sku") or normalized.get("id")
        if product_id:
            normalized["product_id"] = product_id

    # Normalize away legacy asin field for all sites.
    normalized.pop("asin", None)

    if "title_raw" not in normalized and isinstance(normalized.get("title"), str):
        normalized["title_raw"] = normalized["title"]

    _enrich_common_metrics_from_text(normalized, normalized.get("title_raw") or normalized.get("title") or "")
    _coerce_common_types(normalized)
    return normalized


def _build_scraper(
    job: ScrapeJobConfig,
    site: str,
    entry_proxy: Optional[ProxyConfig],
    proxy_pool: Sequence[ProxyConfig],
):
    scraper = create_scraper(
        site=site,
        country_code=job.country_code,
        locale=job.locale,
        impersonate=job.impersonate,
        proxies=entry_proxy,
    )

    scraper.config(
        MAX_RETRIES=job.max_retries,
        REQUEST_TIMEOUT=job.request_timeout,
        DELAY_BETWEEN_REQUESTS=(job.min_delay, job.max_delay),
    )

    if proxy_pool:
        scraper.session.set_proxy_pool(proxy_pool, rotate_every=job.rotate_every, start_random=True)

    return scraper


def _run_scrape(scraper: Any, job: ScrapeJobConfig) -> Any:
    if job.product_url:
        return scraper.get_product_details(job.product_url)
    if job.search_url:
        return scraper.search_products(
            search_url=job.search_url,
            max_pages=job.max_pages,
            max_products=job.max_products,
        )
    return scraper.search_products(
        query=job.query,
        max_pages=job.max_pages,
        max_products=job.max_products,
    )


def _has_usable_payload(payload: Any) -> bool:
    if isinstance(payload, list):
        return bool(payload)
    if isinstance(payload, dict):
        return bool(payload)
    return payload is not None


def _coerce_common_types(product: Dict[str, Any]) -> None:
    float_fields = ["price", "original_price", "rating"]
    int_fields = ["reviews_count", "discount_percent", "stock_left", "sold_recently"]

    for field in float_fields:
        if field in product and product[field] is not None:
            value = _to_float(product[field])
            if value is not None:
                product[field] = value

    for field in int_fields:
        if field in product and product[field] is not None:
            value = _to_int(product[field])
            if value is not None:
                product[field] = value


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.,-]", "", value).replace(",", "")
        if not cleaned or cleaned in {".", "-", "-."}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)([KkMm]?)", value.replace(",", ""))
        if not match:
            return None
        number = float(match.group(1))
        suffix = match.group(2).upper()
        if suffix == "K":
            number *= 1000
        elif suffix == "M":
            number *= 1_000_000
        return int(number)
    return None


def _enrich_common_metrics_from_text(product: Dict[str, Any], text: str) -> None:
    blob = " ".join((text or "").split())
    if not blob:
        return

    if "currency" not in product:
        currency_match = re.search(r"\b(EGP|AED|SAR|USD|EUR|GBP)\b", blob, flags=re.IGNORECASE)
        if currency_match:
            product["currency"] = currency_match.group(1).upper()

    if "price" not in product:
        price_match = re.search(
            r"(?:\b(EGP|AED|SAR|USD|EUR|GBP)\s*|\$)([0-9][0-9,]*(?:\.[0-9]+)?)",
            blob,
            flags=re.IGNORECASE,
        )
        if price_match:
            product["price"] = _to_float(price_match.group(2))
            if price_match.group(1):
                product.setdefault("currency", price_match.group(1).upper())

    if "rating" not in product:
        rating_match = re.search(r"\b([1-5](?:\.\d)?)\s*(?:out of 5|stars?)?\b", blob, flags=re.IGNORECASE)
        if rating_match:
            rating = _to_float(rating_match.group(1))
            if rating is not None:
                product["rating"] = rating

    if "reviews_count" not in product:
        reviews_match = re.search(
            r"\b([0-9]+(?:\.[0-9]+)?[KkMm]?)\s*(?:reviews?|ratings?)\b",
            blob,
            flags=re.IGNORECASE,
        )
        if reviews_match:
            reviews_count = _to_int(reviews_match.group(1))
            if reviews_count is not None:
                product["reviews_count"] = reviews_count
