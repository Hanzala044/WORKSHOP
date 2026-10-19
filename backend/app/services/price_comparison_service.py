import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from app.core.currencies import CURRENCY_CODES
from app.core.errors import APIError
from app.schemas.pricepilot import CompareRequest
from app.services.scraping_service import ScrapingService

_SYMBOLS = {
    "€": {"EUR"}, "£": {"GBP", "GIP", "FKP", "SHP"}, "₹": {"INR"},
    "$": set("USD CAD AUD NZD SGD HKD MXN ARS CLP COP BRL BBD BMD BND BSD BZD CUP DOP FJD GYD JMD KYD LRD NAD SBD SRD TTD TWD UYU XCD".split()),
    "¥": {"JPY", "CNY"},
}
_CURRENCY_CODES = re.compile(r"\b(?:" + "|".join(sorted(CURRENCY_CODES)) + r")\b")


def parse_price(text: str, currency: str | None = None) -> tuple[Decimal, str]:
    """Parse one displayed amount, rejecting ranges and ambiguous currency symbols."""
    text = text.replace("\u00a0", " ").replace("\u202f", " ").strip()
    if any(sign in text for sign in ("−", "﹣", "－")) or ("(" in text and ")" in text):
        raise APIError(422, "ambiguous_price", "Negative or accounting-formatted prices are not supported.")
    if currency is not None and currency not in CURRENCY_CODES:
        raise APIError(422, "unknown_currency", "Use a supported ISO 4217 fiat currency code.")
    codes = set(_CURRENCY_CODES.findall(text))
    if len(codes) > 1 or (currency and codes and codes != {currency}):
        raise APIError(422, "currency_conflict", "Displayed and specified currencies conflict.")
    currency = currency or next(iter(codes), None)
    for symbol, possible in _SYMBOLS.items():
        if symbol in text:
            if currency and currency not in possible:
                raise APIError(422, "currency_conflict", "Displayed symbol conflicts with the currency.")
            if not currency and symbol == "£":
                currency = "GBP"
            if not currency and len(possible) == 1:
                currency = next(iter(possible))
            elif not currency:
                raise APIError(422, "ambiguous_currency", "Specify an ISO currency for ambiguous symbols such as $ or ¥.")
    if not currency:
        raise APIError(422, "unknown_currency", "An explicit or unambiguous displayed currency is required.")
    numbers = re.findall(r"[+-]?[0-9]+(?:[.,' ][0-9]+)*", text)
    if len(numbers) != 1 or numbers[0].startswith(("-", "+")):
        raise APIError(422, "ambiguous_price", "Select a single nonnegative price, not a range or multiple amounts.")
    raw = numbers[0]
    # Spaces/apostrophes are accepted only as consistent thousands separators.
    if " " in raw or "'" in raw:
        grouping = " " if " " in raw else "'"
        if not re.fullmatch(r"[0-9]{1,3}(?:" + re.escape(grouping) + r"[0-9]{3})+(?:[.,][0-9]{1,2})?", raw):
            raise APIError(422, "ambiguous_price", "Price grouping is ambiguous.")
        raw = raw.replace(grouping, "")
    if "," in raw and "." in raw:
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        whole, fraction = raw.rsplit(decimal_sep, 1)
        western = re.fullmatch(r"[0-9]{1,3}(?:" + re.escape(thousands_sep) + r"[0-9]{3})+", whole)
        indian = thousands_sep == "," and re.fullmatch(r"[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3}", whole)
        if not (western or indian) or not re.fullmatch(r"[0-9]{1,2}", fraction):
            raise APIError(422, "ambiguous_price", "Price separators are ambiguous.")
        raw = whole.replace(thousands_sep, "") + "." + fraction
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        parts = raw.split(sep)
        if currency in {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND", "CLF", "UYW"} and len(parts) == 2 and len(parts[1]) >= 3:
            raise APIError(422, "ambiguous_price", "This currency's fractional precision makes the separator ambiguous.")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            raw = ".".join(parts)
        elif re.fullmatch(r"[0-9]{1,3}(?:" + re.escape(sep) + r"[0-9]{3})+", raw):
            raw = "".join(parts)
        elif sep == "," and re.fullmatch(r"[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3}", raw):
            raw = raw.replace(",", "")
        else:
            raise APIError(422, "ambiguous_price", "Price separators are ambiguous.")
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0 or value > Decimal("1000000000000000"):
            raise InvalidOperation
    except InvalidOperation:
        raise APIError(422, "invalid_price", "Displayed price is outside supported bounds.") from None
    return value, currency


class PriceComparisonService:
    def __init__(self, scraper: ScrapingService | None = None):
        self.scraper = scraper or ScrapingService()

    def compare(self, request: CompareRequest) -> dict:
        if not request.permission_confirmed:
            raise APIError(403, "permission_required", "Confirm permission before scraping websites.")
        results = []
        for index, item in enumerate(request.items):
            row = {"index": index, "url": item.url, "status": "failed"}
            try:
                # Check selectors before performing any network requests.
                import soupsieve
                soupsieve.compile(item.name_selector)
                soupsieve.compile(item.price_selector)
                html = self.scraper.fetch_html(item.url, permission_confirmed=True)
                soup = BeautifulSoup(html, "html.parser")
                names = soup.select(item.name_selector, limit=2)
                prices = soup.select(item.price_selector, limit=2)
                if len(names) != 1 or len(prices) != 1:
                    raise APIError(422, "selector_matches", "Each selector must match exactly one element.")
                title = names[0].get_text(" ", strip=True)[:500]
                price_text = prices[0].get_text(" ", strip=True)
                if not title or not price_text or len(price_text) > 500:
                    raise APIError(422, "invalid_product", "Product title or displayed price is empty or too long.")
                value, currency = parse_price(price_text, item.currency)
                row.update(status="completed", title=title, price_text=price_text, price_value=format(value, "f"), currency=currency)
            except SelectorSyntaxError:
                row["error"] = {"code": "invalid_selector", "message": "A CSS selector is invalid."}
            except APIError as exc:
                row["error"] = {"code": exc.code, "message": exc.message}
            results.append(row)
        groups = []
        for currency in sorted({r["currency"] for r in results if r["status"] == "completed"}):
            rows = [r for r in results if r.get("currency") == currency]
            minimum = min(Decimal(r["price_value"]) for r in rows)
            groups.append({"currency": currency, "lowest_price": format(minimum, "f"),
                           "lowest_item_indexes": [r["index"] for r in rows if Decimal(r["price_value"]) == minimum],
                           "item_count": len(rows)})
        return {"results": results, "currency_groups": groups,
                "product_identity_verified": False,
                "warnings": ["Product identity, shipping, taxes and stock are not verified.",
                             "Prices are compared only within the same currency; no exchange conversion is performed."]}
