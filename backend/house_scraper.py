"""Scrape house listing details from move.nl pages."""

import re

import httpx
from bs4 import BeautifulSoup


async def scrape_move_nl(url: str) -> dict:
    """Scrape a move.nl listing page and return structured data.

    Returns dict with: address, city, price, sqm, rooms, year_built,
    energy_label, summary, photos_url, listing_url.
    """
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    data: dict = {"listing_url": url}

    # Address — usually in the main heading
    h1 = soup.find("h1")
    if h1:
        data["address"] = h1.get_text(strip=True)

    # Try to extract city from breadcrumb or subtitle
    subtitle = soup.find("h2") or soup.find(class_=re.compile(r"subtitle|location|city", re.I))
    if subtitle:
        data["city"] = subtitle.get_text(strip=True)

    # Extract key facts from the page text
    page_text = soup.get_text(" ", strip=True)

    # Price — look for euro amounts
    price_match = re.search(r"€\s*([\d.,]+)", page_text)
    if price_match:
        price_str = price_match.group(1).replace(".", "").replace(",", "")
        try:
            data["price"] = int(price_str)
        except ValueError:
            pass

    # Square meters
    sqm_match = re.search(r"(\d+)\s*m²", page_text)
    if sqm_match:
        data["sqm"] = int(sqm_match.group(1))

    # Rooms/kamers
    rooms_match = re.search(r"(\d+)\s*(?:kamer|room|slaapkamer)", page_text, re.I)
    if rooms_match:
        data["rooms"] = int(rooms_match.group(1))

    # Year built
    year_match = re.search(r"(?:bouwjaar|built|jaar)\s*:?\s*(\d{4})", page_text, re.I)
    if year_match:
        data["year_built"] = int(year_match.group(1))

    # Energy label
    label_match = re.search(r"(?:energielabel|energy\s*label)\s*:?\s*([A-G]\+{0,4})", page_text, re.I)
    if label_match:
        data["energy_label"] = label_match.group(1).upper()

    # Photos URL — look for photo/media links
    photo_link = soup.find("a", href=re.compile(r"foto|photo|media", re.I))
    if photo_link:
        data["photos_url"] = photo_link.get("href", "")

    # Summary — meta description or first paragraph
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        data["summary"] = meta_desc.get("content", "")[:500]
    elif not data.get("summary"):
        first_p = soup.find("p")
        if first_p:
            data["summary"] = first_p.get_text(strip=True)[:500]

    return data
