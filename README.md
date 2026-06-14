# FitFindr

FitFindr is a thrift shopping agent — you tell it what you're looking for, it searches mock listings, figures out how to style the best match with your wardrobe, and writes a shareable outfit caption. The interesting part isn't any single tool; it's the planning loop that decides what to call next and what to do when a search comes up empty.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Free key at [console.groq.com](https://console.groq.com) — same one from Project 1.

## Run

```bash
python app.py       # Gradio UI
python agent.py     # CLI test (happy path + no-results path)
pytest tests/       # search tests work without API key; LLM tests need GROQ_API_KEY
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

Searches the mock listings dataset and returns matches sorted by relevance.

- **Inputs:** `description` (str) — keywords to search for; `size` (str | None) — optional, case-insensitive substring match; `max_price` (float | None) — optional price ceiling
- **Output:** `list[dict]` — each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Empty list if nothing matches.
- **Purpose:** Find thrift listings that fit what the user asked for.

### `suggest_outfit(new_item, wardrobe)`

Suggests 1–2 outfit combos using the found item and pieces from the user's wardrobe.

- **Inputs:** `new_item` (dict) — a listing from search; `wardrobe` (dict) — user's closet with an `items` list
- **Output:** `str` — a few paragraphs of styling advice. Uses Groq `llama-3.3-70b-versatile`.
- **Purpose:** Help the user figure out how to actually wear the piece.

### `create_fit_card(outfit, new_item)`

Writes a casual social media caption for the outfit.

- **Inputs:** `outfit` (str) — the suggestion from `suggest_outfit`; `new_item` (dict) — the listing
- **Output:** `str` — 2–4 sentences, Instagram/TikTok style. Temperature 0.9 so it varies between runs. Returns an error string if `outfit` is empty.
- **Purpose:** Give the user something they can actually copy and post.

---

## Planning Loop

`run_agent()` in `agent.py` runs the tools in order, but it checks what came back before moving on:

1. Parse the query with regex → pull out `description`, `size`, `max_price` into `session["parsed"]`
2. Call `search_listings`. If nothing comes back, set `session["error"]` with a specific message and stop — don't call the other two tools
3. Otherwise, save the top result as `session["selected_item"]` and call `suggest_outfit`
4. Call `create_fit_card` with the outfit string and selected item
5. Return the session

The agent doesn't run the same three tools in a fixed sequence every time. Try `"designer ballgown size XXS under $5"` — search returns nothing, so `suggest_outfit` and `create_fit_card` never get called. Compare that to `"vintage graphic tee under $30"` where all three run.

---

## State Management

One `session` dict holds everything for a single interaction:

- `parsed` — what got extracted from the query, used as search inputs
- `search_results` — full list from search
- `selected_item` — top match, passed straight into `suggest_outfit` and `create_fit_card`
- `outfit_suggestion` — what `suggest_outfit` returned, passed into `create_fit_card`
- `fit_card` — final caption
- `error` — set if something failed early

The user doesn't re-enter anything between steps. The listing `search_listings` found is the same dict `suggest_outfit` receives via `session["selected_item"]`. Same for the outfit string going into `create_fit_card`.

---

## Error Handling

**search_listings — no matches:** The agent stops and tells the user what to try. Example from testing: query `"designer ballgown size XXS under $5"` → error message in the listing panel, outfit and fit card panels stay empty. It never calls `suggest_outfit` with nothing to work with.

**suggest_outfit — empty wardrobe:** Not really a failure. The tool switches to general styling advice (what kinds of pieces would pair well) and the agent keeps going. Tested with `get_empty_wardrobe()` — still get a useful string back.

**create_fit_card — missing outfit:** Passing an empty string returns `"Cannot create a fit card: no outfit suggestion was provided. Run suggest_outfit first."` instead of throwing an exception. Verified with:
```bash
python -c "from tools import search_listings, create_fit_card; r = search_listings('vintage graphic tee', size=None, max_price=50); print(create_fit_card('', r[0]))"
```

---

## Spec Reflection

Writing the tool specs in `planning.md` before touching code was the most useful part. I already knew the agent had to stop if search returned nothing, so when I got to `run_agent()` it was mostly connecting session fields to tool calls instead of figuring out the logic on the fly.

One thing I changed: the starter suggested using the LLM to parse queries, but I went with regex instead. Didn't want an extra API call on every interaction, and regex handles the common cases fine (`under $30`, `size M`). Tradeoff is it won't catch weirder phrasing, but it's easier to test.

---

## AI Usage

### Instance 1 — Building the three tools

I gave Cursor Composer 2.5 my Tool 1 spec from `planning.md` (inputs, return value, what to do on empty results) and asked it to implement `search_listings()` using `load_listings()` from the data loader. It got the basic structure right but the keyword scoring treated all fields equally — I changed it so matches in `title` and `style_tags` count more. For `create_fit_card`, Composer's first prompt made captions sound like product listings, so I rewrote the prompt to push for casual OOTD tone and bumped temperature to 0.9.

### Instance 2 — Wiring up the planning loop

I pasted my ASCII architecture diagram and the Planning Loop + State Management sections into Composer 2.5 and asked for `run_agent()` in `agent.py`. The generated version had the right flow but the no-results error message was too generic ("no results found"). I rewrote it to echo back the actual description, size, and price from the parsed query so the user knows exactly what failed. Also pulled `parse_query` into its own function so I could test parsing without running the whole agent.

---

## Project Structure

```
├── agent.py              # Planning loop and query parsing
├── app.py                # Gradio UI
├── tools.py              # The three tools
├── planning.md           # Spec (written before implementation)
├── tests/test_tools.py   # pytest — one test per failure mode
├── data/
│   ├── listings.json
│   └── wardrobe_schema.json
└── utils/data_loader.py
```
