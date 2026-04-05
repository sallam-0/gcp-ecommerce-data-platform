# CLI Reference (`test_with_proxies.py`)

## Basic Command

```bash
python test_with_proxies.py [options] (--query ... | --search-url ... | --product-url ...)
```

## Target Selection

- `--site {amazon,noon,jumia,all}`
  - Repeatable. Default behavior is `amazon` when omitted.
  - `--site all` runs all registered sites.

## Search/Product Input

- `--query <text>`: text query mode.
- `--search-url <url>`: direct search URL mode.
- `--product-url <url>`: direct product URL mode.

## Site Context

- `--country-code <code>`
  - Amazon TLD part (example: `eg`, `com`, `in`).
  - Jumia country/domain hint (example: `eg`, `ng`, `com.eg`).
- `--locale <locale>`
  - Noon locale path (example: `egypt-en`, `saudi-en`).
- `--impersonate <fingerprint>`
  - `curl_cffi` browser impersonation (default `chrome120`).

## Crawl Limits

- `--max-pages <int>`
  - Search pages to traverse per site.
- `--max-products <int>`
  - Product cap per site per run.

## Proxy Controls

- `--proxy <entry>`
  - Repeatable inline proxy entries.
- `--proxy-file <path>`
  - One proxy per line.
- `--proxy-scheme {http,https,socks5,socks5h}`
  - Default for scheme-less entries.
- `--rotate-every <int>`
  - Change active proxy every N requests.
- `--max-proxy-attempts <int>`
  - Full run retries with different initial proxy.

## Request Tuning

- `--max-retries <int>`
- `--request-timeout <sec>`
- `--min-delay <seconds>`
- `--max-delay <seconds>`

## Output

- `--output <path>`
- `--metrics-output <path>`
- `--seed <int>`: deterministic random order for testing.

## Examples

## Amazon + Noon + Jumia in same run

```bash
python test_with_proxies.py --site all --query "iphone 17" --proxy-file proxies.txt --max-products 20
```

## Product details mode

```bash
python test_with_proxies.py --site amazon --product-url "https://www.amazon.eg/dp/B0...." --proxy-file proxies.txt
```
