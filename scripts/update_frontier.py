import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

DISCORD_API_BASE = "https://discord.com/api/v10"
OUTPUT_FILE = Path("frontier-comms.json")

URL_REGEX = re.compile(r"https?://[^\s<>()\"]+")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_links_and_source(message: dict) -> tuple[list[dict], str]:
    raw_sources = []

    content = message.get("content") or ""
    for m in URL_REGEX.findall(content):
        raw_sources.append(m.rstrip(".,);]"))

    for emb in message.get("embeds") or []:
        if emb.get("url"):
            raw_sources.append(emb["url"])
        for field in emb.get("fields") or []:
            val = field.get("value") or ""
            for m in URL_REGEX.findall(val):
                raw_sources.append(m.rstrip(".,);]"))

    seen = set()
    links = []
    source_tag = "FRONTIER"

    for url in raw_sources:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""

        if "x.com" in host or "twitter.com" in host:
            label = "Apri post su X"
            if source_tag == "FRONTIER":
                source_tag = "X / FRONTIER"
        elif "youtube.com" in host or "youtu.be" in host:
            label = "Guarda su YouTube"
            source_tag = "YOUTUBE"
        elif "elitedangerous.com" in host or "frontierstore.net" in host or "forums.frontier.co.uk" in host:
            label = "Leggi su Frontier"
            source_tag = "FRONTIER"
        elif "inara.cz" in host:
            label = "Vedi su Inara"
            source_tag = "INARA"
        else:
            label = f"Apri link ({host or 'esterno'})"
            if source_tag == "FRONTIER" and host:
                source_tag = host.split(".")[0].upper()[:12]

        links.append({"url": url, "label": label})

    return links, source_tag


def build_summary(message: dict) -> str:
    parts = []
    content = (message.get("content") or "").strip()
    if content:
        cleaned_content = URL_REGEX.sub("", content).strip()
        cleaned_content = re.sub(r"\n{3,}", "\n\n", cleaned_content).strip()
        if cleaned_content:
            parts.append(cleaned_content)

    for emb in message.get("embeds") or []:
        emb_title = clean_text(emb.get("title") or "")
        emb_desc = (emb.get("description") or "").strip()
        emb_author = clean_text((emb.get("author") or {}).get("name") or "")
        if emb_author and emb_author.lower() not in {"elite dangerous", "x"}:
            parts.append(f"Fonte anteprima: {emb_author}")
        if emb_title and emb_title.lower() not in {"x", "youtube"}:
            parts.append(emb_title)
        if emb_desc:
            parts.append(emb_desc)

    for att in message.get("attachments") or []:
        att_url = att.get("url") or ""
        if att_url:
            parts.append(f"Allegato: {att_url}")

    return "\n\n".join(parts).strip() or "Nuova comunicazione Frontier inoltrata nel canale #notizie."


def parse_messages(messages: list[dict]) -> list[dict]:
    items = []
    for msg in messages:
        if msg.get("type") in {7, 18, 19}:
            continue

        links, tag = extract_links_and_source(msg)
        summary = build_summary(msg)

        if not summary and not links:
            continue

        ts_raw = msg.get("timestamp") or ""
        date_str = ts_raw[:10] if len(ts_raw) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")

        author_obj = msg.get("author") or {}
        author_name = author_obj.get("global_name") or author_obj.get("username") or "Elite Dangerous Italia"

        first_line = clean_text(summary.splitlines()[0]) if summary else ""
        if first_line and len(first_line) > 95:
            title = first_line[:92].rsplit(" ", 1)[0] + "..."
        elif first_line:
            title = first_line
        elif links:
            title = links[0]["label"]
        else:
            title = f"Dispaccio Frontier ({date_str})"

        image_url = ""
        for att in msg.get("attachments") or []:
            ctype = (att.get("content_type") or "").lower()
            if ctype.startswith("image/") and att.get("url"):
                image_url = att["url"]
                break
        if not image_url:
            for emb in msg.get("embeds") or []:
                if (emb.get("image") or {}).get("url"):
                    image_url = emb["image"]["url"]
                    break
                if (emb.get("thumbnail") or {}).get("url"):
                    image_url = emb["thumbnail"]["url"]
                    break

        items.append({
            "id": f"dc-{msg.get('id')}",
            "title": title,
            "date": date_str,
            "author": author_name,
            "tag": tag,
            "image": image_url,
            "summary": summary,
            "links": links,
        })

    return items


def load_existing() -> list[dict] | None:
    if not OUTPUT_FILE.exists():
        return None
    try:
        data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        return None
    return None


def main():
    token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
    channel_id = (os.environ.get("DISCORD_CHANNEL_ID") or "").strip()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not token or not channel_id:
        existing = load_existing()
        if existing:
            print("DISCORD_BOT_TOKEN o DISCORD_CHANNEL_ID non impostati. Mantengo frontier-comms.json esistente.")
            return
        fallback = [
            {
                "id": "fdev-standby",
                "title": "In attesa configurazione feed Discord #notizie",
                "date": now_iso[:10],
                "author": "Frontier Developments",
                "tag": "ROADMAP",
                "image": "",
                "summary": "Configura i secret DISCORD_BOT_TOKEN e DISCORD_CHANNEL_ID nel workflow per sincronizzare automaticamente patch, roadmap e annunci.",
                "links": [],
            }
        ]
        OUTPUT_FILE.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Salvato stato iniziale in frontier-comms.json.")
        return

    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages?limit=25"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "ULADCommsBot (https://armandobug.github.io/uladsite/, 1.0)",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=25)
        resp.raise_for_status()
        messages = resp.json()
    except Exception as exc:
        print(f"Errore durante la lettura del canale Discord: {exc}")
        existing = load_existing()
        if existing:
            print("Mantengo i dati esistenti in frontier-comms.json.")
            return
        raise

    parsed = parse_messages(messages if isinstance(messages, list) else [])
    if not parsed:
        existing = load_existing()
        if existing:
            print("Nessun messaggio utile trovato in questa lettura. Mantengo i dati esistenti.")
            return
        parsed = [
            {
                "id": "fdev-empty",
                "title": "Nessuna comunicazione Frontier recente nel canale",
                "date": now_iso[:10],
                "author": "Elite Dangerous Italia",
                "tag": "FRONTIER",
                "image": "",
                "summary": "Il canale #notizie è collegato ma non contiene ancora comunicazioni estratte.",
                "links": [],
            }
        ]

    payload = {
        "updatedAt": now_iso,
        "items": parsed,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Aggiornato {OUTPUT_FILE} con {len(parsed)} comunicazioni Frontier.")


if __name__ == "__main__":
    main()
