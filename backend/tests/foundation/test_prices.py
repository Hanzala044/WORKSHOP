from decimal import Decimal

import pytest

from app.core.errors import APIError
from app.schemas.pricepilot import CompareRequest
from app.services.price_comparison_service import PriceComparisonService, parse_price


@pytest.mark.parametrize("text,currency,value,code", [
    ("USD 1,234.56", None, "1234.56", "USD"),
    ("1.234,56 €", None, "1234.56", "EUR"),
    ("₹ 1,29,999", None, "129999", "INR"),
    ("₹ 1,29,999.50", None, "129999.50", "INR"),
    ("1 234,56 EUR", None, "1234.56", "EUR"),
    ("CHF 1'234.50", None, "1234.50", "CHF"),
    ("£0.00", None, "0.00", "GBP"),
    ("$12.10", "CAD", "12.10", "CAD"),
    ("9.99", "USD", "9.99", "USD"),
])
def test_decimal_parsing(text, currency, value, code):
    amount, actual = parse_price(text, currency)
    assert amount == Decimal(value)
    assert actual == code


@pytest.mark.parametrize("text,currency", [
    ("$9.99", None), ("¥500", None), ("9.99", None), ("€10", "USD"),
    ("USD EUR 10", None), ("USD 10 - 20", None), ("USD -10", None),
    ("USD 12,34,56", None), ("USD 100 80", None), ("USD free", None),
    ("ARS 10", "USD"), ("USD −10", None), ("(USD 10)", None),
    ("KWD 1.234", None), ("XYZ 10", "XYZ"),
])
def test_ambiguous_prices_are_not_guessed(text, currency):
    with pytest.raises(APIError):
        parse_price(text, currency)


def test_mixed_currencies_and_ties():
    class Scraper:
        def fetch_html(self, url, permission_confirmed):
            assert permission_confirmed
            if "bad" in url:
                raise APIError(403, "host_not_allowed", "Host is not permitted.")
            return b"<h1>Not guaranteed same product</h1><b>0.10</b>"

    request = CompareRequest.model_validate({"permission_confirmed": True, "items": [
        {"url": "https://example.com/a", "price_selector": "b", "currency": "USD"},
        {"url": "https://example.com/b", "price_selector": "b", "currency": "USD"},
        {"url": "https://example.com/c", "price_selector": "b", "currency": "EUR"},
        {"url": "https://example.com/bad", "price_selector": "b", "currency": "USD"},
    ]})
    result = PriceComparisonService(Scraper()).compare(request)
    assert len(result["currency_groups"]) == 2
    usd = next(g for g in result["currency_groups"] if g["currency"] == "USD")
    assert usd["lowest_price"] == "0.10"
    assert usd["lowest_item_indexes"] == [0, 1]
    assert result["results"][-1]["error"]["code"] == "host_not_allowed"


def test_selectors_must_match_exactly_one():
    class Scraper:
        def fetch_html(self, *args, **kwargs):
            return b"<h1>Example</h1><b>USD 1</b><b>USD 2</b>"
    body = {"permission_confirmed": True, "items": [{"url": "https://x.example", "price_selector": "b"}]}
    result = PriceComparisonService(Scraper()).compare(CompareRequest.model_validate(body))
    assert result["results"][0]["error"]["code"] == "selector_matches"
