"""
Jumia HTML parsing module.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .utils import (
    canonicalize_jumia_product_url,
    extract_jumia_product_id,
    format_jumia_sku_url,
    normalize_jumia_domain,
)

JUMIA_BLOCK_MARKERS: Tuple[str, ...] = (
    "captcha",
    "verify you are human",
    "access denied",
    "security check",
    "attention required",
    "cloudflare",
)

_PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,}$")
_PRICE_CURRENCY_PATTERN = re.compile(
    r"\b(EGP|USD|EUR|GBP|NGN|KES|GHS|MAD|DZD|XOF|UGX|TND|SAR|AED)\s*([0-9][0-9,]*(?:\.\d+)?)\b",
    flags=re.IGNORECASE,
)
_SKU_PATTERN = re.compile(r"\bSKU\s*:\s*([A-Za-z0-9_-]{6,})\b", flags=re.IGNORECASE)


def parse_product_page(html_content: str, url: str = None, domain: str = "com.eg") -> Optional[Dict[str, Any]]:
    if not html_content:
        print("Error: Received empty HTML content")
        return None

    if _is_blocked_html(html_content):
        print("Possible CAPTCHA or block page detected in Jumia product HTML")
        return None

    active_domain = normalize_jumia_domain(domain)
    soup = BeautifulSoup(html_content, "lxml")

    product_id = extract_jumia_product_id(url or "")
    canonical_url = canonicalize_jumia_product_url(url or "", default_domain=active_domain)

    data: Dict[str, Any] = {
        "product_id": product_id,
        "url": canonical_url or url,
    }

    ld_product = _extract_product_from_json_ld(soup)
    if ld_product:
        _merge_product_fields(data, ld_product, active_domain=active_domain)

    _merge_meta_fields(data, soup, active_domain=active_domain)
    _merge_product_fields_from_dom(data, soup)

    if not data.get("product_id"):
        sku_match = _SKU_PATTERN.search(soup.get_text(" ", strip=True))
        if sku_match:
            data["product_id"] = sku_match.group(1).upper()

    if not data.get("url") and data.get("product_id"):
        product_id_value = str(data["product_id"])
        if _looks_like_sku(product_id_value):
            data["url"] = format_jumia_sku_url(product_id_value, domain=active_domain)

    if not data.get("title"):
        print("Failed to extract Jumia product title")
        return None

    return data


def parse_search_page(
    html_content: str,
    base_url: str = None,
    domain: str = "com.eg",
    max_products: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not html_content:
        print("Error: Received empty HTML content for Jumia search page")
        return []

    if _is_blocked_html(html_content):
        print("CAPTCHA or block page detected in Jumia search results")
        return []

    active_domain = normalize_jumia_domain(domain)
    soup = BeautifulSoup(html_content, "lxml")
    resolved_base = base_url or f"https://www.jumia.{active_domain}/"

    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for product in _extract_search_products_from_json_ld(soup, resolved_base, active_domain):
        product_id = product.get("product_id")
        if product_id and product_id not in seen_ids:
            results.append(product)
            seen_ids.add(product_id)
            if max_products and max_products > 0 and len(results) >= max_products:
                return results

    state_payload = _extract_state_payload(soup)
    if state_payload:
        for obj in _iter_dicts(state_payload):
            product = _build_search_product_from_object(obj, resolved_base, active_domain)
            if not product:
                continue
            product_id = product["product_id"]
            if product_id in seen_ids:
                continue
            results.append(product)
            seen_ids.add(product_id)
            if max_products and max_products > 0 and len(results) >= max_products:
                return results

    for card in soup.select("article.prd, article[class*='prd']"):
        product = _build_search_product_from_card(card, resolved_base, active_domain)
        if not product:
            continue
        product_id = product["product_id"]
        if product_id in seen_ids:
            continue
        results.append(product)
        seen_ids.add(product_id)
        if max_products and max_products > 0 and len(results) >= max_products:
            return results

    if not results:
        for anchor in soup.select("a[href*='.html'], a[href*='/catalog/productspecifications/sku/']"):
            product = _build_search_product_from_anchor(anchor, resolved_base, active_domain)
            if not product:
                continue
            product_id = product["product_id"]
            if product_id in seen_ids:
                continue
            results.append(product)
            seen_ids.add(product_id)
            if max_products and max_products > 0 and len(results) >= max_products:
                return results

    return results


def parse_pagination_url(html_content: str, base_url: str = None) -> Optional[str]:
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, "lxml")

    next_link = soup.select_one("link[rel='next']")
    if next_link and next_link.get("href"):
        return urljoin(base_url, next_link["href"]) if base_url else next_link["href"]

    candidates = [
        "a[aria-label*='next' i]",
        "a[rel='next']",
        "a:-soup-contains('Next')",
    ]
    for selector in candidates:
        link = soup.select_one(selector)
        if link and link.get("href"):
            href = link["href"]
            return urljoin(base_url, href) if base_url else href

    current_page = _extract_current_page_number(soup)
    page_links: Dict[int, str] = {}

    for link in soup.select("a[href*='page=']"):
        href = link.get("href")
        if not href:
            continue
        page_number = _extract_page_number(href)
        if page_number is None:
            continue
        page_links.setdefault(page_number, href)

    if not page_links:
        return None

    next_pages = [page for page in page_links if page > current_page]
    if not next_pages:
        return None

    next_page = min(next_pages)
    next_href = page_links[next_page]
    return urljoin(base_url, next_href) if base_url else next_href


def _is_blocked_html(html_content: str) -> bool:
    lower = html_content.lower()
    return any(marker in lower for marker in JUMIA_BLOCK_MARKERS)


def _extract_search_products_from_json_ld(
    soup: BeautifulSoup,
    base_url: str,
    active_domain: str,
) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []

    for payload in _extract_json_ld_payloads(soup):
        for obj in _iter_dicts(payload):
            obj_type = str(obj.get("@type", "")).lower()

            if obj_type == "itemlist":
                items = obj.get("itemListElement")
                if isinstance(items, list):
                    for item in items:
                        candidate: Dict[str, Any]
                        if isinstance(item, dict) and isinstance(item.get("item"), dict):
                            candidate = item["item"]
                        elif isinstance(item, dict):
                            candidate = item
                        else:
                            continue
                        product = _build_search_product_from_object(candidate, base_url, active_domain)
                        if product:
                            products.append(product)

            if "product" in obj_type:
                product = _build_search_product_from_object(obj, base_url, active_domain)
                if product:
                    products.append(product)

    return products


def _extract_product_from_json_ld(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for payload in _extract_json_ld_payloads(soup):
        for obj in _iter_dicts(payload):
            obj_type = obj.get("@type")
            if _is_product_type(obj_type):
                return obj
    return None


def _merge_product_fields(target: Dict[str, Any], product_obj: Dict[str, Any], active_domain: str) -> None:
    title = _first_string(product_obj, ["name", "title", "productName"])
    if title:
        target.setdefault("title", title)

    product_id = _first_string(product_obj, ["sku", "productID", "productId", "id"])
    url_value = _first_string(product_obj, ["url", "pdpUrl", "productUrl", "href"])
    if url_value and not product_id:
        product_id = extract_jumia_product_id(urljoin(f"https://www.jumia.{active_domain}/", url_value))

    if product_id and _PRODUCT_ID_PATTERN.match(product_id):
        normalized_id = product_id.upper() if _looks_like_sku(product_id) else product_id
        target["product_id"] = normalized_id
        if _looks_like_sku(normalized_id):
            target.setdefault("url", format_jumia_sku_url(normalized_id, domain=active_domain))

    if url_value:
        full_url = urljoin(f"https://www.jumia.{active_domain}/", url_value)
        canonical = canonicalize_jumia_product_url(full_url, default_domain=active_domain) or full_url
        target["url"] = canonical
        if not target.get("product_id"):
            extracted = extract_jumia_product_id(canonical)
            if extracted:
                target["product_id"] = extracted

    image = _extract_image(product_obj, base_url=target.get("url"))
    if image:
        target.setdefault("img_url", image)

    brand = _extract_brand(product_obj)
    if brand:
        target.setdefault("brand", brand)

    price, currency = _extract_price_currency(product_obj)
    if price is not None:
        target.setdefault("price", price)
    if currency:
        target.setdefault("currency", currency)

    agg = product_obj.get("aggregateRating")
    if isinstance(agg, dict):
        rating = _as_float(agg.get("ratingValue"))
        reviews = _as_int(agg.get("reviewCount"))
        if rating is not None:
            target.setdefault("rating", rating)
        if reviews is not None:
            target.setdefault("reviews_count", reviews)


def _merge_meta_fields(target: Dict[str, Any], soup: BeautifulSoup, active_domain: str) -> None:
    meta_map: Dict[str, str] = {}
    for tag in soup.select("meta"):
        key = (tag.get("property") or tag.get("name") or "").strip().lower()
        value = (tag.get("content") or "").strip()
        if key and value:
            meta_map[key] = value

    if not target.get("title"):
        title = meta_map.get("og:title")
        if title:
            target["title"] = title

    if not target.get("img_url"):
        image = meta_map.get("og:image")
        if image:
            target["img_url"] = image

    if not target.get("price"):
        price = _as_float(meta_map.get("product:price:amount"))
        if price is not None:
            target["price"] = price

    if not target.get("currency"):
        currency = meta_map.get("product:price:currency")
        if currency:
            target["currency"] = currency.upper()

    if not target.get("rating"):
        rating = _as_float(meta_map.get("product:rating:value"))
        if rating is not None:
            target["rating"] = rating

    if not target.get("reviews_count"):
        reviews = _as_int(meta_map.get("product:rating:count"))
        if reviews is not None:
            target["reviews_count"] = reviews

    if not target.get("url"):
        canonical = soup.select_one("link[rel='canonical']")
        if canonical and canonical.get("href"):
            href = canonical["href"]
            target["url"] = canonicalize_jumia_product_url(href, default_domain=active_domain) or href

    if target.get("url") and not target.get("product_id"):
        product_id = extract_jumia_product_id(target["url"])
        if product_id:
            target["product_id"] = product_id


def _merge_product_fields_from_dom(target: Dict[str, Any], soup: BeautifulSoup) -> None:
    title_elem = soup.select_one("h1")
    if title_elem and not target.get("title"):
        target["title"] = title_elem.get_text(" ", strip=True)

    body_text = soup.get_text(" ", strip=True)
    _enrich_product_from_text_blob(target, body_text)

    if not target.get("product_id"):
        sku_match = _SKU_PATTERN.search(body_text)
        if sku_match:
            target["product_id"] = sku_match.group(1).upper()

    if not target.get("brand"):
        brand_match = re.search(r"\bBrand\s*:\s*([^|]+)", body_text, flags=re.IGNORECASE)
        if brand_match:
            target["brand"] = brand_match.group(1).strip()


def _build_search_product_from_object(
    obj: Dict[str, Any],
    base_url: str,
    active_domain: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None

    title = _first_string(obj, ["name", "title", "displayName", "productName"])
    raw_url = _first_string(obj, ["url", "pdpUrl", "productUrl", "link", "href"])
    product_id = _first_string(obj, ["sku", "productId", "productID", "id", "simpleSku"])

    full_url: Optional[str] = None
    if raw_url:
        full_url = urljoin(base_url, raw_url)
        extracted = extract_jumia_product_id(full_url)
        if extracted and not product_id:
            product_id = extracted

    if product_id and _looks_like_sku(product_id):
        product_id = product_id.upper()

    if not product_id and full_url:
        product_id = extract_jumia_product_id(full_url)

    if not product_id or not _PRODUCT_ID_PATTERN.match(product_id):
        return None
    if not title or len(title.strip()) < 4:
        return None

    canonical_url = None
    if full_url:
        canonical_url = canonicalize_jumia_product_url(full_url, default_domain=active_domain) or full_url
    elif _looks_like_sku(product_id):
        canonical_url = format_jumia_sku_url(product_id, domain=active_domain)

    if not canonical_url:
        return None

    product: Dict[str, Any] = {
        "product_id": product_id,
        "title": title.strip(),
        "url": canonical_url,
    }

    brand = _extract_brand(obj)
    if brand:
        product["brand"] = brand

    image = _extract_image(obj, base_url=base_url)
    if image:
        product["img_url"] = image

    price, currency = _extract_price_currency(obj)
    if price is not None:
        product["price"] = price
    if currency:
        product["currency"] = currency

    rating = _as_float(obj.get("rating") or obj.get("averageRating") or obj.get("ratingValue"))
    if rating is not None:
        product["rating"] = rating

    reviews = _as_int(
        obj.get("reviewCount")
        or obj.get("reviewsCount")
        or obj.get("ratingsCount")
        or obj.get("ratingCount")
        or obj.get("numReviews")
    )
    if reviews is not None:
        product["reviews_count"] = reviews

    _enrich_product_from_text_blob(product, title)
    return product


def _build_search_product_from_card(
    card: BeautifulSoup,
    base_url: str,
    active_domain: str,
) -> Optional[Dict[str, Any]]:
    anchor = card.select_one("a.core[href]") or card.select_one("a[href*='.html']")
    if not anchor or not anchor.get("href"):
        return None

    full_url = urljoin(base_url, anchor["href"])
    canonical_url = canonicalize_jumia_product_url(full_url, default_domain=active_domain) or full_url
    product_id = extract_jumia_product_id(canonical_url)
    if not product_id:
        return None

    title_elem = card.select_one("h3.name") or card.select_one(".name")
    title = (
        title_elem.get_text(" ", strip=True)
        if title_elem
        else anchor.get("title") or anchor.get("aria-label") or anchor.get_text(" ", strip=True)
    )
    if not title or len(title.strip()) < 4:
        return None

    product: Dict[str, Any] = {
        "product_id": product_id.upper() if _looks_like_sku(product_id) else product_id,
        "title": title.strip(),
        "url": canonical_url,
    }

    img = card.select_one("img")
    if img:
        img_url = img.get("data-src") or img.get("src") or img.get("data-srcset") or img.get("srcset")
        if img_url:
            product["img_url"] = img_url.split(",")[0].strip().split(" ")[0]

    price_elem = card.select_one(".prc, [class*='prc']")
    old_price_elem = card.select_one(".old, [class*='old']")
    discount_elem = card.select_one(".bdg._dsct, [class*='dsct']")
    rating_elem = card.select_one(".stars, [class*='stars']")
    review_elem = card.select_one(".rev, [class*='rev']")

    card_blob_parts = [
        title,
        price_elem.get_text(" ", strip=True) if price_elem else "",
        old_price_elem.get_text(" ", strip=True) if old_price_elem else "",
        discount_elem.get_text(" ", strip=True) if discount_elem else "",
        rating_elem.get_text(" ", strip=True) if rating_elem else "",
        review_elem.get_text(" ", strip=True) if review_elem else "",
    ]
    card_blob = " ".join(part for part in card_blob_parts if part)
    _enrich_product_from_text_blob(product, card_blob)

    if old_price_elem:
        old_price = _as_float(old_price_elem.get_text(" ", strip=True))
        if old_price is not None:
            product["original_price"] = old_price
            if product.get("price"):
                current_price = float(product["price"])
                if old_price > current_price > 0:
                    product["discount_percent"] = round(100 - (current_price / old_price * 100))

    if discount_elem and "discount_percent" not in product:
        discount_match = re.search(r"(\d{1,2})\s*%", discount_elem.get_text(" ", strip=True))
        if discount_match:
            product["discount_percent"] = int(discount_match.group(1))

    return product


def _build_search_product_from_anchor(
    anchor: BeautifulSoup,
    base_url: str,
    active_domain: str,
) -> Optional[Dict[str, Any]]:
    href = anchor.get("href")
    if not href:
        return None

    full_url = urljoin(base_url, href)
    canonical_url = canonicalize_jumia_product_url(full_url, default_domain=active_domain) or full_url
    product_id = extract_jumia_product_id(canonical_url)
    if not product_id:
        return None

    title = anchor.get("title") or anchor.get("aria-label") or anchor.get_text(" ", strip=True)
    if not title or len(title.strip()) < 4:
        return None

    product: Dict[str, Any] = {
        "product_id": product_id.upper() if _looks_like_sku(product_id) else product_id,
        "title": title.strip(),
        "url": canonical_url,
    }

    image = anchor.select_one("img")
    if image:
        img_url = image.get("data-src") or image.get("src") or image.get("data-srcset") or image.get("srcset")
        if img_url:
            product["img_url"] = img_url.split(",")[0].strip().split(" ")[0]

    _enrich_product_from_text_blob(product, title)
    return product


def _extract_json_ld_payloads(soup: BeautifulSoup) -> List[Any]:
    payloads: List[Any] = []
    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text(strip=True)
        if not text:
            continue
        try:
            payloads.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return payloads


def _extract_state_payload(soup: BeautifulSoup) -> Optional[Any]:
    for selector in ("script#__NEXT_DATA__", "script#__NUXT__", "script#__APOLLO_STATE__"):
        script = soup.select_one(selector)
        if not script:
            continue
        text = script.string or script.get_text(strip=True)
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue

    for script in soup.select("script"):
        text = script.string or script.get_text(strip=True)
        if not text:
            continue
        for marker in ("window.__PRELOADED_STATE__ =", "window.__INITIAL_STATE__ ="):
            if marker not in text:
                continue
            raw_json = text.split(marker, 1)[1].strip().rstrip(";")
            try:
                return json.loads(raw_json)
            except json.JSONDecodeError:
                continue

    return None


def _iter_dicts(payload: Any) -> Iterable[Dict[str, Any]]:
    stack: List[Any] = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def _first_string(data: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_brand(data: Dict[str, Any]) -> Optional[str]:
    brand = data.get("brand") or data.get("brandName") or data.get("manufacturer")
    if isinstance(brand, dict):
        return _first_string(brand, ["name", "brandName", "title"])
    if isinstance(brand, str) and brand.strip():
        return brand.strip()
    return None


def _extract_image(data: Dict[str, Any], base_url: Optional[str]) -> Optional[str]:
    image = data.get("image") or data.get("imageUrl") or data.get("thumbnail") or data.get("img")
    if isinstance(image, list):
        image = next((item for item in image if isinstance(item, str) and item.strip()), None)
    elif isinstance(image, dict):
        image = image.get("url") or image.get("src") or image.get("link")

    if isinstance(image, str) and image.strip():
        return urljoin(base_url, image) if base_url else image
    return None


def _extract_price_currency(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    currency = _first_string(data, ["currency", "currencyCode", "currency_code", "priceCurrency"])
    candidates = [
        data.get("price"),
        data.get("salePrice"),
        data.get("finalPrice"),
        data.get("sellingPrice"),
        data.get("specialPrice"),
        data.get("regularPrice"),
        data.get("oldPrice"),
        data.get("wasPrice"),
        data.get("offerPrice"),
        data.get("priceNow"),
        data.get("currentPrice"),
        data.get("amount"),
        data.get("prices"),
        data.get("pricing"),
        data.get("priceInfo"),
        data.get("offer"),
        data.get("offers"),
    ]

    for candidate in candidates:
        if isinstance(candidate, list):
            for item in candidate:
                value, nested_currency = _extract_price_currency_from_candidate(item)
                if value is not None:
                    return value, (nested_currency or currency or "").upper() or None
        elif isinstance(candidate, dict):
            value, nested_currency = _extract_price_currency_from_candidate(candidate)
            if value is not None:
                return value, (nested_currency or currency or "").upper() or None
            if nested_currency and not currency:
                currency = nested_currency
        else:
            value = _as_float(candidate)
            if value is not None:
                return value, (currency or "").upper() or None

    return None, (currency or "").upper() or None


def _extract_price_currency_from_candidate(candidate: Any) -> Tuple[Optional[float], Optional[str]]:
    if isinstance(candidate, list):
        for item in candidate:
            value, currency = _extract_price_currency_from_candidate(item)
            if value is not None:
                return value, currency
        return None, None

    if not isinstance(candidate, dict):
        return _as_float(candidate), None

    currency = _first_string(candidate, ["currency", "priceCurrency", "currencyCode"])
    nested_candidates = [
        candidate.get("value"),
        candidate.get("price"),
        candidate.get("amount"),
        candidate.get("current"),
        candidate.get("final"),
        candidate.get("priceValue"),
        candidate.get("amountWithCurrency"),
        candidate.get("selling"),
        candidate.get("special"),
    ]
    for nested in nested_candidates:
        value = _as_float(nested)
        if value is not None:
            return value, currency

    for value in candidate.values():
        if isinstance(value, (dict, list)):
            nested_value, nested_currency = _extract_price_currency_from_candidate(value)
            if nested_value is not None:
                return nested_value, nested_currency or currency

    return None, currency


def _extract_current_page_number(soup: BeautifulSoup) -> int:
    for selector in ("link[rel='canonical']", "meta[property='og:url']", "meta[name='twitter:url']"):
        node = soup.select_one(selector)
        if not node:
            continue
        href = node.get("href") or node.get("content")
        if not href:
            continue
        page = _extract_page_number(href)
        if page is not None:
            return page

    active_selectors = (
        ".pg .sqr._act",
        ".pg .sqr.-active",
        ".pg a[aria-current='page']",
        ".pagination .active",
    )
    for selector in active_selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        text = node.get_text(" ", strip=True)
        if text.isdigit():
            return int(text)

    return 1


def _extract_page_number(url_or_path: str) -> Optional[int]:
    parsed = urlparse(url_or_path)
    query = parse_qs(parsed.query)
    page_values = query.get("page")
    if page_values:
        try:
            return int(page_values[0])
        except (ValueError, TypeError):
            return None

    match = re.search(r"[?&]page=(\d+)", url_or_path)
    if match:
        return int(match.group(1))
    return None


def _is_product_type(type_value: Any) -> bool:
    if isinstance(type_value, str):
        return type_value.lower() == "product"
    if isinstance(type_value, list):
        return any(isinstance(item, str) and item.lower() == "product" for item in type_value)
    return False


def _looks_like_sku(value: str) -> bool:
    if not value:
        return False
    candidate = value.strip().upper()
    return candidate.endswith("FAMZ") and bool(re.fullmatch(r"[A-Z0-9_-]{8,}", candidate))


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.,-]", "", value).replace(",", "")
        if cleaned in {"", ".", "-", "-."}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9]", "", value)
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def _enrich_product_from_text_blob(product: Dict[str, Any], text_blob: str) -> None:
    text = " ".join((text_blob or "").split())
    if not text:
        return

    if "title" in product and product["title"]:
        cleaned_title = _clean_title(product["title"])
        if cleaned_title and cleaned_title != product["title"]:
            product["title_raw"] = product["title"]
            product["title"] = cleaned_title

    currency_prices = _PRICE_CURRENCY_PATTERN.findall(text)
    if currency_prices:
        first_currency, first_price_text = currency_prices[0]
        first_price = _as_float(first_price_text)
        if first_price is not None and "price" not in product:
            product["price"] = first_price
        if first_currency and "currency" not in product:
            product["currency"] = first_currency.upper()

        if len(currency_prices) > 1 and "original_price" not in product:
            _, second_price_text = currency_prices[1]
            second_price = _as_float(second_price_text)
            if (
                second_price is not None
                and "price" in product
                and second_price > float(product["price"])
            ):
                product["original_price"] = second_price

    if "rating" not in product:
        rating_match = re.search(r"\b([0-5](?:\.\d)?)\s+out of 5\b", text, flags=re.IGNORECASE)
        if rating_match:
            rating = _as_float(rating_match.group(1))
            if rating is not None:
                product["rating"] = rating

    if "reviews_count" not in product:
        review_match = re.search(
            r"\(([\d,]+)\s*(?:verified\s+)?(?:ratings?|reviews?)\)",
            text,
            flags=re.IGNORECASE,
        )
        if not review_match:
            review_match = re.search(r"\b([\d,]+)\s+verified\s+ratings?\b", text, flags=re.IGNORECASE)
        if review_match:
            reviews = _as_int(review_match.group(1))
            if reviews is not None:
                product["reviews_count"] = reviews

    if "discount_percent" not in product:
        discount_match = re.search(r"\b(\d{1,2})\s*%\b", text)
        if discount_match:
            product["discount_percent"] = int(discount_match.group(1))

    if "stock_left" not in product:
        stock_match = re.search(r"\b(\d+)\s+units?\s+left\b", text, flags=re.IGNORECASE)
        if stock_match:
            product["stock_left"] = int(stock_match.group(1))

    if "free delivery" in text.lower():
        product["free_delivery"] = True


def _clean_title(title: str) -> str:
    cleaned = " ".join((title or "").split())
    if not cleaned:
        return cleaned

    price_marker = _PRICE_CURRENCY_PATTERN.search(cleaned)
    if price_marker:
        candidate = cleaned[: price_marker.start()].strip(" -|,")
        if len(candidate) >= 6:
            return candidate

    rating_marker = re.search(r"\b[0-5](?:\.\d)?\s+out of 5\b", cleaned, flags=re.IGNORECASE)
    if rating_marker:
        candidate = cleaned[: rating_marker.start()].strip(" -|,")
        if len(candidate) >= 6:
            return candidate

    return cleaned
