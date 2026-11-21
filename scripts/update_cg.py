import json
import os
import re
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

INARA_CG_URL = "https://inara.cz/elite/communitygoals/"
OUTPUT_FILE = "community-goals.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_inara_community_goals(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    goals = []

    headings = soup.find_all(["h2", "h3"])
    for heading in headings:
        title = clean_text(heading.get_text(" ", strip=True))
        if not title or title.lower() in {"community goals", "news", "galaxy", "rankings", "data"}:
            continue

        container = heading.parent
        while container and container.name not in {"body", "main"}:
            block_text = container.get_text(" | ", strip=True)
            if "Location" in block_text and "Objective" in block_text and "Status" in block_text:
                break
            container = container.parent

        if not container or container.name in {"body", "main"}:
            continue

        if any(g["title"] == title for g in goals):
            continue

        raw_lines = [clean_text(line) for line in container.get_text("\n").splitlines() if clean_text(line)]

        def extract_field(label: str) -> str:
            for idx, line in enumerate(raw_lines):
                if line.lower() == label.lower() and idx + 1 < len(raw_lines):
                    return raw_lines[idx + 1]
                if line.lower().startswith(label.lower() + " "):
                    return clean_text(line[len(label):])
            return ""

        location = extract_field("Location")
        objective = extract_field("Objective")
        progress = extract_field("Progress")
        end_date = extract_field("End")
        status = extract_field("Status")

        if not status:
            continue

        if "finish" in status.lower() or "complet" in status.lower() or "expired" in status.lower():
            continue

        systems = []
        if "|" in location:
            parts = [clean_text(p) for p in location.split("|") if clean_text(p)]
            if len(parts) >= 2:
                systems = [parts[-1]]
            else:
                systems = parts
        elif location:
            systems = [location]

        rewards_parts = []
        table = container.find("table")
        if table:
            for tr in table.find_all("tr"):
                cols = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
                if len(cols) >= 3 and cols[0].lower() != "tier":
                    rewards_parts.append(f"{cols[0]}: {cols[-1]}")

        paragraphs = []
        extra_rewards = []
        for p in container.find_all(["p", "li"]):
            txt = clean_text(p.get_text(" ", strip=True))
            if not txt or txt == title:
                continue
            if txt.startswith("-") or "receive" in txt.lower() or "reward" in txt.lower() or "decal" in txt.lower() or "paint job" in txt.lower():
                extra_rewards.append(txt.lstrip("- ").strip())
            else:
                paragraphs.append(txt)

        description = " ".join(paragraphs[:3]) if paragraphs else f"Obiettivo: {objective} ({location})."
        if objective:
            description = f"Obiettivo: {objective} — Location: {location}. {description}".strip()

        combined_rewards = []
        if extra_rewards:
            combined_rewards.extend(extra_rewards[:3])
        if rewards_parts:
            combined_rewards.append("Fasce Crediti: " + " | ".join(rewards_parts))

        rewards_text = " — ".join(combined_rewards) if combined_rewards else "Crediti e ricompense in base al tier raggiunto."

        goals.append({
            "title": title,
            "status": status.upper(),
            "systems": systems if systems else ["Sconosciuto"],
            "location": location,
            "objective": objective,
            "progress": progress,
            "end": end_date,
            "description": description,
            "rewards": rewards_text,
            "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    return goals


def main():
    resp = requests.get(INARA_CG_URL, headers=HEADERS, timeout=25)
    resp.raise_for_status()

    active_goals = parse_inara_community_goals(resp.text)

    if not active_goals:
        active_goals = [
            {
                "title": "Nessun Community Goal attivo al momento",
                "status": "STANDBY",
                "systems": ["Galassia"],
                "description": "Al momento non risultano Community Goal attivi su Inara. Il sistema ricontrolla automaticamente ogni 3 ore.",
                "rewards": "In attesa della prossima iniziativa galattica.",
                "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(active_goals, f, ensure_ascii=False, indent=2)

    print(f"Salvati {len(active_goals)} record in {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
