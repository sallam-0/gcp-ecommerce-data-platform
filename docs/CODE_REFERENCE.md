# Code Reference

This file documents every active source module in the repository.

## Root Files

## `test_with_proxies.py`

Entry script for running scraping with proxies and retries.

Main functions:

- `build_scraper(args, site, proxy, proxy_pool=None)`
- `run_search(scraper, args)`
- `run_product(scraper, args)`
- `run_with_proxy_fallback(args, site, proxy_pool)`
- `print_metrics_summary(attempt_metrics)`
- `parse_args()`
- `default_output_paths(args)`
- `resolve_sites(site_args)`
- `infer_site_from_url(url)`
- `normalize_result_payload(data, site)`
- `normalize_product_schema(product, site)`
- `_coerce_common_types(product)`
- `_to_float(value)`
- `_to_int(value)`
- `_enrich_common_metrics_from_text(product, text)`
- `main()`

## `scrappers/__init__.py`

- Re-export layer for package consumers.

## `scrappers/factory.py`

- `SUPPORTED_SITES = ("amazon", "noon", "jumia")`
- `create_scraper(...)`

## `scrappers/core/__init__.py`

- Re-exports core utilities and base classes.

## `scrappers/core/proxy.py`

- `SUPPORTED_PROXY_SCHEMES`
- `normalize_proxy_url(value, default_scheme="http")`
- `normalize_proxy_dict(proxy, default_scheme="http")`
- `parse_proxy_entry(raw, default_scheme="http")`
- `load_proxy_pool(proxy_args=None, proxy_file=None, default_scheme="http")`
- `mask_proxy_url(url)`
- `proxy_label(proxy_cfg)`

## `scrappers/core/session.py`

Constants:

- `DEFAULT_SESSION_CONFIG`
- `DEFAULT_BROWSER_HEADERS`
- `DEFAULT_BLOCK_MARKERS`
- `FALLBACK_USER_AGENTS`

Class:

- `BaseSession`
  - `__init__(...)`
  - `set_proxy_pool(...)`
  - `update_config(...)`
  - `get(url, headers=None)`
  - `is_blocked_response(text)`
  - `get_stats()`
  - `_maybe_rotate_proxy()`
  - `_touch_proxy_stats(metric)`
  - `_random_user_agent()`
  - `_validate_delay_range(raw_delay)`

## `scrappers/core/scraper.py`

Class:

- `BaseEcommerceScraper`
  - `__init__(country_code, session, default_config)`
  - `config(config_str=None, **kwargs)`
  - `get_product_details(url)`
  - `search_products(query=None, search_url=None, max_pages=1, max_products=None)`
  - abstract methods for site adapters:
    - `site_base_url()`
    - `build_search_url(query)`
    - `normalize_product_url(url)`
    - `parse_product_html(html_content, url)`
    - `parse_search_html(html_content)`
    - `parse_next_page_url(html_content)`

## `scrappers/amzpy/__init__.py`

- Exports `AmazonScraper`.

## `scrappers/amzpy/session.py`

- `DEFAULT_CONFIG`
- `AMAZON_BLOCK_MARKERS`
- `AmzSession(BaseSession)`

## `scrappers/amzpy/utils.py`

- `parse_amazon_url(url)`
- `extract_asin(url)`
- `format_canonical_url(url, asin, country_code=None)`
- `extract_brand_name(text)`

## `scrappers/amzpy/parser.py`

Public parsing API:

- `parse_product_page(html_content, url=None, country_code=None)`
- `parse_search_page(html_content, base_url=None, country_code=None)`
- `parse_pagination_url(html_content, base_url=None)`

Highlights:

- Extensive selector fallback coverage for changing Amazon layouts.
- CAPTCHA/block detection short-circuit.
- Canonical ASIN URL formatting.
- Extracts optional rich fields such as discounts, ratings, review counts, prime status, badges, and delivery text.

## `scrappers/amzpy/scraper.py`

Class:

- `AmazonScraper(BaseEcommerceScraper)`
  - `site_base_url()`
  - `build_search_url(query)`
  - `normalize_product_url(url)`
  - `parse_product_html(html_content, url)`
  - `parse_search_html(html_content)`
  - `parse_next_page_url(html_content)`

## `scrappers/noonpy/__init__.py`

- Exports `NoonScraper`.

## `scrappers/noonpy/session.py`

- `DEFAULT_CONFIG`
- `NOON_BLOCK_MARKERS`
- `NoonSession(BaseSession)`

## `scrappers/noonpy/utils.py`

- `parse_noon_product_url(url, locale=None)`
- `format_noon_product_url(product_id, locale="egypt-en")`

## `scrappers/noonpy/parser.py`

Public parsing API:

- `parse_product_page(html_content, url=None, locale="egypt-en")`
- `parse_search_page(html_content, base_url=None, locale="egypt-en")`
- `parse_pagination_url(html_content, base_url=None)`

Internal helpers:

- block detection and payload extraction:
  - `_is_blocked_html`, `_extract_json_ld_payloads`, `_extract_next_data`, `_iter_dicts`
- product transformation:
  - `_build_search_product_from_object`, `_merge_product_page_fields`, `_merge_meta_fields`
- field parsers:
  - `_extract_brand`, `_extract_image`, `_extract_price_currency`, `_extract_price_currency_from_candidate`
  - `_as_float`, `_as_int`, `_parse_count_token`
- fallback enrichment:
  - `_enrich_product_from_text_blob`, `_clean_title_from_blob`

## `scrappers/noonpy/scraper.py`

Class:

- `NoonScraper(BaseEcommerceScraper)`
  - `site_base_url()`
  - `build_search_url(query)`
  - `normalize_product_url(url)`
  - `parse_product_html(html_content, url)`
  - `parse_search_html(html_content)`
  - `parse_next_page_url(html_content)`

## `scrappers/jumiapy/__init__.py`

- Exports `JumiaScraper`.

## `scrappers/jumiapy/session.py`

- `DEFAULT_CONFIG`
- `JUMIA_BLOCK_MARKERS`
- `JumiaSession(BaseSession)`

## `scrappers/jumiapy/utils.py`

- `normalize_jumia_domain(country_or_domain=None)`
- `parse_jumia_product_url(url, default_domain="com.eg")`
- `extract_jumia_product_id(url)`
- `canonicalize_jumia_product_url(url, default_domain="com.eg")`
- `format_jumia_sku_url(sku, domain="com.eg")`

## `scrappers/jumiapy/parser.py`

Public parsing API:

- `parse_product_page(html_content, url=None, domain="com.eg")`
- `parse_search_page(html_content, base_url=None, domain="com.eg")`
- `parse_pagination_url(html_content, base_url=None)`

Highlights:

- JSON-LD + app-state extraction.
- Jumia card selector parsing (`article.prd` / product anchors).
- URL normalization for numeric listing URLs and SKU spec URLs.
- Shared field extraction for `price`, `currency`, `rating`, `reviews_count`, and merchandising flags.

## `scrappers/jumiapy/scraper.py`

Class:

- `JumiaScraper(BaseEcommerceScraper)`
  - `site_base_url()`
  - `build_search_url(query)`
  - `normalize_product_url(url)`
  - `parse_product_html(html_content, url)`
  - `parse_search_html(html_content)`
  - `parse_next_page_url(html_content)`
