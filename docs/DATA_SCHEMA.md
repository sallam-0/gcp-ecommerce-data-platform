# Data Schema

This project emits normalized product objects so multi-site outputs are easier to consume.

## Result Shapes

- Single-site run: JSON `list[product]` (search) or `product` (detail)
- Multi-site run: JSON object:

```json
{
  "amazon": [ ... ],
  "noon": [ ... ],
  "jumia": [ ... ]
}
```

## Normalized Product Fields

Core fields (common target schema):

- `site` (`"amazon" | "noon" | "jumia"`)
- `product_id` (ASIN for Amazon, Noon product ID for Noon, numeric listing ID or SKU for Jumia)
- `asin` (ASIN for Amazon, nullable for non-Amazon)
- `title`
- `title_raw`
- `url`

Common commerce/reputation fields (when available):

- `price`
- `original_price`
- `currency`
- `rating`
- `reviews_count`
- `discount_percent`

Optional merchandising fields (site-dependent, available when present):

- `img_url`
- `brand`
- `prime`
- `badge`
- `free_delivery`
- `selling_out_fast`
- `stock_left`
- `sold_recently`
- `category_rank` (object with `rank` and `category`)

## Metrics File Schema

Each attempt stores:

- `attempt`
- `site`
- `entry_proxy`
- `session_stats`

`session_stats` includes:

- `requests_total`
- `responses_ok`
- `responses_non_200`
- `network_errors`
- `captcha_blocks`
- `last_status_code`
- `success_rate`
- `captcha_rate`
- `proxy_stats` (per-proxy counters + derived rates)
