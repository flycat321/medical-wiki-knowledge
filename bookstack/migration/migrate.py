"""Migrate data from epc-knowledge-base SQLite to BookStack.

Usage:
    python migrate.py --db /path/to/knowledge.db \
        --url http://192.168.1.69:6875 \
        --token-id YOUR_TOKEN_ID \
        --token-secret YOUR_TOKEN_SECRET
"""

import argparse
import sqlite3
import sys
import os

# Add ranking dir to path for client reuse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ranking"))
from bookstack_client import BookStackClient


# Mapping: top-level category IDs -> which BookStack Shelf they belong to
SHELF_MAP = {
    "EPC设计管理流程": [1, 2, 3, 4, 7, 8, 9],  # category IDs
    "各专业设计要点": [5],
    "专项设计": [6],
    "错题本总库": [10],
    "模板文件库": [11],
}


def get_categories(db_path: str) -> tuple[list[dict], list[dict]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    top = conn.execute(
        "SELECT * FROM categories WHERE parent_id IS NULL ORDER BY sort_order"
    ).fetchall()
    subs = conn.execute(
        "SELECT * FROM categories WHERE parent_id IS NOT NULL ORDER BY parent_id, sort_order"
    ).fetchall()
    conn.close()
    return [dict(r) for r in top], [dict(r) for r in subs]


def get_articles(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM articles ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def migrate(db_path: str, client: BookStackClient) -> None:
    top_cats, sub_cats = get_categories(db_path)
    articles = get_articles(db_path)

    print(f"Found {len(top_cats)} top categories, {len(sub_cats)} sub categories, {len(articles)} articles")

    # Create Shelves
    shelf_ids: dict[str, int] = {}
    for shelf_name in SHELF_MAP:
        print(f"Creating shelf: {shelf_name}")
        shelf = client.create_shelf(shelf_name, f"医疗设计部知识库 - {shelf_name}")
        shelf_ids[shelf_name] = shelf["id"]

    # Also create extra shelves
    for extra in ["规范与标准解读", "项目案例库"]:
        print(f"Creating shelf: {extra}")
        shelf = client.create_shelf(extra, f"医疗设计部知识库 - {extra}")
        shelf_ids[extra] = shelf["id"]

    # Build cat_id -> shelf_name mapping
    cat_to_shelf: dict[int, str] = {}
    for shelf_name, cat_ids in SHELF_MAP.items():
        for cid in cat_ids:
            cat_to_shelf[cid] = shelf_name

    # Create Books (from top-level categories) and assign to shelves
    book_ids: dict[int, int] = {}  # category_id -> book_id
    for cat in top_cats:
        # Strip number prefix for cleaner name
        name = cat["title"]
        if ". " in name:
            name = name.split(". ", 1)[1]

        print(f"Creating book: {name}")
        book = client.create_book(name, "")
        book_ids[cat["id"]] = book["id"]

        # Assign to shelf
        shelf_name = cat_to_shelf.get(cat["id"])
        if shelf_name and shelf_name in shelf_ids:
            client.assign_book_to_shelf(shelf_ids[shelf_name], [book["id"]])

    # Create Chapters (from sub-categories)
    chapter_ids: dict[int, int] = {}  # sub_category_id -> chapter_id
    for sub in sub_cats:
        parent_book = book_ids.get(sub["parent_id"])
        if not parent_book:
            print(f"  Warning: no book for sub-category {sub['title']} (parent_id={sub['parent_id']})")
            continue

        name = sub["title"]
        if ". " in name:
            name = name.split(". ", 1)[1]

        print(f"  Creating chapter: {name}")
        chapter = client.create_chapter(parent_book, name)
        chapter_ids[sub["id"]] = chapter["id"]

    # Migrate articles as pages
    for article in articles:
        cat_id = article.get("category_id")
        html = article.get("body", "")
        title = article.get("title", "Untitled")

        if not html.strip():
            html = "<p>(empty)</p>"

        if cat_id in chapter_ids:
            print(f"  Creating page in chapter: {title}")
            client.create_page_in_chapter(chapter_ids[cat_id], title, html)
        elif cat_id in book_ids:
            print(f"  Creating page in book: {title}")
            client.create_page_in_book(book_ids[cat_id], title, html)
        else:
            # Fallback: create in first book
            first_book = list(book_ids.values())[0] if book_ids else None
            if first_book:
                print(f"  Creating page (fallback): {title}")
                client.create_page_in_book(first_book, title, html)

    print(f"\nMigration complete!")
    print(f"  Shelves: {len(shelf_ids)}")
    print(f"  Books: {len(book_ids)}")
    print(f"  Chapters: {len(chapter_ids)}")
    print(f"  Articles: {len(articles)}")


def main():
    parser = argparse.ArgumentParser(description="Migrate epc-knowledge-base to BookStack")
    parser.add_argument("--db", required=True, help="Path to knowledge.db")
    parser.add_argument("--url", required=True, help="BookStack URL (e.g. http://192.168.1.69:6875)")
    parser.add_argument("--token-id", required=True, help="BookStack API token ID")
    parser.add_argument("--token-secret", required=True, help="BookStack API token secret")
    args = parser.parse_args()

    client = BookStackClient(
        base_url=args.url,
        token_id=args.token_id,
        token_secret=args.token_secret,
    )
    migrate(args.db, client)


if __name__ == "__main__":
    main()
