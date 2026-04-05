# GCP Ecommerce Data Platform (Scrapers)

This repository contains a modular scraping framework for ecommerce search/product extraction, with current adapters for:

- Amazon (`scrappers/amzpy`)
- Noon (`scrappers/noonpy`)
- Jumia (`scrappers/jumiapy`)

It includes a shared proxy-aware HTTP/session layer, a reusable base scraper flow, and a CLI test runner that can scrape one or multiple sites in the same run.

## Project Structure

```text
.
|-- test_with_proxies.py
|-- proxies.txt
|-- scrappers/
|   |-- __init__.py
|   |-- factory.py
|   |-- core/
|   |   |-- __init__.py
|   |   |-- proxy.py
|   |   |-- session.py
|   |   `-- scraper.py
|   |-- amzpy/
|   |   |-- __init__.py
|   |   |-- utils.py
|   |   |-- session.py
|   |   |-- parser.py
|   |   `-- scraper.py
|   |-- jumiapy/
|   |   |-- __init__.py
|   |   |-- utils.py
|   |   |-- session.py
|   |   |-- parser.py
|   |   `-- scraper.py
|   `-- noonpy/
|       |-- __init__.py
|       |-- utils.py
|       |-- session.py
|       |-- parser.py
|       `-- scraper.py
`-- docs/
    |-- CLI_REFERENCE.md
    |-- CODE_REFERENCE.md
    `-- DATA_SCHEMA.md
```

## How The System Works

1. `test_with_proxies.py` parses CLI arguments and target sites.
2. Proxy pool is loaded from `--proxy` and/or `--proxy-file` via `scrappers.core.proxy`.
3. `scrappers.factory.create_scraper()` instantiates site scraper(s).
4. Site scraper inherits `BaseEcommerceScraper` and calls shared flow:
   - build search URL
   - fetch pages through `BaseSession`
   - parse products via site parser
   - normalize results in the CLI
5. Result and metrics JSON files are saved.

## Quick Start

## 1) Install dependencies

```bash
pip install curl-cffi fake-useragent beautifulsoup4 lxml
```

## 2) Scrape Amazon

```bash
python test_with_proxies.py --site amazon --query "iphone 17" --country-code eg --proxy-file proxies.txt
```

## 3) Scrape Noon

```bash
python test_with_proxies.py --site noon --query "iphone 17" --locale egypt-en --proxy-file proxies.txt
```

## 4) Scrape both in one run

```bash
python test_with_proxies.py --site all --query "iphone 17" --proxy-file proxies.txt --max-products 20
```

## 5) Scrape Jumia

```bash
python test_with_proxies.py --site jumia --query "iphone 17" --country-code eg --proxy-file proxies.txt
```

## Output Files

- Single-site defaults:
  - `<site>_proxy_test_results.json`
  - `<site>_proxy_test_metrics.json`
- Multi-site defaults:
  - `multi_site_proxy_test_results.json`
  - `multi_site_proxy_test_metrics.json`

## Documentation Index

- High-level package docs:
  - `scrappers/README.md`
  - `scrappers/core/README.md`
  - `scrappers/amzpy/README.md`
  - `scrappers/jumiapy/README.md`
  - `scrappers/noonpy/README.md`
- Detailed references:
  - `docs/README.md`
  - `docs/CLI_REFERENCE.md`
  - `docs/CODE_REFERENCE.md`
  - `docs/DATA_SCHEMA.md`

## Notes

- Folder name intentionally uses `scrappers` (double `p`) to match current code imports.
- Some site pages can still require selector tuning when providers change markup.
