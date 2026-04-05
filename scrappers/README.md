# `scrappers` Package

This package is the modular scraping engine.

## Purpose

- Provide reusable scraping primitives (`core`)
- Provide site adapters (`amzpy`, `noonpy`, `jumiapy`)
- Provide one factory entrypoint for site creation (`factory.py`)

## Main Modules

- `scrappers/__init__.py`
  - Exports `SUPPORTED_SITES` and `create_scraper`.
- `scrappers/factory.py`
  - Maps `site` name -> concrete scraper class.

## Design Pattern

- Shared infrastructure lives in `core`.
- Site-specific parsing/URL logic lives in site folder.
- CLI uses the factory and does not need to know parser internals.

## Adding A New Site (Summary)

1. Create folder: `scrappers/<newsite>py/`.
2. Add:
   - `utils.py` for URL parsing/canonicalization
   - `session.py` extending `BaseSession`
   - `parser.py` with `parse_product_page`, `parse_search_page`, `parse_pagination_url`
   - `scraper.py` extending `BaseEcommerceScraper`
   - `__init__.py` exporting scraper
3. Register in `scrappers/factory.py` and `SUPPORTED_SITES`.
4. Run through `test_with_proxies.py` with `--site <newsite>`.
