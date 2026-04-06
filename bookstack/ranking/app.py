"""Flask app with APScheduler for BookStack contribution ranking."""

import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request

from bookstack_client import BookStackClient
from calculator import collect_and_snapshot
from models import (
    get_ranking, get_user_detail, init_db,
    create_submission, get_submissions, get_submission,
    update_submission_status, get_user_submissions_stats,
)

app = Flask(__name__)

# Admin password for export/detail views
ADMIN_PASS = os.environ.get("RANKING_ADMIN_PASS", "admin2026")


def scheduled_collect() -> None:
    """Scheduled task to collect contribution data."""
    try:
        result = collect_and_snapshot()
        print(f"[{datetime.now()}] Collection done: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Collection error: {e}")


@app.route("/")
def index():
    period = request.args.get("period", "all")
    if period not in ("week", "month", "year", "all"):
        period = "all"
    ranking = get_ranking(period)
    return render_template("ranking.html", ranking=ranking, period=period)


@app.route("/api/ranking")
def api_ranking():
    period = request.args.get("period", "all")
    ranking = get_ranking(period)
    return jsonify(ranking)


@app.route("/api/collect", methods=["POST"])
def api_collect():
    """Manually trigger a collection."""
    result = collect_and_snapshot()
    return jsonify(result)


@app.route("/api/user/<int:user_id>")
def api_user_detail(user_id: int):
    detail = get_user_detail(user_id)
    return jsonify(detail)


@app.route("/export")
def export_excel():
    """Export ranking data as Excel."""
    from io import BytesIO

    from openpyxl import Workbook

    period = request.args.get("period", "all")
    ranking = get_ranking(period)

    wb = Workbook()
    ws = wb.active
    ws.title = "贡献排名"

    period_labels = {"week": "本周", "month": "本月", "year": "本年", "all": "总计"}
    ws.append(["排名", "姓名", f"{period_labels.get(period, '总计')}字数", "页面数", "累计总字数", "累计总页面"])

    for r in ranking:
        ws.append([
            r["rank"],
            r["user_name"],
            r["period_chars"],
            r["period_pages"],
            r["total_chars"],
            r["total_pages"],
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    from flask import send_file
    filename = f"贡献排名_{period}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================================
# 提交修改（普通用户）
# ============================================================

@app.route("/submit", methods=["GET"])
def submit_page():
    """Show submission form. Pre-fill page info if page_id provided."""
    page_id = request.args.get("page_id")
    page_name = request.args.get("page_name", "")
    book_name = request.args.get("book_name", "")
    # Fetch page list for dropdown
    try:
        client = BookStackClient()
        pages = client.get_pages()
        books = {p.get("book_id"): p.get("book_slug", "") for p in pages}
    except Exception:
        pages = []
    return render_template("submit.html", pages=pages, page_id=page_id,
                           page_name=page_name, book_name=book_name)


@app.route("/submit", methods=["POST"])
def submit_post():
    """Handle submission from user."""
    user_name = request.form.get("user_name", "").strip()
    user_email = request.form.get("user_email", "").strip()
    target_page_id = request.form.get("target_page_id")
    target_page_name = request.form.get("target_page_name", "").strip()
    target_book_name = request.form.get("target_book_name", "").strip()
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    if not user_name or not content or not title:
        return render_template("submit_result.html", success=False, message="姓名、标题和内容不能为空")

    target_pid = int(target_page_id) if target_page_id and target_page_id.isdigit() else None

    sub_id = create_submission(
        user_name=user_name, user_email=user_email or f"{user_name}@wiki.local",
        target_page_id=target_pid, target_page_name=target_page_name,
        target_book_name=target_book_name, title=title, content=content,
    )
    return render_template("submit_result.html", success=True,
                           message=f"提交成功！编号 #{sub_id}，等待管理员审核。")


@app.route("/my-submissions")
def my_submissions():
    """Show submissions for a specific user."""
    email = request.args.get("email", "")
    if not email:
        return render_template("my_submissions.html", submissions=[], email="")
    subs = [s for s in get_submissions() if s["user_email"] == email]
    return render_template("my_submissions.html", submissions=subs, email=email)


# ============================================================
# 审核面板（管理员）
# ============================================================

@app.route("/admin/review")
def admin_review():
    """Admin review dashboard."""
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASS:
        return "需要密码：/admin/review?pwd=admin2026", 403
    status_filter = request.args.get("status", "pending")
    subs = get_submissions(status_filter if status_filter != "all" else None)
    stats = get_user_submissions_stats()
    return render_template("admin_review.html", submissions=subs, stats=stats,
                           status_filter=status_filter, pwd=pwd)


@app.route("/admin/review/<int:sub_id>")
def admin_review_detail(sub_id: int):
    """View a single submission detail."""
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASS:
        return "需要密码", 403
    sub = get_submission(sub_id)
    if not sub:
        return "提交不存在", 404

    # If it targets an existing page, fetch current content for comparison
    current_content = ""
    if sub["target_page_id"]:
        try:
            client = BookStackClient()
            page = client.get_page_detail(sub["target_page_id"])
            current_content = page.get("html", "")
        except Exception:
            pass

    return render_template("admin_review_detail.html", sub=sub,
                           current_content=current_content, pwd=pwd)


@app.route("/admin/approve/<int:sub_id>", methods=["POST"])
def admin_approve(sub_id: int):
    """Approve a submission and publish to BookStack."""
    pwd = request.form.get("pwd", "")
    if pwd != ADMIN_PASS:
        return "需要密码", 403

    sub = get_submission(sub_id)
    if not sub or sub["status"] != "pending":
        return "无效的提交", 400

    comment = request.form.get("comment", "")

    # Publish to BookStack
    try:
        client = BookStackClient()
        if sub["target_page_id"]:
            # Update existing page: append content
            resp = client.session.put(
                f"{client.base_url}/api/pages/{sub['target_page_id']}",
                json={"html": sub["content"]},
            )
            resp.raise_for_status()
        else:
            # Create new page in the first book
            books_resp = client.session.get(f"{client.base_url}/api/books", params={"count": 1})
            books_resp.raise_for_status()
            first_book = books_resp.json()["data"][0]["id"]
            client.create_page_in_book(first_book, sub["title"], sub["content"])
    except Exception as e:
        update_submission_status(sub_id, "approved", f"已批准但发布失败: {e}", "admin")
        return f"批准成功但发布到BookStack失败: {e}", 500

    update_submission_status(sub_id, "approved", comment, "admin")
    return f'<script>alert("已批准并发布！");location.href="/admin/review?pwd={pwd}";</script>'


@app.route("/admin/reject/<int:sub_id>", methods=["POST"])
def admin_reject(sub_id: int):
    """Reject a submission."""
    pwd = request.form.get("pwd", "")
    if pwd != ADMIN_PASS:
        return "需要密码", 403
    comment = request.form.get("comment", "")
    update_submission_status(sub_id, "rejected", comment, "admin")
    return f'<script>alert("已驳回");location.href="/admin/review?pwd={pwd}";</script>'


# ============================================================
# 贡献排行榜（基于审核通过的提交）
# ============================================================

@app.route("/leaderboard")
def leaderboard():
    """Leaderboard based on approved submissions."""
    stats = get_user_submissions_stats()
    return render_template("leaderboard.html", stats=stats)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    init_db()

    # Schedule collection every 6 hours
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_collect, "interval", hours=6, next_run_time=None)
    scheduler.start()

    print(f"[{datetime.now()}] Ranking service started on port 5000")
    app.run(host="0.0.0.0", port=5000)
