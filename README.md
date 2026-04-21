
# GCP E-Commerce Data Platform

**A production-grade, end-to-end data pipeline that aggregates product data from multiple e-commerce marketplaces, streams it through Google Cloud, and transforms it into query-ready analytics tables.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Google Cloud](https://img.shields.io/badge/Google%20Cloud-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/)
[![Apache Beam](https://img.shields.io/badge/Apache%20Beam-FF6F00?logo=apachebeam&logoColor=white)](https://beam.apache.org/)
[![dbt](https://img.shields.io/badge/dbt-FF694B?logo=dbt&logoColor=white)](https://www.getdbt.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Core Components](#core-components)
  - [Scraper Engine](#1-scraper-engine)
  - [API Service](#2-api-service)
  - [Stream Processor](#3-stream-processor)
  - [Transform Layer (dbt)](#4-transform-layer-dbt)
- [Data Model](#data-model)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running the Scraper CLI](#running-the-scraper-cli)
  - [Running the API](#running-the-api)
  - [Running the Stream Processor](#running-the-stream-processor)
  - [Running dbt Transformations](#running-dbt-transformations)
- [Deployment](#deployment)
  - [API — Cloud Run Service](#api--cloud-run-service)
  - [dbt — Cloud Run Job](#dbt--cloud-run-job)
  - [Stream Processor — Dataflow](#stream-processor--dataflow)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

This platform solves a real-world problem: **comparing product prices and metadata across multiple e-commerce marketplaces in near real-time.** It scrapes product listings from **Amazon**, **Noon**, and **Jumia**, normalizes the data into a unified schema, streams it into a data warehouse, and transforms it into analytics-ready tables for price comparison, trend analysis, and product intelligence.

### Key Capabilities

| Capability | Description |
|---|---|
| **Multi-Site Scraping** | Concurrent scraping of Amazon, Noon, and Jumia with site-specific parsers |
| **Anti-Bot Resilience** | Proxy rotation, browser fingerprint impersonation via `curl_cffi`, CAPTCHA detection, and automatic retry with exponential backoff |
| **Real-Time Streaming** | Google Cloud Pub/Sub ingestion with Apache Beam / Dataflow for continuous processing |
| **Dual-Sink Architecture** | Every scraped record is persisted to both BigQuery (structured) and GCS (raw JSON data lake) |
| **Incremental Transforms** | dbt models with incremental merge strategies ensure deduplication and efficient warehouse updates |
| **Cache-First API** | The REST API checks BigQuery for recent results before triggering a new scrape, reducing latency and cost |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT REQUEST                                 │
│                         POST /search (FastAPI)                              │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │    BigQuery Cache Check  │
                    │   (mart_best_price)      │
                    └────┬──────────────┬──────┘
                         │              │
                    Cache HIT      Cache MISS
                    (return)            │
                                        │
          ┌─────────────────────────────▼──────────────────────────────┐
          │               SCRAPER ENGINE (Background Task)             │
          │  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
          │  │ Amazon   │  │  Noon    │  │  Jumia   │                  │
          │  │ (amzpy)  │  │ (noonpy) │  │(jumiapy) │                  │
          │  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
          │       └─────────────┼─────────────┘                        │
          │                     │                                      │
          │          Schema Normalization                              │
          │          (service.py)                                      │
          └─────────────────────┬──────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Google Cloud Pub/Sub│
                    │   (ecommerce-raw)     │
                    └───────────┬───────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │   Apache Beam / Dataflow Pipeline  │
              │        (stream_processor.py)       │
              └──────┬────────────────────┬────────┘
                     │                    │
          ┌──────────▼──────────┐  ┌──────▼───────────────┐
          │   BigQuery          │  │   GCS Data Lake      │
          │   raw_scrapes       │  │   (windowed JSON)    │
          └──────────┬──────────┘  └──────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   dbt Transform     │
          │   (Cloud Run Job)   │
          │                     │
          │  stg_raw_scrapes    │  ← Staging view (JSON extraction)
          │  mart_best_price    │  ← Incremental merge (deduplicated)
          └─────────────────────┘
```

### Data Flow Sequence

1. A client sends a `POST /search` request to the FastAPI service with a query, site, and scraping parameters.
2. The API first performs a **cache lookup** against the `mart_best_price` BigQuery table for results published within the last 7 days.
3. On a **cache hit**, the API returns the cached result immediately — no scraping occurs.
4. On a **cache miss**, the API generates a unique `job_id`, enqueues the scraping work as a **background task**, and returns an `accepted` response to the client.
5. The background task runs the scraper engine, which creates site-specific scraper instances via the **factory pattern**, executes HTTP requests through a proxy-aware session, and parses the HTML responses.
6. Each parsed product record is **normalized** into a unified schema and **published** to Google Cloud Pub/Sub with metadata (`job_id`, `site`, `published_at`).
7. The **Dataflow streaming pipeline** continuously consumes Pub/Sub messages and writes them to two sinks in parallel:
   - **BigQuery `raw_scrapes`** — structured rows with extracted metadata and the full raw JSON payload.
   - **GCS data lake** — windowed JSON files (5-minute fixed windows) for archival and batch reprocessing.
8. A **dbt Cloud Run Job** is executed on schedule (or on-demand) to transform raw data through staging and into the final mart table, applying deduplication and incremental merge logic.

---

## Repository Structure

```
.
├── api/
│   ├── main.py                  # FastAPI application — routing, cache, Pub/Sub publish
│   ├── schemas.py               # Pydantic request/response models
│   └── requirements.txt         # Python dependencies for the API and scrapers
│
├── scrappers/
│   ├── __init__.py              # Public API surface for the scraper package
│   ├── factory.py               # Factory function to instantiate site-specific scrapers
│   ├── service.py               # Orchestration layer — proxy fallback, normalization, metrics
│   ├── core/
│   │   ├── scraper.py           # BaseEcommerceScraper abstract class
│   │   ├── session.py           # HTTP session with retry, rotation, fingerprinting
│   │   └── proxy.py             # Proxy parsing, normalization, and pool management
│   ├── amzpy/
│   │   ├── scraper.py           # AmazonScraper implementation
│   │   ├── session.py           # Amazon-specific session configuration
│   │   ├── parser.py            # Amazon HTML parsing (search + product pages)
│   │   └── utils.py             # Amazon URL construction and helpers
│   ├── noonpy/
│   │   ├── scraper.py           # NoonScraper implementation
│   │   ├── session.py           # Noon-specific session configuration
│   │   ├── parser.py            # Noon HTML parsing (search + product pages)
│   │   └── utils.py             # Noon URL construction and helpers
│   └── jumiapy/
│       ├── scraper.py           # JumiaScraper implementation
│       ├── session.py           # Jumia-specific session configuration
│       ├── parser.py            # Jumia HTML parsing (search + product pages)
│       └── utils.py             # Jumia URL construction and helpers
│
├── ecommerce_transform/
│   ├── dbt_project.yml          # dbt project configuration
│   ├── profiles.yml             # dbt connection profile (env-var driven)
│   ├── Dockerfile               # Container image for dbt Cloud Run Job
│   └── models/
│       ├── source.yml           # BigQuery source declarations
│       ├── staging/
│       │   └── stg_raw_scrapes.sql   # Staging view — JSON field extraction
│       └── mart/
│           └── mart_best_price.sql   # Incremental mart — deduplication + merge
│
├── stream_processor.py          # Apache Beam streaming pipeline (Pub/Sub → BQ + GCS)
├── test_with_proxies.py         # CLI tool for local scraping with proxy support
├── Dockerfile                   # Cloud Run API container image
├── .env                         # Environment variables for Dataflow configuration
└── docs/                        # Supplementary reference documentation
```

---

## Core Components

### 1. Scraper Engine

**Location:** `scrappers/`

The scraper engine is a modular, extensible system built on a shared abstract base class. Each supported marketplace has its own adapter package that implements site-specific HTML parsing, URL construction, and session management.

#### Architecture

```
scrappers/
├── core/                        # Shared infrastructure
│   ├── BaseEcommerceScraper     # Abstract base defining the scraping contract
│   ├── BaseSession              # HTTP session with retry, proxy rotation, fingerprinting
│   └── Proxy utilities          # Proxy URL parsing, normalization, pool management
│
├── factory.py                   # create_scraper("amazon") → AmazonScraper instance
├── service.py                   # High-level orchestration with proxy fallback
│
└── {amzpy, noonpy, jumiapy}/    # Site-specific implementations
    ├── scraper.py               # Concrete scraper (extends BaseEcommerceScraper)
    ├── session.py               # Site-tuned session (base URL, headers, block markers)
    ├── parser.py                # HTML parsing with BeautifulSoup + lxml
    └── utils.py                 # URL builders & site-specific helpers
```

#### `BaseEcommerceScraper` (Abstract Base)

Defines the contract that all site scrapers must implement:

| Method | Purpose |
|---|---|
| `site_base_url()` | Returns the root URL for the marketplace |
| `build_search_url(query)` | Constructs a search results URL from query text |
| `normalize_product_url(url)` | Canonicalizes a product URL or returns `None` if invalid |
| `parse_product_html(html, url)` | Parses a single product page into a structured dictionary |
| `parse_search_html(html, max_products)` | Parses a search results page into a list of product dictionaries |
| `parse_next_page_url(html)` | Extracts the next-page URL for pagination |

The base class also provides shared flow logic:
- **`search_products()`** — iterates through paginated search results up to `max_pages`, stopping early when `max_products` is reached to minimize cloud execution time and cost.
- **`get_product_details()`** — fetches and parses a single product page.

#### `BaseSession` (HTTP Session Layer)

The session layer handles all HTTP communication with enterprise-grade resilience:

| Feature | Implementation |
|---|---|
| **Browser Impersonation** | Uses `curl_cffi` to impersonate real browser TLS fingerprints (e.g., `chrome120`) |
| **User-Agent Rotation** | Randomizes `User-Agent` headers on every request via `fake_useragent` |
| **Proxy Pool Rotation** | Round-robin or random proxy switching every N requests |
| **CAPTCHA Detection** | Scans response HTML for block markers (`captcha`, `verify you are human`, `access denied`, `bot check`) |
| **Retry with Backoff** | Automatic retry on 5xx errors and CAPTCHA blocks with increasing delay multipliers |
| **Per-Proxy Metrics** | Tracks request count, success rate, and CAPTCHA rate for each proxy endpoint |
| **Cookie Seeding** | Pre-fetches the site homepage on session init to seed cookies before scraping |

#### Proxy System

The proxy module supports multiple input formats and schemes:

- **Schemes:** `http`, `https`, `socks5`, `socks5h`
- **Formats:** plain URL, `key=value` pairs, JSON dictionaries, or a proxy file (one entry per line)
- **Credential Masking:** Proxy URLs are automatically masked in logs to prevent credential leakage

#### Orchestration Service (`service.py`)

The service layer sits above individual scrapers and provides:

- **`run_with_proxy_fallback()`** — runs a scrape job with automatic retry using different entry proxies from the pool. If the first proxy fails or gets blocked, it rotates to the next.
- **`normalize_result_payload()`** — normalizes heterogeneous field names across sites into a unified schema (e.g., `asin` → `product_id`, `title` → `title_raw`).
- **`summarize_attempt_metrics()`** — aggregates per-attempt and per-proxy statistics for observability.
- **Type coercion** — safely converts price, rating, and review count fields from various string formats to native types, handling currency symbols, commas, and K/M suffixes.

#### Supported Marketplaces

| Site | Package | Country/Locale Support |
|---|---|---|
| **Amazon** | `scrappers/amzpy/` | Country code for TLD (e.g., `eg` → `amazon.eg`, `com` → `amazon.com`) |
| **Noon** | `scrappers/noonpy/` | Locale path (e.g., `egypt-en`, `saudi-en`, `uae-en`) |
| **Jumia** | `scrappers/jumiapy/` | Country code for domain (e.g., `eg` → `jumia.com.eg`, `ng` → `jumia.com.ng`) |

---

### 2. API Service

**Location:** `api/`

A production-ready RESTful API built with FastAPI that serves as the primary interface for triggering scrape jobs and retrieving results.

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/search` | Trigger a product search across one or more e-commerce sites |
| `GET` | `/docs` | Interactive Swagger UI documentation |

#### Request Model (`SearchRequest`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `site` | `amazon \| noon \| jumia \| all` | Auto-inferred | Target marketplace(s). Use `all` for cross-site search. |
| `query` | `string` | — | Free-text search query (mutually exclusive with URL modes) |
| `search_url` | `string` | — | Direct search results URL to scrape |
| `product_url` | `string` | — | Single product page URL to scrape |
| `country_code` | `string` | `eg` | Amazon TLD / Jumia country hint |
| `locale` | `string` | `egypt-en` | Noon locale path |
| `impersonate` | `string` | `chrome120` | `curl_cffi` browser fingerprint to impersonate |
| `max_pages` | `int` | `1` | Maximum number of search result pages to scrape |
| `max_products` | `int` | `50` | Maximum products to return per site |
| `proxy` | `list[string]` | `[]` | Inline proxy entries |
| `proxy_file` | `string` | — | Path to a file containing proxy entries |
| `proxy_scheme` | `string` | `http` | Default scheme for `host:port` proxy entries |
| `rotate_every` | `int` | `1` | Rotate proxy every N requests |
| `max_proxy_attempts` | `int` | `3` | Number of retries with different entry proxies |
| `max_retries` | `int` | `3` | HTTP retries within a session |
| `request_timeout` | `int` | `25` | Request timeout in seconds |
| `min_delay` | `float` | `2.5` | Minimum delay between requests (seconds) |
| `max_delay` | `float` | `4.0` | Maximum delay between requests (seconds) |
| `fast_mode` | `bool` | `false` | Reduces retries/delays for faster responses |

#### Response Model (`SearchResponse`)

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "accepted | completed",
  "message": "Descriptive status message",
  "best_match": {
    "product_url": "...",
    "product_name": "...",
    "current_price": 449.99,
    "rating": 4.5,
    "image_url": "..."
  }
}
```

- **`status: completed`** — returned on cache hit with the `best_match` object populated.
- **`status: accepted`** — returned on cache miss; scraping runs asynchronously and results flow to Pub/Sub.

#### Request Processing Flow

1. **Sanitization**: All input strings are trimmed and placeholder values (`"string"`, `"none"`, `"null"`) are discarded.
2. **Validation**: Exactly one of `query`, `search_url`, or `product_url` must be provided.
3. **Site Resolution**: If `site` is omitted, the API infers the site from the URL domain. If `site=all` is used with a query, all three marketplaces are scraped in sequence.
4. **Proxy Validation**: Proxy configuration is validated upfront so errors return `422` immediately.
5. **Cache Check**: A BigQuery query searches `mart_best_price` for products matching the search term published within the last 7 days, ordered by lowest price.
6. **Background Execution**: On cache miss, the scrape job is dispatched as a FastAPI `BackgroundTask` and the API returns immediately with the `job_id`.
7. **Pub/Sub Publishing**: Each scraped product record is enriched with `job_id`, `site`, and `published_at` metadata, then published to the configured Pub/Sub topic.

---

### 3. Stream Processor

**Location:** `stream_processor.py`

A stateless Apache Beam streaming pipeline deployed on Google Cloud Dataflow that continuously consumes Pub/Sub messages and writes them to two output sinks.

#### Pipeline Design

```
Pub/Sub Subscription
        │
        ├──► Format for BigQuery  ──►  BigQuery (raw_scrapes table)
        │      • Extracts job_id, site, published_at
        │      • Stores full message as raw_payload JSON string
        │
        └──► Decode Bytes  ──►  5-Minute Fixed Window  ──►  GCS Data Lake (JSON files)
               • Raw UTF-8 decoded messages
               • Windowed into 5-minute batches
               • Written as sharded JSON files
```

#### BigQuery Sink

Each message is transformed into a structured BigQuery row:

| Column | Source | Type |
|---|---|---|
| `job_id` | `record.job_id` | `STRING` |
| `site` | `record.site` | `STRING` |
| `published_at` | `record.published_at` | `TIMESTAMP` |
| `raw_payload` | Full JSON-serialized message | `STRING` |

The table is auto-created if it does not exist (`CREATE_IF_NEEDED`) and records are appended (`WRITE_APPEND`).

#### GCS Data Lake Sink

Raw messages are decoded to UTF-8, grouped into **5-minute fixed windows**, and written as JSON files to Cloud Storage. This provides:

- A durable, immutable archive of all scraped data.
- A source for batch reprocessing or schema migrations.
- Cost-effective long-term storage with lifecycle management.

#### Environment Configuration

The stream processor reads all configuration from environment variables (loaded from `.env`):

| Variable | Description |
|---|---|
| `GCP_PROJECT_ID` | Google Cloud project ID |
| `GCP_REGION` | Dataflow job region |
| `PUBSUB_SUBSCRIPTION` | Pub/Sub subscription name |
| `BQ_DATASET` | BigQuery dataset name |
| `BQ_TABLE` | BigQuery table name |
| `DATAFLOW_TEMP_LOCATION` | GCS path for Dataflow temp files |
| `DATAFLOW_STAGING_LOCATION` | GCS path for Dataflow staging |
| `DATAFLOW_DATA_LAKE` | GCS path prefix for data lake output |
| `DATAFLOW_RUNNER` | Beam runner (`DataflowRunner` for production) |
| `DATAFLOW_SERVICE_ACCOUNT` | GCP service account email |
| `DATAFLOW_WORKER_ZONE` | Compute Engine zone for Dataflow workers |

---

### 4. Transform Layer (dbt)

**Location:** `ecommerce_transform/`

A dbt project that transforms raw JSON payloads from BigQuery into clean, analytics-ready tables. The project is containerized and runs as a Cloud Run Job on a schedule.

#### Model Lineage

```
raw_scrapes (BigQuery source, loaded by Dataflow)
    │
    ▼
stg_raw_scrapes (staging view)
    │  • Extracts fields from raw_payload JSON
    │  • type-casts published_at, current_price, rating
    │  • Handles field name aliases across sites
    │  • Filters out records with missing product URLs
    │
    ▼
mart_best_price (incremental table)
       • Incremental merge keyed on product_url
       • Deduplicates using ROW_NUMBER() OVER (PARTITION BY product_url ORDER BY published_at DESC)
       • Only processes records newer than the last dbt run
       • Maintains a single row per unique product URL with the latest data
```

#### `stg_raw_scrapes` (Staging)

A **view** that transforms raw JSON payloads into typed columns. Handles cross-site field name differences:

| Output Column | JSON Extraction (with fallbacks) |
|---|---|
| `product_id` | `$.product_id` |
| `product_name` | `$.product_name` → `$.title` → `$.title_raw` |
| `product_url` | `$.product_url` → `$.url` |
| `image_url` | `$.image_url` → `$.img_url` |
| `current_price` | `$.price` (cast to `FLOAT64`) |
| `rating` | `$.rating` (cast to `FLOAT64`) |

#### `mart_best_price` (Mart)

An **incremental table** using the `merge` strategy:

- **Unique key:** `product_url` — ensures one row per product.
- **Incremental filter:** Only processes records where `published_at` is newer than the maximum `published_at` in the existing table.
- **Deduplication:** If multiple records exist for the same product URL within a batch, only the most recent is kept.
- **Merge behavior:** On conflict, updates all columns with the newest values.

#### dbt Profile

The connection profile uses environment variables for all credentials:

```yaml
ecommerce_transform:
  outputs:
    dev:
      type: bigquery
      method: oauth
      project: "{{ env_var('DBT_PROJECT_ID') }}"
      dataset: "{{ env_var('DBT_DATASET') }}"
      location: "{{ env_var('DBT_LOCATION') }}"
```

---

## Data Model

### Unified Product Schema

After normalization in `service.py` and transformation in dbt, every product record conforms to this schema:

| Field | Type | Description |
|---|---|---|
| `product_id` | `STRING` | Marketplace-specific identifier (ASIN for Amazon, SKU for others) |
| `product_url` | `STRING` | Canonical URL to the product page |
| `image_url` | `STRING` | Product thumbnail image URL |
| `product_name` | `STRING` | Product title / display name |
| `site` | `STRING` | Source marketplace (`amazon`, `noon`, `jumia`) |
| `current_price` | `FLOAT64` | Current listed price |
| `rating` | `FLOAT64` | Average customer rating (1.0–5.0) |
| `published_at` | `TIMESTAMP` | UTC timestamp when the record was scraped |
| `job_id` | `STRING` | UUID linking the record to the API request that triggered it |

### Additional Fields (Raw only)

These fields are available in the raw payload but not yet surfaced in the mart:

| Field | Type | Description |
|---|---|---|
| `original_price` | `FLOAT64` | Pre-discount price |
| `currency` | `STRING` | Currency code (`EGP`, `AED`, `SAR`, `USD`, etc.) |
| `reviews_count` | `INT64` | Number of customer reviews |
| `discount_percent` | `INT64` | Discount percentage |
| `title_raw` | `STRING` | Unprocessed product title |

---

## Getting Started

### Prerequisites

| Requirement | Purpose |
|---|---|
| **Python 3.11+** | Runtime for API, scrapers, and stream processor |
| **Google Cloud SDK** | `gcloud` CLI for authentication and deployment |
| **Google Cloud Authentication** | `gcloud auth application-default login` for local development |
| **GCP Project** | With BigQuery, Pub/Sub, Dataflow, Cloud Run, and GCS APIs enabled |
| **dbt-core** (optional) | For running transformations locally |

### Installation

**1. Clone the repository:**

```bash
git clone https://github.com/sallam-0/gcp-ecommerce-data-platform.git
cd gcp-ecommerce-data-platform
```

**2. Install API and scraper dependencies:**

```bash
pip install -r api/requirements.txt
```

**3. Install stream processor dependencies (if running locally):**

```bash
pip install "apache-beam[gcp]" google-cloud-storage
```

### Running the Scraper CLI

The `test_with_proxies.py` script provides a full-featured CLI for testing scrapers locally.

**Single site search:**

```bash
python test_with_proxies.py --site amazon --query "iphone 16 pro" --max-products 5
```

**Multi-site search:**

```bash
python test_with_proxies.py --site all --query "samsung galaxy s25" --max-products 10
```

**With proxy support:**

```bash
python test_with_proxies.py \
  --site amazon \
  --query "laptop" \
  --proxy-file scrappers/proxies.txt \
  --rotate-every 2 \
  --max-proxy-attempts 5
```

**Product details mode:**

```bash
python test_with_proxies.py --product-url "https://www.amazon.eg/dp/B0EXAMPLE"
```

Results are saved as JSON files (e.g., `amazon_proxy_test_results.json`) along with detailed proxy metrics.

### Running the API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8080
```

Open the interactive documentation at `http://localhost:8080/docs`.

**Example request:**

```bash
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{
    "site": "all",
    "query": "samsung galaxy",
    "max_products": 5,
    "fast_mode": true
  }'
```

### Running the Stream Processor

**1. Configure the `.env` file** with your GCP project details (see [Configuration Reference](#configuration-reference)).

**2. Submit the Dataflow job:**

```bash
python stream_processor.py
```

> **Note:** When using `DataflowRunner`, the job is submitted to GCP and runs continuously as a streaming pipeline. For local testing, change `DATAFLOW_RUNNER` to `DirectRunner`.

### Running dbt Transformations

**From the project root:**

```bash
dbt run --project-dir ecommerce_transform --profiles-dir ecommerce_transform
```

**Or from within the dbt directory:**

```bash
cd ecommerce_transform
dbt run
```

> **Important:** Your dbt profile must have `DBT_PROJECT_ID`, `DBT_DATASET`, and `DBT_LOCATION` environment variables set. The `location` must match your BigQuery dataset region.

---

## Deployment

### API — Cloud Run Service

The API is containerized with the root `Dockerfile` and deployed as a Cloud Run service.

**Build and push the container image:**

```bash
gcloud builds submit \
  --tag europe-west3-docker.pkg.dev/<PROJECT>/docker-repo/ecommerce-api:latest .
```

**Deploy to Cloud Run:**

```bash
gcloud run deploy ecommerce-api \
  --image europe-west3-docker.pkg.dev/<PROJECT>/docker-repo/ecommerce-api:latest \
  --region europe-west3 \
  --allow-unauthenticated
```

The Dockerfile creates a minimal `python:3.11-slim` image, installs dependencies, copies only the `api/` and `scrappers/` directories, creates a non-root user, and runs Uvicorn on port `8080`.

### dbt — Cloud Run Job

The dbt project is containerized separately using `ecommerce_transform/Dockerfile` and deployed as a Cloud Run **Job** (not a service).

**Build:**

```bash
gcloud builds submit \
  --tag europe-west3-docker.pkg.dev/<PROJECT>/docker-repo/dbt-transformation:latest \
  ./ecommerce_transform
```

**Create or update the job:**

```bash
gcloud run jobs update dbt-transformation \
  --image europe-west3-docker.pkg.dev/<PROJECT>/docker-repo/dbt-transformation:latest \
  --region europe-west3 \
  --set-env-vars DBT_PROJECT_ID=<PROJECT>,DBT_DATASET=ecommerce_prod,DBT_LOCATION=europe-west3
```

**Execute the job:**

```bash
gcloud run jobs execute dbt-transformation --region europe-west3
```

The dbt container uses the official `dbt-bigquery` image and runs `dbt run` with profiles bundled inside the container.

### Stream Processor — Dataflow

The stream processor is submitted directly from `stream_processor.py` as a Dataflow streaming job. Ensure all environment variables in `.env` are configured, then run:

```bash
python stream_processor.py
```

The job will run continuously on Dataflow, processing messages as they arrive in the Pub/Sub subscription.

---

## Configuration Reference

### Environment Variables (`.env`)

| Variable | Example | Required By |
|---|---|---|
| `GCP_PROJECT_ID` | `e-commerce-492314` | Stream Processor, API |
| `GCP_REGION` | `europe-west1` | Stream Processor |
| `PUBSUB_SUBSCRIPTION` | `ecommerce-raw-sub` | Stream Processor |
| `PUBSUB_TOPIC_ID` | `ecommerce-raw` | API |
| `BQ_DATASET` | `ecommerce_prod` | Stream Processor, API |
| `BQ_TABLE` | `raw_scrapes` | Stream Processor, API |
| `DATAFLOW_TEMP_LOCATION` | `gs://bucket/temp` | Stream Processor |
| `DATAFLOW_STAGING_LOCATION` | `gs://bucket/staging` | Stream Processor |
| `DATAFLOW_DATA_LAKE` | `gs://bucket/data` | Stream Processor |
| `DATAFLOW_RUNNER` | `DataflowRunner` | Stream Processor |
| `DATAFLOW_SERVICE_ACCOUNT` | `sa@project.iam.gserviceaccount.com` | Stream Processor |
| `DATAFLOW_WORKER_ZONE` | `europe-west1-b` | Stream Processor |

### dbt Environment Variables

| Variable | Example | Description |
|---|---|---|
| `DBT_PROJECT_ID` | `e-commerce-492314` | BigQuery project for dbt |
| `DBT_DATASET` | `ecommerce_prod` | Target dataset for dbt models |
| `DBT_LOCATION` | `europe-west3` | BigQuery dataset location/region |

---

## Troubleshooting

| Issue | Cause | Resolution |
|---|---|---|
| `site='all'` fails with URL mode | `all` is only supported for query-based searches | Provide a single site or use query mode |
| BigQuery `invalid project ID` | Whitespace in environment variable values | Trim whitespace in `.env` (e.g., remove trailing spaces) |
| Dataflow workers not starting | Regional quota limits or IAM permission issues | Verify `DATAFLOW_WORKER_ZONE` availability and service account roles |
| dbt `dataset/location` error | Profile `location` doesn't match dataset region | Set `DBT_LOCATION` to match the BigQuery dataset's region |
| CAPTCHA blocks on scraping | Anti-bot detection triggered | Use proxies, increase delays, or reduce `max_products` |
| `ImportError: google-cloud-pubsub` | GCP dependencies not installed | Run `pip install -r api/requirements.txt` |
| Pub/Sub publishing fails | `GCP_PROJECT_ID` not set or invalid | Set the environment variable or authenticate via `gcloud auth application-default login` |

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

