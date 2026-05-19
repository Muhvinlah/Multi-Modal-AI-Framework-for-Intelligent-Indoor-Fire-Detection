# ==============================================================================
# Tujuan       : Capture user feedback (thumbs up/down + alasan) untuk improve bot
#                Storage: SQLite untuk simplicity, bisa migrate ke Postgres nanti
# Caller       : main.py (router include), frontend dashboard
# Main Functions: POST /api/feedback, GET /api/feedback/stats
# ==============================================================================

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

DB_PATH = os.getenv("FEEDBACK_DB_PATH", "data/feedback.db")


def init_db():
    """Bikin tabel kalau belum ada."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                bot_reply TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                reason TEXT,
                intent TEXT,
                context_used TEXT,
                created_at TEXT NOT NULL,
                user_id TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)")
        conn.commit()
    print(f"[Feedback] DB initialized: {DB_PATH}")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# === Pydantic models ===
class FeedbackIn(BaseModel):
    message_id: str = Field(..., min_length=1, max_length=64)
    user_message: str = Field(..., max_length=2000)
    bot_reply: str = Field(..., max_length=5000)
    rating: int = Field(..., ge=-1, le=1)   # -1 = thumbs down, 1 = thumbs up
    reason: Optional[str] = Field(None, max_length=500)
    intent: Optional[str] = Field(None, max_length=64)
    context_used: Optional[str] = Field(None, max_length=2000)
    user_id: Optional[str] = Field(None, max_length=64)


class FeedbackStatsOut(BaseModel):
    total_count: int
    positive_count: int
    negative_count: int
    positive_rate: float
    recent_negatives: List[Dict]
    by_intent: Dict[str, Dict]


@router.post("/api/feedback")
async def submit_feedback(fb: FeedbackIn):
    """Submit feedback untuk 1 message."""
    if fb.rating == 0:
        raise HTTPException(400, "Rating harus -1 atau 1")

    with get_db() as conn:
        conn.execute("""
            INSERT INTO feedback
            (message_id, user_message, bot_reply, rating, reason, intent, context_used, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fb.message_id,
            fb.user_message,
            fb.bot_reply,
            fb.rating,
            fb.reason,
            fb.intent,
            fb.context_used,
            datetime.now().isoformat(),
            fb.user_id,
        ))
        conn.commit()

    return {"ok": True, "message": "Thanks for feedback!"}


@router.get("/api/feedback/stats")
async def get_stats() -> FeedbackStatsOut:
    """Aggregate stats untuk monitoring dashboard."""
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM feedback").fetchone()["c"]
        positive = conn.execute("SELECT COUNT(*) as c FROM feedback WHERE rating = 1").fetchone()["c"]
        negative = total - positive

        recent_neg = conn.execute("""
            SELECT message_id, user_message, bot_reply, reason, intent, created_at
            FROM feedback WHERE rating = -1
            ORDER BY created_at DESC LIMIT 10
        """).fetchall()

        by_intent_rows = conn.execute("""
            SELECT intent,
                   COUNT(*) as total,
                   SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as positive
            FROM feedback
            WHERE intent IS NOT NULL
            GROUP BY intent
        """).fetchall()

        by_intent = {
            row["intent"]: {
                "total": row["total"],
                "positive": row["positive"],
                "rate": round(row["positive"] / row["total"], 3) if row["total"] else 0,
            }
            for row in by_intent_rows
        }

    return FeedbackStatsOut(
        total_count=total,
        positive_count=positive,
        negative_count=negative,
        positive_rate=round(positive / total, 3) if total else 0.0,
        recent_negatives=[dict(r) for r in recent_neg],
        by_intent=by_intent,
    )


@router.get("/api/feedback/export")
async def export_for_training():
    """Export feedback dalam format untuk training data prep."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT user_message, bot_reply, rating, reason, intent, context_used
            FROM feedback
            ORDER BY created_at DESC
        """).fetchall()
    return {
        "count": len(rows),
        "data": [dict(r) for r in rows],
    }
