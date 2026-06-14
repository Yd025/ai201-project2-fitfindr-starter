"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Uses regex — no LLM call. Documented in planning.md.
    """
    text = query.strip()
    max_price = None
    size = None

    price_match = re.search(
        r"(?:under|below|max|less than)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if price_match:
        max_price = float(price_match.group(1))

    size_match = re.search(
        r"(?:size|sz)\s*[:\s]?\s*([A-Za-z0-9]+(?:\s*/\s*[A-Za-z0-9]+)?)",
        text,
        re.IGNORECASE,
    )
    if not size_match:
        size_match = re.search(
            r"\bin\s+size\s+([A-Za-z0-9]+(?:\s*/\s*[A-Za-z0-9]+)?)",
            text,
            re.IGNORECASE,
        )
    if size_match:
        size = size_match.group(1).strip()

    description = text
    for pattern in [
        r"(?:under|below|max|less than)\s*\$?\s*\d+(?:\.\d+)?",
        r"(?:size|sz)\s*[:\s]?\s*[A-Za-z0-9]+(?:\s*/\s*[A-Za-z0-9]+)?",
        r"\bin\s+size\s+[A-Za-z0-9]+(?:\s*/\s*[A-Za-z0-9]+)?",
        r"\b(?:i mostly wear|what'?s out there|how would i style|what do you think)\b.*",
        r"[?.!]+$",
    ]:
        description = re.sub(pattern, "", description, flags=re.IGNORECASE)

    description = re.sub(
        r"\b(?:looking for|i'm looking for|i am looking for|find me|search for)\b",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = " ".join(description.split()).strip(" ,.-")

    if not description:
        description = text

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _format_search_error(parsed: dict) -> str:
    """Build an actionable error message when search returns no results."""
    desc = parsed.get("description", "your query")
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    size_clause = f" in size {size}" if size else ""
    price_clause = f" under ${max_price:g}" if max_price is not None else ""

    return (
        f"No listings found for '{desc}'{size_clause}{price_clause}. "
        "Try broadening your search — use more general keywords, raise your "
        "max price, or remove the size filter."
    )


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    session = _new_session(query, wardrobe)

    session["parsed"] = parse_query(query)
    parsed = session["parsed"]

    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed.get("size"),
        max_price=parsed.get("max_price"),
    )

    if not session["search_results"]:
        session["error"] = _format_search_error(parsed)
        return session

    session["selected_item"] = session["search_results"][0]

    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    if not session["outfit_suggestion"] or not session["outfit_suggestion"].strip():
        session["error"] = (
            "Could not generate an outfit suggestion. Please try again."
        )
        return session

    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    if session["fit_card"].startswith("Cannot create a fit card"):
        session["error"] = session["fit_card"]
        session["fit_card"] = None

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
