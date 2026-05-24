"""
Session stats tracker — SQLite-backed log of every delegation event.
Records agent used, tokens, score. Reports savings vs. always-Claude baseline.
"""
import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "session_stats.db"

# Rough Claude API token cost anchor (used only for display, not billing)
CLAUDE_TOKENS_PER_DELEGATION = 4000  # baseline if task had gone to Claude


def _conn() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS delegations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            ts          REAL    NOT NULL,
            task_id     TEXT    NOT NULL,
            task_type   TEXT    NOT NULL,
            agent       TEXT    NOT NULL,
            est_tokens  INTEGER NOT NULL,
            score       INTEGER
        )
    """)
    db.commit()
    return db


def log_delegation(
    session_id: str,
    task_id: str,
    task_type: str,
    agent: str,
    estimated_tokens: int,
    score: int | None = None,
) -> None:
    db = _conn()
    db.execute(
        "INSERT INTO delegations (session_id, ts, task_id, task_type, agent, est_tokens, score) "
        "VALUES (?,?,?,?,?,?,?)",
        (session_id, time.time(), task_id, task_type, agent, estimated_tokens, score),
    )
    db.commit()
    db.close()


def update_score(task_id: str, score: int) -> None:
    db = _conn()
    db.execute("UPDATE delegations SET score=? WHERE task_id=?", (score, task_id))
    db.commit()
    db.close()


def _fetch_rows(db: sqlite3.Connection, where: str = "", params: tuple = ()) -> list[dict]:
    sql = f"SELECT session_id, ts, task_id, task_type, agent, est_tokens, score FROM delegations {where} ORDER BY ts ASC"
    cur = db.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _summarise(rows: list[dict]) -> dict:
    total = len(rows)
    gemma_rows = [r for r in rows if r["agent"] == "gemma4"]
    claude_rows = [r for r in rows if r["agent"] == "claude_agent"]

    gemma_tokens = sum(r["est_tokens"] for r in gemma_rows)
    scored = [r for r in gemma_rows if r["score"] is not None]
    avg_score = round(sum(r["score"] for r in scored) / len(scored), 1) if scored else None

    # Tokens "saved" = what those tasks would have consumed via Claude
    tokens_saved = sum(r["est_tokens"] for r in gemma_rows)

    return {
        "total_delegations": total,
        "gemma4_delegations": len(gemma_rows),
        "claude_delegations": len(claude_rows),
        "gemma4_tokens_handled": gemma_tokens,
        "tokens_saved_from_claude": tokens_saved,
        "gemma4_avg_score": avg_score,
    }


def session_report(session_id: str) -> dict:
    db = _conn()
    rows = _fetch_rows(db, "WHERE session_id=?", (session_id,))
    db.close()
    return {"session_id": session_id, **_summarise(rows)}


def all_sessions_report() -> dict:
    db = _conn()
    rows = _fetch_rows(db)
    db.close()
    if not rows:
        return {"sessions": [], "totals": _summarise([])}

    by_session: dict[str, list] = {}
    for r in rows:
        by_session.setdefault(r["session_id"], []).append(r)

    sessions = []
    for sid, srows in by_session.items():
        s = _summarise(srows)
        s["session_id"] = sid
        s["first_ts"] = srows[0]["ts"]
        s["last_ts"] = srows[-1]["ts"]
        sessions.append(s)

    sessions.sort(key=lambda s: s["first_ts"], reverse=True)
    totals = _summarise(rows)
    return {"sessions": sessions, "totals": totals}


def _fmt_ts(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def print_report(report: dict | None = None) -> None:
    if report is None:
        report = all_sessions_report()

    totals = report["totals"]
    sessions = report.get("sessions", [])

    print("\n══════════════════════════════════════════════")
    print("  Conductor Session Stats")
    print("══════════════════════════════════════════════")

    if not sessions:
        print("  No delegations recorded yet.")
        return

    print(f"\n  {'SESSION':<24} {'DATE':<17} {'TOTAL':>5} {'GEMMA4':>6} {'TOKENS→LOCAL':>12} {'AVG SCORE':>9}")
    print(f"  {'-'*24} {'-'*17} {'-'*5} {'-'*6} {'-'*12} {'-'*9}")
    for s in sessions:
        score_str = f"{s['gemma4_avg_score']:.0f}/100" if s["gemma4_avg_score"] is not None else "n/a"
        print(
            f"  {s['session_id'][:24]:<24} "
            f"{_fmt_ts(s['first_ts']):<17} "
            f"{s['total_delegations']:>5} "
            f"{s['gemma4_delegations']:>6} "
            f"{s['gemma4_tokens_handled']:>12,} "
            f"{score_str:>9}"
        )

    print(f"\n  {'TOTALS':<24} {'':17} "
          f"{totals['total_delegations']:>5} "
          f"{totals['gemma4_delegations']:>6} "
          f"{totals['tokens_saved_from_claude']:>12,}")

    pct = 0
    if totals["total_delegations"]:
        pct = round(100 * totals["gemma4_delegations"] / totals["total_delegations"])

    print(f"\n  Tokens routed to gemma4 (local):  {totals['gemma4_tokens_handled']:,}")
    print(f"  Tokens saved from Claude API:     {totals['tokens_saved_from_claude']:,}")
    print(f"  Local offload rate:               {pct}%")
    if totals["gemma4_avg_score"] is not None:
        print(f"  gemma4 avg accuracy:              {totals['gemma4_avg_score']:.0f}/100")
    print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--session":
        r = session_report(sys.argv[2])
        print_report({"sessions": [r], "totals": r})
    else:
        print_report()
