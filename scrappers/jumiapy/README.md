# `scrappers/jumiapy`

Jumia site adapter built on core components.

## Files

## `session.py`

- `JumiaSession(BaseSession)`
  - Sets `base_url` to `https://www.jumia.<domain>/`
  - Uses Jumia-specific block markers.

## `utils.py`

- `normalize_jumia_domain(country_or_domain=None)`
  - Resolves country/domain inputs like `eg` -> `com.eg`.
- `parse_jumia_product_url(url, default_domain="com.eg")`
  - Returns `(base_url, product_id)` from Jumia product URLs.
- `extract_jumia_product_id(url)`
  - Extracts numeric listing ID or SKU token (e.g. `...FAMZ`).
- `canonicalize_jumia_product_url(url, default_domain="com.eg")`
  - Normalizes product URLs to stable Jumia product/spec endpoints.
- `format_jumia_sku_url(sku, domain="com.eg")`
  - Builds canonical SKU specification URL.

## `parser.py`

Public parsing API:

- `parse_product_page(html_content, url=None, domain="com.eg")`
- `parse_search_page(html_content, base_url=None, domain="com.eg")`
- `parse_pagination_url(html_content, base_url=None)`

Strategy:

1. JSON-LD extraction when available
2. Embedded app state extraction (`__NEXT_DATA__`/preloaded state)
3. DOM card fallbacks (`article.prd`, product anchors)
4. Text enrichment for price/rating/reviews/discount fields

## `scraper.py`

- `JumiaScraper(BaseEcommerceScraper)`
  - Search URL format: `/catalog/?q=<query>`
  - Product URL normalization for HTML product pages and SKU endpoints.

## `__init__.py`

- Exports: `JumiaScraper`.
