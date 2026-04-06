"""BookStack REST API client."""

import os
from typing import Any

import requests


class BookStackClient:
    """Wrapper for BookStack REST API with token authentication."""

    def __init__(
        self,
        base_url: str | None = None,
        token_id: str | None = None,
        token_secret: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ["BOOKSTACK_URL"]).rstrip("/")
        self.token_id = token_id or os.environ["BOOKSTACK_TOKEN_ID"]
        self.token_secret = token_secret or os.environ["BOOKSTACK_TOKEN_SECRET"]
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {self.token_id}:{self.token_secret}",
            "Content-Type": "application/json",
        })

    def _get_all(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Fetch all items from a paginated endpoint."""
        items: list[dict] = []
        offset = 0
        count = 100
        while True:
            p = {"count": count, "offset": offset}
            if params:
                p.update(params)
            resp = self.session.get(f"{self.base_url}/api/{endpoint}", params=p)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("data", []))
            total = data.get("total", 0)
            offset += count
            if offset >= total:
                break
        return items

    def get_users(self) -> list[dict]:
        return self._get_all("users")

    def get_pages(self) -> list[dict]:
        return self._get_all("pages")

    def get_page_detail(self, page_id: int) -> dict:
        resp = self.session.get(f"{self.base_url}/api/pages/{page_id}")
        resp.raise_for_status()
        return resp.json()

    def get_audit_log(self, filters: dict[str, str] | None = None) -> list[dict]:
        params = {}
        if filters:
            for k, v in filters.items():
                params[f"filter[{k}]"] = v
        return self._get_all("audit-log", params)

    # --- Write operations (for migration) ---

    def create_shelf(self, name: str, description: str = "") -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/shelves",
            json={"name": name, "description": description},
        )
        resp.raise_for_status()
        return resp.json()

    def create_book(self, name: str, description: str = "") -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/books",
            json={"name": name, "description": description},
        )
        resp.raise_for_status()
        return resp.json()

    def assign_book_to_shelf(self, shelf_id: int, book_ids: list[int]) -> None:
        """Assign books to a shelf by updating the shelf."""
        current = self.session.get(f"{self.base_url}/api/shelves/{shelf_id}").json()
        existing = [b["id"] for b in current.get("books", [])]
        all_ids = existing + [bid for bid in book_ids if bid not in existing]
        resp = self.session.put(
            f"{self.base_url}/api/shelves/{shelf_id}",
            json={"books": all_ids},
        )
        resp.raise_for_status()

    def create_chapter(self, book_id: int, name: str, description: str = "") -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/chapters",
            json={"book_id": book_id, "name": name, "description": description},
        )
        resp.raise_for_status()
        return resp.json()

    def create_page_in_chapter(self, chapter_id: int, name: str, html: str) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/pages",
            json={"chapter_id": chapter_id, "name": name, "html": html},
        )
        resp.raise_for_status()
        return resp.json()

    def create_page_in_book(self, book_id: int, name: str, html: str) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/pages",
            json={"book_id": book_id, "name": name, "html": html},
        )
        resp.raise_for_status()
        return resp.json()
