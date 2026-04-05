# `scrappers/amzpy`

Amazon site adapter built on core components.

## Files

## `session.py`

- `AmzSession(BaseSession)`
  - Sets `base_url` to `https://www.amazon.<country_code>/`
  - Uses Amazon-specific block markers.

## `utils.py`

Utility helpers for Amazon URLs.

- `parse_amazon_url(url)`
  - Returns `(base_url, asin)` when possible.
- `extract_asin(url)`
  - Extracts ASIN from multiple URL forms.
- `format_canonical_url(url, asin, country_code=None)`
  - Generates canonical `/dp/<ASIN>` URL.
- `extract_brand_name(text)`
  - Parses byline text like "Visit the ... store".

## `parser.py`

Main HTML extraction logic.

- `parse_product_page(html_content, url=None, country_code=None)`
  - Extracts product-level fields:
    - `title`, `price`, `currency`, `brand`, `img_url`
    - `asin`, `product_id`, `url`
    - `rating`, `reviews_count`
- `parse_search_page(html_content, base_url=None, country_code=None)`
  - Extracts search cards with multiple selector fallbacks.
  - Handles rich fields where present:
    - pricing, discounts, rating/reviews, prime, badges, delivery, variants.
- `parse_pagination_url(html_content, base_url=None)`
  - Finds URL of next result page.

## `scraper.py`

- `AmazonScraper(BaseEcommerceScraper)`
  - Implements all abstract methods for Amazon.
  - Search URL format: `/s?k=<query>`.
  - Product URL normalization to `/dp/<ASIN>`.

## `__init__.py`

- Exports: `AmazonScraper`.
