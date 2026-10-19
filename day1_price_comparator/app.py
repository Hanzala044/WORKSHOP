"""
Configurable product-page scraper and price comparator.
Set CSS selectors in products.json for each permitted product page.
"""
import csv
import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
CONFIG = ROOT / "products.json"
OUTPUT = ROOT / "price_comparison.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}


def parse_price(text):
    """Extract a numeric price from text such as '₹1,299.00' or '$19.99'."""
    if not text:
        return None
    cleaned = text.replace(",", "")
    match = re.search(r"\d+(?:\.\d{1,2})?", cleaned)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def scrape_product(item):
    url = item["url"]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    name_node = soup.select_one(item["name_selector"])
    price_node = soup.select_one(item["price_selector"])
    name = name_node.get_text(" ", strip=True) if name_node else ""
    price_text = price_node.get_text(" ", strip=True) if price_node else ""
    amount = parse_price(price_text)

    return {
        "site": item.get("site") or parsed.netloc,
        "product": name or "(name selector did not match)",
        "price_text": price_text or "(price selector did not match)",
        "price_value": str(amount) if amount is not None else "",
        "currency": item.get("currency", ""),
        "url": url,
        "status": "ok" if name and amount is not None else "check selectors"
    }


def main():
    items = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not items:
        print("Add at least one permitted product page to products.json.")
        return

    results = []
    for index, item in enumerate(items):
        try:
            result = scrape_product(item)
            results.append(result)
            print(f"{result['site']}: {result['product']} | {result['currency']} {result['price_text']} | {result['status']}")
        except Exception as exc:
            results.append({
                "site": item.get("site", ""),
                "product": "",
                "price_text": "",
                "price_value": "",
                "currency": item.get("currency", ""),
                "url": item.get("url", ""),
                "status": f"error: {type(exc).__name__}: {exc}"
            })
            print(f"Failed: {item.get('url')} -> {exc}")
        # Be polite to websites; avoid rapid repeated requests.
        if index < len(items) - 1:
            time.sleep(2)

    fields = ["site", "product", "price_text", "price_value", "currency", "url", "status"]
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    valid = [r for r in results if r["price_value"]]
    valid.sort(key=lambda r: Decimal(r["price_value"]))
    print(f"\nSaved: {OUTPUT}")
    if valid:
        print("\nComparable prices (only compare rows with the same currency/product):")
        for row in valid:
            print(f"- {row['site']}: {row['currency']} {row['price_value']} — {row['url']}")
    else:
        print("No numeric prices were extracted. Check each page's CSS selectors and permitted access.")


if __name__ == "__main__":
    main()
