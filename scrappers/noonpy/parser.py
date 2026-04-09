"""
Noon HTML parsing module.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .utils import format_noon_product_url, parse_noon_product_url

NOON_BLOCK_MARKERS: Tuple[str, ...] = (
    "captcha",
    "verify you are human",
    "access denied",
)

_PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,}$")


def parse_product_page(html_content: str, url: str = None, locale: str = "egypt-en") -> Optional[Dict[str, Any]]:
    if not html_content:
        print("Error: Received empty HTML content")
        return None

    if _is_blocked_html(html_content):
        print("Possible CAPTCHA or block page detected in Noon product HTML")
        return None

    soup = BeautifulSoup(html_content, "lxml")
    product_id = None
    canonical_url = url

    parsed_url = parse_noon_product_url(url or "", locale=locale)
    if parsed_url:
        _, product_id = parsed_url
        canonical_url = format_noon_product_url(product_id, locale)

    data: Dict[str, Any] = {
        "product_id": product_id,
        "url": canonical_url,
    }

    ld_product = _extract_product_from_json_ld(soup)
    if ld_product:
        _merge_product_page_fields(data, ld_product, locale=locale)

    _merge_meta_fields(data, soup)

    if not data.get("title"):
        title_elem = soup.select_one("h1")
        if title_elem:
            data["title"] = title_elem.get_text(" ", strip=True)

    if not data.get("product_id") and url:
        parsed_again = parse_noon_product_url(url, locale=locale)
        if parsed_again:
            _, data["product_id"] = parsed_again
            data["url"] = format_noon_product_url(data["product_id"], locale)

    if not data.get("title"):
        print("Failed to extract Noon product title")
        return None

    return data


def parse_search_page(
    html_content: str,
    base_url: str = None,
    locale: str = "egypt-en",
    max_products: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not html_content:
        print("Error: Received empty HTML content for Noon search page")
        return []

    if _is_blocked_html(html_content):
        print("CAPTCHA or block page detected in Noon search results")
        return []

    soup = BeautifulSoup(html_content, "lxml")
    resolved_base = base_url or f"https://www.noon.com/{locale}/"

    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for product in _extract_search_products_from_json_ld(soup, resolved_base, locale):
        if product["product_id"] not in seen_ids:
            results.append(product)
            seen_ids.add(product["product_id"])
            if max_products and max_products > 0 and len(results) >= max_products:
                return results

    next_data = _extract_next_data(soup)
    if next_data:
        for obj in _iter_dicts(next_data):
            product = _build_search_product_from_object(obj, resolved_base, locale)
            if not product:
                continue
            if product["product_id"] in seen_ids:
                continue
            results.append(product)
            seen_ids.add(product["product_id"])
            if max_products and max_products > 0 and len(results) >= max_products:
                return results

    if not results:
        for anchor in soup.select("a[href*='/p/']"):
            href = anchor.get("href")
            if not href:
                continue
            full_url = urljoin(resolved_base, href)
            parsed = parse_noon_product_url(full_url, locale=locale)
            if not parsed:
                continue
            _, product_id = parsed
            if product_id in seen_ids:
                continue

            title = anchor.get("title") or anchor.get("aria-label") or anchor.get_text(" ", strip=True)
            if not title or len(title) < 4:
                continue

            product: Dict[str, Any] = {
                "product_id": product_id,
                "title": title,
                "url": format_noon_product_url(product_id, locale),
            }

            image = anchor.select_one("img")
            if image:
                img_url = image.get("src") or image.get("data-src") or image.get("srcset")
                if img_url:
                    product["img_url"] = img_url.split(",")[0].strip().split(" ")[0]

            _enrich_product_from_text_blob(product, title)
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
        "a[href*='page=']",
    ]
    for selector in candidates:
        link = soup.select_one(selector)
        if not link or not link.get("href"):
            continue
        text = link.get_text(" ", strip=True).lower()
        aria = (link.get("aria-label") or "").lower()
        if "next" in text or "next" in aria or selector == "a[href*='page=']":
            href = link["href"]
            return urljoin(base_url, href) if base_url else href

    return None


def _is_blocked_html(html_content: str) -> bool:
    lower = html_content.lower()
    return any(marker in lower for marker in NOON_BLOCK_MARKERS)


def _extract_search_products_from_json_ld(
    soup: BeautifulSoup,
    base_url: str,
    locale: str,
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
                        product = _build_search_product_from_object(candidate, base_url, locale)
                        if product:
                            products.append(product)

            if "product" in obj_type:
                product = _build_search_product_from_object(obj, base_url, locale)
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


def _merge_product_page_fields(target: Dict[str, Any], product_obj: Dict[str, Any], locale: str) -> None:
    title = _first_string(product_obj, ["name", "title"])
    if title:
        target.setdefault("title", title)

    product_id = _first_string(product_obj, ["sku", "productID", "productId", "id"])
    url_value = _first_string(product_obj, ["url"])
    if url_value and not product_id:
        parsed = parse_noon_product_url(url_value, locale=locale)
        if parsed:
            _, product_id = parsed

    if product_id and _PRODUCT_ID_PATTERN.match(product_id):
        target["product_id"] = product_id
        target["url"] = format_noon_product_url(product_id, locale)

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


def _merge_meta_fields(target: Dict[str, Any], soup: BeautifulSoup) -> None:
    meta_map: Dict[str, str] = {}
    for tag in soup.select("meta"):
        key = (tag.get("property") or tag.get("name") or "").strip().lower()
        value = (tag.get("content") or "").strip()
        if key and value:
            meta_map[key] = value

    if not target.get("title"):
        target_title = meta_map.get("og:title")
        if target_title:
            target["title"] = target_title

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
            target["currency"] = currency

    if not target.get("rating"):
        rating = _as_float(meta_map.get("product:rating:value"))
        if rating is not None:
            target["rating"] = rating

    if not target.get("reviews_count"):
        reviews = _as_int(meta_map.get("product:rating:count"))
        if reviews is not None:
            target["reviews_count"] = reviews

    if not target.get("brand"):
        brand = meta_map.get("product:brand")
        if brand:
            target["brand"] = brand


def _build_search_product_from_object(obj: Dict[str, Any], base_url: str, locale: str) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None

    title = _first_string(obj, ["name", "title", "displayName", "productName"])
    raw_url = _first_string(obj, ["url", "pdpUrl", "productUrl", "link", "href"])
    product_id = _first_string(obj, ["sku", "productId", "productID", "id", "catalogSku"])

    parsed = None
    if raw_url:
        full_url = urljoin(base_url, raw_url)
        parsed = parse_noon_product_url(full_url, locale=locale)
        if parsed:
            _, product_id = parsed
    elif product_id and _PRODUCT_ID_PATTERN.match(product_id):
        full_url = format_noon_product_url(product_id, locale)
    else:
        full_url = None

    if not product_id or not _PRODUCT_ID_PATTERN.match(product_id):
        return None
    if not title or len(title.strip()) < 4:
        return None

    product: Dict[str, Any] = {
        "product_id": product_id,
        "title": title.strip(),
        "url": format_noon_product_url(product_id, locale),
    }

    if parsed and raw_url:
        resolved = urljoin(base_url, raw_url)
        product["url"] = resolved

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

    if title:
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


def _extract_next_data(soup: BeautifulSoup) -> Optional[Any]:
    script = soup.select_one("script#__NEXT_DATA__")
    if not script:
        return None

    text = script.string or script.get_text(strip=True)
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
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
    currency = _first_string(data, ["currency", "currencyCode", "currency_code"])
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
                    return value, nested_currency or currency
        elif isinstance(candidate, dict):
            value, nested_currency = _extract_price_currency_from_candidate(candidate)
            if value is not None:
                return value, nested_currency or currency
            if nested_currency and not currency:
                currency = nested_currency
        else:
            value = _as_float(candidate)
            if value is not None:
                return value, currency

    return None, currency


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

    for key, value in candidate.items():
        if isinstance(value, (dict, list)):
            nested_value, nested_currency = _extract_price_currency_from_candidate(value)
            if nested_value is not None:
                return nested_value, nested_currency or currency

    return None, currency


def _is_product_type(type_value: Any) -> bool:
    if isinstance(type_value, str):
        return type_value.lower() == "product"
    if isinstance(type_value, list):
        return any(isinstance(item, str) and item.lower() == "product" for item in type_value)
    return False


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
        cleaned_title = _clean_title_from_blob(product["title"])
        if cleaned_title and cleaned_title != product["title"]:
            product["title_raw"] = product["title"]
            product["title"] = cleaned_title

    if "currency" not in product:
        currency_match = re.search(r"\b(EGP|AED|SAR)\b", text, flags=re.IGNORECASE)
        if currency_match:
            product["currency"] = currency_match.group(1).upper()

    if "price" not in product:
        price_match = re.search(r"\b(EGP|AED|SAR)\s*([0-9][0-9,]*(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
        if price_match:
            price = _as_float(price_match.group(2))
            if price is not None:
                product["price"] = price
            product.setdefault("currency", price_match.group(1).upper())

            trailing = text[price_match.end():]
            original_match = re.search(r"\b([0-9][0-9,]*(?:\.\d+)?)\b", trailing)
            if original_match:
                original_price = _as_float(original_match.group(1))
                if (
                    original_price is not None
                    and "price" in product
                    and original_price > float(product["price"])
                ):
                    product["original_price"] = original_price

    if "rating" not in product or "reviews_count" not in product:
        rating_match = re.search(
            r"\b([1-5](?:\.\d)?)\s+([0-9]+(?:\.[0-9]+)?[KkMm]?)\s+(?:EGP|AED|SAR)\b",
            text,
        )
        if not rating_match:
            rating_match = re.search(r"\b([1-5](?:\.\d)?)\s+([0-9]+(?:\.[0-9]+)?[KkMm]?)\b", text)

        if rating_match:
            if "rating" not in product:
                rating = _as_float(rating_match.group(1))
                if rating is not None:
                    product["rating"] = rating
            if "reviews_count" not in product:
                reviews = _parse_count_token(rating_match.group(2))
                if reviews is not None:
                    product["reviews_count"] = reviews

    if "discount_percent" not in product:
        discount_match = re.search(r"\b(\d{1,2})%\s*Off\b", text, flags=re.IGNORECASE)
        if discount_match:
            product["discount_percent"] = int(discount_match.group(1))

    if "stock_left" not in product:
        stock_match = re.search(r"\bOnly\s+([0-9]+)\s+left in stock\b", text, flags=re.IGNORECASE)
        if stock_match:
            product["stock_left"] = int(stock_match.group(1))

    sold_match = re.search(r"\b([0-9]+)\+\s+sold recently\b", text, flags=re.IGNORECASE)
    if sold_match:
        product["sold_recently"] = int(sold_match.group(1))

    if "badge" not in product and text.lower().startswith("best seller"):
        product["badge"] = "Best Seller"

    if "free delivery" in text.lower():
        product["free_delivery"] = True
    if "selling out fast" in text.lower():
        product["selling_out_fast"] = True

    if "category_rank" not in product:
        rank_match = re.search(r"#(\d+)\s+in\s+([^#]+?)(?=\s+(?:Free Delivery|Get it by|\d+\+\s+sold recently|$))", text)
        if rank_match:
            product["category_rank"] = {
                "rank": int(rank_match.group(1)),
                "category": rank_match.group(2).strip(),
            }


def _clean_title_from_blob(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return cleaned

    cleaned = re.sub(r"^(Best Seller|Payweek Sale\S*)\s+", "", cleaned, flags=re.IGNORECASE)

    cutoffs: List[int] = []
    patterns = [
        r"\b[1-5](?:\.\d)?\s+[0-9]+(?:\.[0-9]+)?[KkMm]?\s+(?:EGP|AED|SAR)\b",
        r"\b(?:EGP|AED|SAR)\s*[0-9]",
        r"\bFree Delivery\b",
        r"\bGet it by\b",
        r"\b#\d+\s+in\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            cutoffs.append(match.start())

    if cutoffs:
        trimmed = cleaned[: min(cutoffs)].strip(" -|,")
        if len(trimmed) >= 6:
            return trimmed

    return cleaned


def _parse_count_token(token: str) -> Optional[int]:
    if not token:
        return None

    candidate = token.strip().upper()
    multiplier = 1
    if candidate.endswith("K"):
        multiplier = 1_000
        candidate = candidate[:-1]
    elif candidate.endswith("M"):
        multiplier = 1_000_000
        candidate = candidate[:-1]

    value = _as_float(candidate)
    if value is None:
        return None
    return int(value * multiplier)
