#!/usr/bin/env python3
"""
Proxy-aware CLI runner that uses reusable scraper orchestration from scrappers.service.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scrappers import (
    SUPPORTED_SITES,
    ScrapeJobConfig,
    infer_site_from_url,
    load_proxies,
    resolve_sites,
    run_with_proxy_fallback,
    summarize_attempt_metrics,
)
from scrappers.core.proxy import SUPPORTED_PROXY_SCHEMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Proxy-aware runner for modular scrappers")
    parser.add_argument(
        "--site",
        action="append",
        choices=[*SUPPORTED_SITES, "all"],
        default=None,
        help="Target ecommerce site. Repeat for multiple sites, or use 'all'.",
    )

    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--query", help="Search query text")
    target_group.add_argument("--search-url", help="Direct search URL")
    target_group.add_argument("--product-url", help="Product URL for product-details mode")

    parser.add_argument(
        "--country-code",
        default="eg",
        help="Amazon TLD (e.g. com, eg, in) and Jumia country/domain hint (e.g. eg, ng, com.eg)",
    )
    parser.add_argument("--locale", default="egypt-en", help="Noon locale path (e.g. egypt-en, saudi-en)")
    parser.add_argument("--impersonate", default="chrome120", help="curl_cffi browser fingerprint")
    parser.add_argument("--max-pages", type=int, default=1, help="Max search pages to scrape")
    parser.add_argument("--max-products", type=int, default=50, help="Max products to keep per site in one run")

    parser.add_argument("--proxy", action="append", help="Proxy entry (repeatable)")
    parser.add_argument("--proxy-file", help="Text file with one proxy entry per line")
    parser.add_argument(
        "--proxy-scheme",
        choices=sorted(SUPPORTED_PROXY_SCHEMES),
        default="http",
        help="Default scheme for proxy entries without scheme (host:port)",
    )
    parser.add_argument("--rotate-every", type=int, default=1, help="Rotate proxy every N requests")
    parser.add_argument("--max-proxy-attempts", type=int, default=3, help="Retries with different starting proxies")

    parser.add_argument("--max-retries", type=int, default=3, help="HTTP retries inside site session")
    parser.add_argument("--request-timeout", type=int, default=25, help="Request timeout (seconds)")
    parser.add_argument("--min-delay", type=float, default=2.5, help="Minimum random delay between requests")
    parser.add_argument("--max-delay", type=float, default=4.0, help="Maximum random delay between requests")

    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--metrics-output", default=None, help="Output JSON path for ban/proxy metrics")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible proxy order")
    return parser.parse_args()


def default_output_paths(args: argparse.Namespace) -> Tuple[Path, Path]:
    sites = resolve_sites(args.site)
    if len(sites) == 1:
        result_name = args.output or f"{sites[0]}_proxy_test_results.json"
        metrics_name = args.metrics_output or f"{sites[0]}_proxy_test_metrics.json"
        return Path(result_name), Path(metrics_name)

    result_name = args.output or "multi_site_proxy_test_results.json"
    metrics_name = args.metrics_output or "multi_site_proxy_test_metrics.json"
    return Path(result_name), Path(metrics_name)


def print_metrics_summary(attempt_metrics: List[Dict[str, Any]]) -> None:
    summary = summarize_attempt_metrics(attempt_metrics)
    attempts = summary["attempts"]
    if not attempts:
        return

    print("\n=== Ban/Proxy Metrics Summary ===")
    for item in attempts:
        print(
            f"Attempt {item['attempt']} ({item['entry_proxy']}): "
            f"requests={item['requests_total']}, success_rate={item['success_rate']:.2%}, "
            f"captcha_rate={item['captcha_rate']:.2%}, non_200={item['responses_non_200']}, "
            f"network_errors={item['network_errors']}"
        )

    per_proxy = summary["per_proxy"]
    if per_proxy:
        print("Per-proxy:")
        for proxy_name, data in per_proxy.items():
            print(
                f"  {proxy_name}: requests={int(data['requests'])}, "
                f"success_rate={data['success_rate']:.2%}, captcha_rate={data['captcha_rate']:.2%}"
            )


def _build_job(args: argparse.Namespace, site: str, proxy_pool: List[Dict[str, str]]) -> ScrapeJobConfig:
    return ScrapeJobConfig(
        site=site,
        query=args.query,
        search_url=args.search_url,
        product_url=args.product_url,
        country_code=args.country_code,
        locale=args.locale,
        impersonate=args.impersonate,
        max_pages=args.max_pages,
        max_products=args.max_products,
        max_proxy_attempts=args.max_proxy_attempts,
        rotate_every=args.rotate_every,
        max_retries=args.max_retries,
        request_timeout=args.request_timeout,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        proxy_pool=proxy_pool,
    )


def main() -> None:
    args = parse_args()
    sites = resolve_sites(args.site)

    if args.seed is not None:
        random.seed(args.seed)

    proxy_pool = load_proxies(args.proxy, args.proxy_file, proxy_scheme=args.proxy_scheme)
    if proxy_pool:
        print(f"Loaded {len(proxy_pool)} proxy entries.")
    else:
        print("No proxy configured. Running direct requests.")

    output_path, metrics_path = default_output_paths(args)

    url_target = args.search_url or args.product_url
    if url_target and len(sites) > 1:
        guessed = infer_site_from_url(url_target)
        if guessed in sites:
            print(f"URL looks site-specific ({guessed}), so this run will target only: {guessed}")
            sites = [guessed]

    if len(sites) == 1:
        target_site = sites[0]
        result = run_with_proxy_fallback(_build_job(args, target_site, proxy_pool))
        data = result.payload
        attempt_metrics = result.attempt_metrics

        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved output to: {output_path}")

        metrics_path.write_text(json.dumps(attempt_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved metrics to: {metrics_path}")
        print_metrics_summary(attempt_metrics)

        if isinstance(data, list):
            print(f"Total products in output: {len(data)}")
        elif isinstance(data, dict):
            identifier = data.get("asin") or data.get("product_id") or data.get("id")
            print(f"Saved product id: {identifier}")
        else:
            print("No data captured (possibly blocked on all attempts).")
    else:
        multi_results: Dict[str, Any] = {}
        multi_metrics: Dict[str, List[Dict[str, Any]]] = {}

        for site in sites:
            print(f"\n================ {site.upper()} ================")
            result = run_with_proxy_fallback(_build_job(args, site, proxy_pool))
            multi_results[site] = result.payload
            multi_metrics[site] = result.attempt_metrics
            print_metrics_summary(result.attempt_metrics)

        output_path.write_text(json.dumps(multi_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved multi-site output to: {output_path}")

        metrics_path.write_text(json.dumps(multi_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved multi-site metrics to: {metrics_path}")


if __name__ == "__main__":
    main()
