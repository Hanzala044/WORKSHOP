# Day 1 — Web Scraping and Product Price Comparison

## Configure it
Edit `products.json`. For each product page, supply:
- `site`: display label
- `url`: full product page URL
- `name_selector`: CSS selector for the product title
- `price_selector`: CSS selector for the displayed price
- `currency`: currency code/symbol

The included `example.com` URL is only a placeholder and will not produce a real product result. Replace it with product pages you are allowed to access.

## Find selectors
Open the product page in a browser, inspect the title and price element, and copy a stable CSS selector. Some sites render prices with JavaScript or block automated requests; this simple Requests/BeautifulSoup version will not handle every site. Do not attempt to bypass protections. Use an official API or permitted data source when available.

## Run
```bash
pip install -r requirements.txt
python app.py
```
The result is saved to `price_comparison.csv`.

## Test and explain
The program downloads HTML, parses it with BeautifulSoup, extracts the selected elements, parses a numeric price, and writes the results to CSV. A missing selector is reported as `check selectors`, not silently treated as a correct result.
