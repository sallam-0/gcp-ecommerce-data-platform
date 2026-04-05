# `scrappers/core`

Shared core components used by all site implementations.

## Files

## `proxy.py`

Handles proxy parsing, validation, masking, and loading.

- `SUPPORTED_PROXY_SCHEMES`
  - Allowed schemes: `http`, `https`, `socks5`, `socks5h`.
- `normalize_proxy_url(value, default_scheme="http")`
  - Ensures scheme/hostname are valid.
- `normalize_proxy_dict(proxy, default_scheme="http")`
  - Normalizes dict-based proxies; supports `all=` shorthand.
- `parse_proxy_entry(raw, default_scheme="http")`
  - Parses one proxy from JSON, key=value list, or raw URL.
- `load_proxy_pool(proxy_args=None, proxy_file=None, default_scheme="http")`
  - Loads proxies from CLI and/or file.
- `mask_proxy_url(url)`
  - Hides credentials for logs.
- `proxy_label(proxy_cfg)`
  - Returns safe display label for a proxy.

## `session.py`

Contains HTTP behavior and anti-ban mechanics.

- `DEFAULT_SESSION_CONFIG`
  - `MAX_RETRIES`, `REQUEST_TIMEOUT`, `DELAY_BETWEEN_REQUESTS`, `DEFAULT_IMPERSONATE`.
- `BaseSession`
  - Main reusable session class.

### `BaseSession` behavior

- User-agent rotation per request.
- Proxy pool rotation with `rotate_every`.
- Retry loop for network failures / server errors.
- Block-marker detection (captcha/verify text).
- Per-run + per-proxy metrics collection.

Key methods:

- `set_proxy_pool(...)`
- `update_config(...)`
- `get(url, headers=None)`
- `is_blocked_response(text)`
- `get_stats()`

## `scraper.py`

Abstract base flow for search/detail scraping.

- `BaseEcommerceScraper`
  - Owns common run loop.

Core methods:

- `config(config_str=None, **kwargs)`
  - Updates runtime session config.
- `get_product_details(url)`
  - URL normalize -> fetch -> parse.
- `search_products(query=None, search_url=None, max_pages=1, max_products=None)`
  - Multi-page search crawl with optional product cap.

Required abstract methods each site must implement:

- `site_base_url()`
- `build_search_url(query)`
- `normalize_product_url(url)`
- `parse_product_html(html_content, url)`
- `parse_search_html(html_content)`
- `parse_next_page_url(html_content)`
