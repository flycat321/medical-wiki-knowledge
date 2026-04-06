"""Contribution calculator: fetches BookStack data and computes per-user stats."""

import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from bookstack_client import BookStackClient
from models import save_page_ownership, save_snapshot


def strip_html(html: str) -> str:
    """Remove HTML tags and return plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def count_chars(text: str) -> int:
    """Count meaningful characters (CJK chars + words)."""
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return len(text)


def collect_and_snapshot(client: BookStackClient | None = None) -> dict[str, Any]:
    """Main collection routine: fetch all pages, compute stats, save snapshot."""
    if client is None:
        client = BookStackClient()

    taken_at = datetime.now().isoformat()

    # Fetch all users
    users = {u["id"]: u["name"] for u in client.get_users()}

    # Fetch all pages (list only, no content)
    pages_list = client.get_pages()

    # Per-user accumulators
    stats: dict[int, dict[str, int]] = {}
    for uid in users:
        stats[uid] = {
            "total_pages": 0,
            "total_chars": 0,
            "created_pages": 0,
            "updated_pages": 0,
        }

    # Fetch each page detail for content
    for page_summary in pages_list:
        page_id = page_summary["id"]
        try:
            detail = client.get_page_detail(page_id)
        except Exception:
            continue

        html_content = detail.get("html", "")
        text = strip_html(html_content)
        char_count = count_chars(text)

        creator_id = detail.get("created_by", {}).get("id") if isinstance(detail.get("created_by"), dict) else detail.get("created_by")
        updater_id = detail.get("updated_by", {}).get("id") if isinstance(detail.get("updated_by"), dict) else detail.get("updated_by")

        if creator_id is None:
            continue

        # Save page ownership
        save_page_ownership(page_id, creator_id, char_count)

        # Attribute chars to creator
        if creator_id in stats:
            stats[creator_id]["total_chars"] += char_count
            stats[creator_id]["total_pages"] += 1
            stats[creator_id]["created_pages"] += 1

        # Track updater activity (if different from creator)
        if updater_id and updater_id != creator_id and updater_id in stats:
            stats[updater_id]["updated_pages"] += 1

    # Save snapshots
    for uid, s in stats.items():
        if s["total_pages"] > 0 or s["updated_pages"] > 0:
            save_snapshot(
                taken_at=taken_at,
                user_id=uid,
                user_name=users.get(uid, f"User#{uid}"),
                total_pages=s["total_pages"],
                total_chars=s["total_chars"],
                created_pages=s["created_pages"],
                updated_pages=s["updated_pages"],
            )

    return {
        "taken_at": taken_at,
        "users_processed": len(users),
        "pages_processed": len(pages_list),
    }
