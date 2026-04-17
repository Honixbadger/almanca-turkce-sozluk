#!/usr/bin/env python3
"""
Fetch example sentences (Beispiele) from German Wiktionary for a list of verbs.
Input:  orneksiz_batch_2.json  (list of ~1917 German verbs)
Output: ornekler_batch_2.json  (dict: verb -> list of example sentences, max 3)
Progress is saved every 100 verbs to avoid data loss on interruption.
"""

import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error
import sys
import os

INPUT_FILE  = "C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/orneksiz_batch_1.json"
OUTPUT_FILE = "C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/ornekler_batch_1.json"
BATCH_SIZE  = 50
MAX_EXAMPLES = 3
SAVE_EVERY  = 100   # verbs processed before intermediate save
API_URL     = "https://de.wiktionary.org/w/api.php"
DELAY_SECS  = 0.5   # polite delay between API calls


def fetch_pages(titles):
    """Fetch wikitext for up to 50 titles in one API request."""
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "revisions",
        "rvprop": "content",
        "format": "json",
        "rvslots": "main",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozlukBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [WARN] API request failed: {e}", flush=True)
        return None


def extract_examples(wikitext, verb):
    """
    Extract up to MAX_EXAMPLES example sentences from wikitext.
    German Wiktionary uses {{Beispiele}} as a template marker (not a section header).
    Example lines follow directly with ':' prefix.
    Returns a list of cleaned example strings (may be empty).
    """
    if not wikitext:
        return []

    # German Wiktionary marks the examples block with the template {{Beispiele}}
    # Sometimes also written as {{Beispiele|...}} with parameters
    # Find the first occurrence of {{Beispiele (within the German language section)
    # Strategy: find {{Beispiele}} and read the colon-prefixed lines that follow.

    # First restrict to the German language section to avoid picking up other languages
    # German section starts with == word ({{Sprache|Deutsch}}) ==
    de_section_match = re.search(r'==\s*\w.*?\{\{Sprache\|Deutsch\}\}.*?==', wikitext)
    if de_section_match:
        # Find end of German section: next == something == at same level (not ===)
        de_start = de_section_match.start()
        next_l2 = re.search(r'\n==\s*\w', wikitext[de_section_match.end():])
        if next_l2:
            de_end = de_section_match.end() + next_l2.start()
        else:
            de_end = len(wikitext)
        wikitext = wikitext[de_start:de_end]

    # Look for {{Beispiele}} or {{Beispiele fehlen}}
    beispiele_idx = wikitext.find('{{Beispiele')
    if beispiele_idx == -1:
        return []

    # Check for fehlen immediately after
    line_end = wikitext.find('\n', beispiele_idx)
    beispiele_line = wikitext[beispiele_idx:line_end if line_end != -1 else beispiele_idx+50]
    if 'fehlen' in beispiele_line:
        return []

    # Extract the block after {{Beispiele...}} until the next {{...}} template block
    # or next section marker
    block_start = line_end + 1 if line_end != -1 else beispiele_idx + len('{{Beispiele}}')
    # Find where the block ends: next {{ that is at the start of a line, or next == heading
    block_end_match = re.search(r'\n\{\{|\n==', wikitext[block_start:])
    if block_end_match:
        block = wikitext[block_start:block_start + block_end_match.start()]
    else:
        block = wikitext[block_start:]

    examples = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith(":"):
            continue
        # Remove leading colons and whitespace
        text = re.sub(r'^:+\s*', '', line)
        # Remove reference markers like [1], [1, 2], [1–3] etc.
        text = re.sub(r'^\[\d[\d,\s\u2013-]*\]\s*', '', text)
        # Remove italic markup ''
        text = re.sub(r"''", '', text)
        # Remove wikilinks [[word|display]] -> display, or [[word]] -> word
        text = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', text)
        # Remove template calls {{...}} (including nested, simple approach)
        text = re.sub(r'\{\{[^}]*\}\}', '', text)
        # Remove HTML tags and ref tags
        text = re.sub(r'<ref[^>]*/?>.*?</ref>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        # Remove external links [URL text] -> text, or bare [URL]
        text = re.sub(r'\[https?://\S+ ([^\]]+)\]', r'\1', text)
        text = re.sub(r'\[https?://\S+\]', '', text)
        # Clean up multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) < 5:
            continue
        if text.startswith("|") or text.startswith("="):
            continue
        examples.append(text)
        if len(examples) >= MAX_EXAMPLES:
            break

    return examples


def load_existing_output():
    """Load existing output file if it exists (for resume support)."""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_output(results):
    """Save results dict to output JSON file."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def main():
    # Load input verbs
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        verbs = json.load(f)
    total = len(verbs)
    print(f"Loaded {total} verbs from input file.", flush=True)

    # Load any existing results (resume support)
    results = load_existing_output()
    already_done = set(results.keys())
    print(f"Already have examples for {len(already_done)} verbs.", flush=True)

    # Filter to verbs not yet processed
    remaining = [v for v in verbs if v not in already_done]
    print(f"Remaining to process: {len(remaining)} verbs.", flush=True)

    processed_since_save = 0
    total_with_examples = len(already_done)

    for batch_start in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Batch {batch_num}/{total_batches}: fetching {len(batch)} verbs ...", flush=True)

        data = fetch_pages(batch)
        if data is None:
            # Retry once after a longer wait
            print("  Retrying batch after 5s ...", flush=True)
            time.sleep(5)
            data = fetch_pages(batch)
            if data is None:
                print("  [ERROR] Batch failed twice, skipping.", flush=True)
                continue

        pages = data.get("query", {}).get("pages", {})

        for page_id, page_data in pages.items():
            title = page_data.get("title", "")
            # Get wikitext from revisions
            revisions = page_data.get("revisions", [])
            if not revisions:
                continue
            rev = revisions[0]
            # Handle both old and new API slot formats
            if "slots" in rev:
                wikitext = rev["slots"].get("main", {}).get("*", "")
            else:
                wikitext = rev.get("*", "")

            examples = extract_examples(wikitext, title)
            if examples:
                results[title] = examples
                total_with_examples += 1

            processed_since_save += 1

        # Save every SAVE_EVERY verbs
        if processed_since_save >= SAVE_EVERY:
            save_output(results)
            print(f"  [SAVE] Progress saved. {total_with_examples} verbs with examples so far.", flush=True)
            processed_since_save = 0

        time.sleep(DELAY_SECS)

    # Final save
    save_output(results)
    print(f"\nDone! {total_with_examples} verbs with examples out of {total} total.", flush=True)
    print(f"Output written to: {OUTPUT_FILE}", flush=True)


if __name__ == "__main__":
    main()
