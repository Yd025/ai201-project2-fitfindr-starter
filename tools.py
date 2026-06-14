"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

LLM_MODEL = "llama-3.3-70b-versatile"

_STOP_WORDS = {
    "a", "an", "the", "for", "and", "or", "in", "on", "with", "to", "of",
    "i", "im", "looking", "want", "need", "find", "some", "any", "my",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float = 0.7) -> str:
    """Send a single-turn prompt to Groq and return the response text."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


def _extract_keywords(description: str) -> list[str]:
    """Tokenize a description into searchable keywords."""
    tokens = re.findall(r"[a-z0-9]+", description.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _score_listing(listing: dict, keywords: list[str]) -> int:
    """Score a listing by keyword overlap across searchable fields."""
    if not keywords:
        return 0

    searchable_parts = [
        listing.get("title", ""),
        listing.get("description", ""),
        listing.get("category", ""),
        " ".join(listing.get("style_tags", [])),
        " ".join(listing.get("colors", [])),
        listing.get("brand") or "",
    ]
    searchable_text = " ".join(searchable_parts).lower()

    score = 0
    for keyword in keywords:
        if keyword in searchable_text:
            score += 1
        if keyword in listing.get("title", "").lower():
            score += 2
        if any(keyword in tag.lower() for tag in listing.get("style_tags", [])):
            score += 2

    return score


def _matches_size(listing_size: str, requested_size: str) -> bool:
    """Case-insensitive substring match (e.g., 'M' matches 'S/M')."""
    return requested_size.lower() in listing_size.lower()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()
    keywords = _extract_keywords(description)

    candidates = []
    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue
        if size and not _matches_size(listing["size"], size):
            continue

        score = _score_listing(listing, keywords)
        if score > 0:
            candidates.append((score, listing))

    candidates.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return [listing for _, listing in candidates]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    items = wardrobe.get("items", [])
    item_summary = (
        f"Title: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Description: {new_item.get('description', '')}"
    )

    if not items:
        prompt = f"""You are a personal stylist helping someone who just found a thrift piece but hasn't added their wardrobe yet.

New thrift find:
{item_summary}

Suggest 1-2 complete outfit ideas for this item using general wardrobe staples (e.g., jeans, sneakers, jackets) that would pair well. Describe the vibe, how to style it, and what categories of pieces complement it. Be specific and practical — 2-4 short paragraphs."""
    else:
        wardrobe_lines = []
        for piece in items:
            notes = piece.get("notes") or ""
            note_text = f" ({notes})" if notes else ""
            wardrobe_lines.append(
                f"- {piece['name']} [{piece['category']}] "
                f"colors: {', '.join(piece.get('colors', []))}"
                f"{note_text}"
            )
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = f"""You are a personal stylist helping someone style a new thrift find with pieces they already own.

New thrift find:
{item_summary}

User's existing wardrobe:
{wardrobe_text}

Suggest 1-2 complete outfit combinations that incorporate the new item AND name specific pieces from their wardrobe. Include styling tips (tucking, layering, rolling sleeves, etc.). Be conversational and specific — 2-4 short paragraphs."""

    return _call_llm(prompt, temperature=0.7)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return (
            "Cannot create a fit card: no outfit suggestion was provided. "
            "Run suggest_outfit first."
        )

    prompt = f"""Write a casual, authentic outfit caption for social media (Instagram/TikTok).

Thrifted item: {new_item['title']}
Price: ${new_item['price']:.2f}
Platform: {new_item['platform']}
Outfit idea: {outfit}

Guidelines:
- Sound like a real person posting an OOTD, not a product description
- Mention the item, price, and platform naturally (once each)
- Capture the outfit vibe in specific terms
- 2-4 sentences, can include 1-2 emojis
- Be creative and varied — don't use generic phrases

Write only the caption, nothing else."""

    return _call_llm(prompt, temperature=0.9)
