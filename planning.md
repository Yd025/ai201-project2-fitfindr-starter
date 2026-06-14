# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Looks through the mock listings dataset and finds items that match what the user described. It can also filter by size and max price if the user included those. Results come back sorted by relevance — best match first.

**Input parameters:**
- `description` (str): What the user is looking for, like "vintage graphic tee". I score each listing by how many of these keywords show up in the title, description, style tags, and category.
- `size` (str | None): Optional size filter. Case-insensitive substring match, so "M" will match "S/M" or just "M". Pass None to skip.
- `max_price` (float | None): Optional price ceiling. Anything over this gets filtered out. Pass None to skip.

**What it returns:**
A `list[dict]` of matching listings, best match first. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list[str]), `size`, `condition`, `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). If nothing matches, it returns an empty list `[]` — no exception thrown.

**What happens if it fails or returns nothing:**
The agent stops right there. It sets `session["error"]` to something like: "No listings found for 'designer ballgown' in size XXS under $5. Try broadening your search — remove the size filter, raise your max price, or use more general keywords like 'dress' instead of 'ballgown'." It does not call `suggest_outfit` or `create_fit_card` with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the item the user found and their existing wardrobe, then asks the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 outfit combos. If they have wardrobe items saved, the suggestion names specific pieces from their closet. If their wardrobe is empty, it still gives useful general styling advice.

**Input parameters:**
- `new_item` (dict): A listing dict from `search_listings` — the thrift piece they're thinking about buying.
- `wardrobe` (dict): Their wardrobe, with an `items` key holding a list of item dicts (`id`, `name`, `category`, `colors`, `style_tags`, `notes`).

**What it returns:**
A `str` with outfit suggestions, usually 2–4 paragraphs. Should never be empty and should never raise an exception.

**What happens if it fails or returns nothing:**
Empty wardrobe isn't actually a failure — the tool just switches to general styling advice (what kinds of bottoms/shoes/layers would work, what vibe the piece gives off) and keeps going. The agent stores the result in `session["outfit_suggestion"]` and moves on to `create_fit_card`. If the Groq call itself fails, the agent sets `session["error"]` and tells the user to try again.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion into a short social media caption — the kind of thing you'd actually post on Instagram or TikTok after a thrift haul. Uses Groq (llama-3.3-70b-versatile) at temperature 0.9 so it doesn't sound identical every time. Works in the item name, price, and platform without being stiff about it.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`.
- `new_item` (dict): The listing dict for the thrifted item.

**What it returns:**
A `str`, 2–4 sentences, written like a casual OOTD post. Should read differently on different runs even with the same input. If `outfit` is empty or just whitespace, returns an error message string instead of crashing.

**What happens if it fails or returns nothing:**
If the outfit string is missing, the tool returns: `"Cannot create a fit card: no outfit suggestion was provided. Run suggest_outfit first."` The agent puts that in the fit card panel. If the LLM call fails, same deal — `session["error"]` gets set.

---

### Additional Tools (if any)

None — just the three required tools for now.

---

## Planning Loop

**How does your agent decide which tool to call next?**

It's a straight-line loop, but it bails out early if something goes wrong. The agent doesn't just run all three tools no matter what — it actually looks at what came back before deciding what to do next.

1. Start a fresh `session` with `_new_session(query, wardrobe)`.
2. Parse the query with regex to pull out `description`, `size`, and `max_price`. Stick that in `session["parsed"]`.
3. Call `search_listings` with those parsed values. Save results in `session["search_results"]`.
   - If the list is empty → write a helpful error to `session["error"]` and return immediately. Don't touch the other tools.
   - If there are results → grab the top one and save it as `session["selected_item"]`.
4. Call `suggest_outfit(selected_item, wardrobe)`. Save the string in `session["outfit_suggestion"]`.
   - If that comes back empty for some reason → set `session["error"]` and return.
5. Call `create_fit_card(outfit_suggestion, selected_item)`. Save in `session["fit_card"]`.
   - If the result starts with "Cannot create" → that's an error, put it in `session["error"]`.
6. Return the session.

Done when all three tools succeed, or when an error branch cuts things short. The big conditional is step 3 — no search results means no outfit suggestion and no fit card.

For parsing, I'm using regex instead of the LLM. `under $30` or `under 30` grabs the price, `size M` or `in size M` grabs the size, and whatever's left after stripping that stuff becomes the description. Keeps things fast and predictable.

---

## State Management

**How does information from one tool get passed to the next?**

Everything lives in one `session` dict for the whole interaction. No re-prompting the user, no hardcoded values between steps.

| Field | Set when | Used by |
|-------|----------|---------|
| `query` | Start | Debugging / reference |
| `parsed` | After parsing | Inputs for `search_listings` |
| `search_results` | After search | Picking `selected_item` |
| `selected_item` | After search (top result) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | Start (from UI choice) | `suggest_outfit` |
| `outfit_suggestion` | After suggest | `create_fit_card` |
| `fit_card` | After fit card | Final UI output |
| `error` | When something fails | Tells the UI to stop |

So the listing from `search_listings` goes into `session["selected_item"]` and that's the exact same dict `suggest_outfit` receives. Same thing with the outfit string — `session["outfit_suggestion"]` is what `create_fit_card` gets. The Gradio app just reads these fields once `run_agent()` finishes.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` to something like: "No listings found for 'designer ballgown' in size XXS under $5. Try broadening your search — use more general keywords, raise your max price, or remove the size filter." `selected_item`, `outfit_suggestion`, and `fit_card` all stay `None`. Doesn't call the other tools. |
| suggest_outfit | Wardrobe is empty | Not treated as an error. Tool gives general styling advice anyway. Agent keeps going and still generates a fit card. |
| create_fit_card | Outfit input is missing or incomplete | Tool returns an error string. Agent sets `session["error"]` and the fit card panel shows that message. |

---

## Architecture

```mermaid
flowchart TD
    U[User query] --> PL[Planning Loop]
    PL --> P[Parse query → session.parsed]
    P --> SL[search_listings]
    SL -->|results=[]| ERR1[session.error = actionable message]
    ERR1 --> RET[Return session]
    SL -->|results=[item,...]| SI[session.selected_item = results0]
    SI --> SO[suggest_outfit selected_item, wardrobe]
    SO --> OS[session.outfit_suggestion]
    OS --> FC[create_fit_card outfit_suggestion, selected_item]
    FC --> FCOUT[session.fit_card]
    FCOUT --> RET
    W[Wardrobe dict] --> SO
```

```
User query
    │
    ▼
Planning Loop ───────────────────────────────────────────┐
    │                                                    │
    ├─► Parse query → session["parsed"]                  │
    │                                                    │
    ├─► search_listings(description, size, max_price)    │
    │       │ results=[]                                 │
    │       ├──► [ERROR] actionable message → return     │
    │       │                                            │
    │       │ results=[item, ...]                        │
    │       ▼                                            │
    │   Session: selected_item = results[0]              │
    │       │                                            │
    ├─► suggest_outfit(selected_item, wardrobe)          │
    │       │                                            │
    │   Session: outfit_suggestion = "..."               │
    │       │                                            │
    └─► create_fit_card(outfit_suggestion, selected_item)│
            │                                            │
        Session: fit_card = "..."                        │
            │                                            └─ error path returns here
            ▼
        Return session
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`, I'll give Cursor Composer 2.5 my Tool 1 block from this file (inputs, return value, failure mode) plus the `load_listings()` signature from `utils/data_loader.py`, and ask it to implement the function in `tools.py`. Before I trust it, I'll check that it actually filters on all three parameters and returns `[]` instead of crashing when nothing matches. Then I'll test it with three queries: a normal one like "vintage graphic tee", an impossible one like "designer ballgown size XXS under $5", and a price-filter check.

For `suggest_outfit`, I'll paste the Tool 2 spec and the wardrobe schema from `data/wardrobe_schema.json` into Composer 2.5 and ask it to write the Groq prompt. I'll verify it handles the empty wardrobe case separately from the normal case — run it once with `get_example_wardrobe()` and once with `get_empty_wardrobe()` and make sure both return a real string, not `""`.

For `create_fit_card`, I'll give Composer 2.5 the Tool 3 spec and mention the temperature 0.9 requirement so captions don't come out identical every time. I'll run it twice on the same input to confirm the output actually varies, and call it with an empty outfit string to make sure I get the error message back instead of an exception.

**Milestone 4 — Planning loop and state management:**

I'll share the ASCII diagram plus my Planning Loop and State Management sections with Composer 2.5 and ask it to implement `run_agent()` in `agent.py`. When I get the code back, I'll check three things before running it: does it branch when `search_results` is empty? Does it actually write to the session dict between steps? And does it skip `suggest_outfit` on the no-results path? Then I'll run `python agent.py` — the happy path should print a listing, outfit, and fit card; the ballgown query should set `session["error"]` and leave `fit_card` as `None`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

FitFindr takes a natural language request, finds a matching listing, styles it against the user's wardrobe, and writes a shareable caption. Each step only runs if the one before it worked — if the search comes up empty, the agent tells the user what to change and stops.

**Step 1:**
The agent parses the query into `{description: "vintage graphic tee", size: None, max_price: 30.0}` and calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. That returns a handful of matches. Top result is the Vintage Band Tee — Faded Grey ($19 on depop). The agent saves that as `session["selected_item"]`.

**Step 2:**
It calls `suggest_outfit(selected_item, wardrobe)` using the example wardrobe (baggy jeans, chunky sneakers, etc.). The LLM comes back with something like: "Pair this faded band tee with your baggy straight-leg jeans and chunky white sneakers for a classic 90s grunge look. Throw your vintage black denim jacket on top if it's cold."

**Step 3:**
It calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM writes a caption along the lines of: "thrifted this faded band tee off depop for $19 and it was literally made for my baggy jeans era 🖤 full fit on my stories"

**Final output to user:**
Three panels in the Gradio UI: the listing details (title, price, platform, condition), the outfit suggestion naming actual wardrobe pieces, and the fit card caption.

**Error path example:** If the user types "designer ballgown size XXS under $5", `search_listings` returns `[]`. The agent sets an error like "No listings found... Try broadening your search" and only the first panel shows anything — outfit and fit card stay blank.
