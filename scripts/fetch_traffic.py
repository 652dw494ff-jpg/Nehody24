#!/usr/bin/env python3
"""Fetch the public Czech Police traffic XML and create a cautious JSON view.

The XML schema can evolve. This parser intentionally avoids inventing values:
if it cannot identify event records, it publishes an empty list and a warning.
"""
import json
import re
import sys
import urllib.request
import asyncio
import re as regex
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "https://cdi.policie.gov.cz/doprava-web-iframe/mapa"
OUT = Path("data/traffic.json")
KEYWORDS = re.compile(r"nehod|uzav|omezen|provoz|kolon|silnic|dálnic|dalnic|průjezd|prujezd|vozidl|překáž|prekaz|doprav|událost|udalost|havári|havari", re.I)

def local(tag):
    return tag.rsplit("}", 1)[-1].replace("_", " ").replace("-", " ").strip()

def node_text(node):
    return " ".join(" ".join(t.split()) for t in node.itertext() if t and t.strip())

def flatten(node):
    result = {}
    for child in list(node):
        key = local(child.tag)
        value = node_text(child)
        if list(child):
            nested = flatten(child)
            for nk, nv in nested.items():
                result.setdefault(nk, nv)
        elif value:
            result.setdefault(key, value)
    return result

def choose(fields, patterns):
    for key, value in fields.items():
        if any(re.search(p, key, re.I) for p in patterns) and value:
            return value[:700]
    return ""

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Use the official map's own XML-download control. The old direct-download
    # URL published in the catalog currently returns 404, so do not rely on it.
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Chybi Playwright; workflow musi nainstalovat prohlizec Chromium.") from exc

    async def download_xml():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(accept_downloads=True)
            try:
                await page.goto(SOURCE, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
                locator = page.get_by_text(regex.compile(r"St[aá]hnout v[sš]echny dopravn[ií] informace v XML", regex.I)).first
                await locator.wait_for(state="visible", timeout=30000)
                async with page.expect_download(timeout=30000) as download_info:
                    await locator.click()
                download = await download_info.value
                path = await download.path()
                if not path:
                    raise RuntimeError("Oficialni mapa nevytvorila XML soubor ke stazeni.")
                with open(path, "rb") as fh:
                    return fh.read()
            finally:
                await browser.close()

    raw = asyncio.run(download_xml())
    if not raw or b"<" not in raw[:1000]:
        raise RuntimeError("Oficialni mapa nevratila XML dokument.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RuntimeError("Stazeny soubor neni platne XML: " + str(exc)) from exc
    content_type = "application/xml (download from official Police CR map)"

    candidates = []
    seen = set()
    # Prefer event-like nodes with several meaningful child fields.
    for node in root.iter():
        if not list(node):
            continue
        fields = flatten(node)
        if len(fields) < 2:
            continue
        combined = node_text(node)
        if len(combined) < 18:
            continue
        eventish = bool(KEYWORDS.search(local(node.tag) + " " + combined))
        semantic = sum(bool(re.search(r"typ|druh|popis|text|název|nazev|místo|misto|lokal|silnic|komunik|datum|čas|cas|zač|zac|konec|stav|směr|smer|obec|úsek|usek|description|location|road|start|end|title", k, re.I)) for k in fields)
        if not eventish or semantic < 1:
            continue
        # Avoid emitting ancestors that simply repeat an already identified child.
        signature = re.sub(r"\s+", " ", combined).strip().lower()
        if signature in seen:
            continue
        seen.add(signature)
        item = {
            "id": str(len(candidates) + 1),
            "type": choose(fields, [r"typ", r"druh", r"category", r"kind"]) or "Dopravní událost",
            "title": choose(fields, [r"název", r"nazev", r"title", r"typ", r"druh", r"headline"]) or local(node.tag),
            "description": choose(fields, [r"popis", r"description", r"text", r"detail", r"poznám", r"poznam"]) or combined[:700],
            "location": choose(fields, [r"místo", r"misto", r"lokal", r"location", r"obec", r"úsek", r"usek", r"adresa", r"silnic", r"komunik", r"road"]),
            "start": choose(fields, [r"zač", r"zac", r"start", r"od.?datum", r"datum.*od", r"čas", r"cas", r"date", r"time"]),
            "end": choose(fields, [r"konec", r"do.?datum", r"datum.*do", r"end", r"platnost"]),
            "rawTag": local(node.tag),
        }
        candidates.append(item)

    # Keep only the most specific likely records, not huge document wrappers.
    candidates.sort(key=lambda x: len(x.get("description", "")))
    filtered = []
    for item in candidates:
        desc = item["description"]
        if any(desc and desc in old["description"] and len(desc) < len(old["description"]) for old in filtered):
            continue
        filtered.append(item)
    # A conservative ceiling prevents accidental publication of XML wrapper nodes.
    events = filtered[:500]
    warning = None if events else "XML se stáhl, ale automatický parser zatím nerozpoznal strukturu jednotlivých událostí. Zobrazujeme prázdný seznam, nikoli vymyšlená data."
    payload = {
        "source": SOURCE,
        "sourceName": "Policie České republiky – Centrum dopravních informací",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "contentType": content_type,
        "eventCount": len(events),
        "events": events,
        "warning": warning,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zapsano {len(events)} rozpoznanych polozek do {OUT}")
    if warning:
        print(warning)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Chyba pri stahovani dopravnich dat: {exc}", file=sys.stderr)
        sys.exit(1)
