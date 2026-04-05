# `scrappers/noonpy`

Noon site adapter built on core components.

## Files

## `session.py`

- `NoonSession(BaseSession)`
  - Sets `base_url` to `https://www.noon.com/<locale>/`
  - Uses Noon-specific block markers.

## `utils.py`

- `parse_noon_product_url(url, locale=None)`
  - Returns `(base_url, product_id)` from Noon product URL.
- `format_noon_product_url(product_id, locale="egypt-en")`
  - Builds canonical Noon product URL.

## `parser.py`

Uses a layered parsing strategy:

1. JSON-LD extraction (preferred)
2. `__NEXT_DATA__` traversal
3. Anchor/text fallback parsing

Public functions:

- `parse_product_page(html_content, url=None, locale="egypt-en")`
- `parse_search_page(html_content, base_url=None, locale="egypt-en")`
- `parse_pagination_url(html_content, base_url=None)`

Key private helpers:

- JSON/data extraction:
  - `_extract_json_ld_payloads`, `_extract_next_data`, `_iter_dicts`
- object field extraction:
  - `_extract_brand`, `_extract_image`, `_extract_price_currency`
- fallback enrichment from text blobs:
  - `_enrich_product_from_text_blob`
  - `_clean_title_from_blob`
  - `_parse_count_token`

Common fields produced (when present):

- identifiers: `product_id`, `url`
- catalog: `title`, `brand`, `img_url`
- commerce: `price`, `original_price`, `discount_percent`, `currency`
- social proof: `rating`, `reviews_count`
- merchandising: `badge`, `category_rank`, `free_delivery`, `sold_recently`, `stock_left`

## `scraper.py`

- `NoonScraper(BaseEcommerceScraper)`
  - Search URL format: `/search?q=<query>`
  - Product URL normalization to canonical Noon `/p/` URL.

## `__init__.py`

- Exports: `NoonScraper`.
