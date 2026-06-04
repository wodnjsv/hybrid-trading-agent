"""SQLite 페이퍼북: 진입 기록(LLM·baseline) + 정산 + 조회."""
from __future__ import annotations
import sqlite3
from pathlib import Path

_COLS = ["run_date", "market", "ticker", "source", "k_t", "catalyst_summary",
         "catalyst_timestamp", "theme", "conviction", "rationale", "websearch_snapshot",
         "entry_close", "ret_d", "close_pos", "close_strength", "trade_value", "vol20"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT, market TEXT, ticker TEXT, source TEXT, k_t INTEGER,
  catalyst_summary TEXT, catalyst_timestamp TEXT, theme TEXT, conviction REAL,
  rationale TEXT, websearch_snapshot TEXT,
  entry_close REAL, ret_d REAL, close_pos REAL, close_strength REAL, trade_value REAL, vol20 REAL,
  exit_open REAL, exit_high REAL, exit_low REAL, exit_close1 REAL, exit_close2 REAL,
  net_s0 REAL, net_s05 REAL, net_s10 REAL, settled INTEGER DEFAULT 0
);
"""


class PaperBook:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def record(self, row: dict) -> int:
        cols = ", ".join(_COLS)
        ph = ", ".join("?" for _ in _COLS)
        cur = self.conn.execute(f"INSERT INTO paper ({cols}) VALUES ({ph})",
                                [row[c] for c in _COLS])
        self.conn.commit()
        return cur.lastrowid

    def open_positions(self, run_date: str) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM paper WHERE run_date=? AND settled=0", (run_date,))
        return [dict(r) for r in cur.fetchall()]

    def settle(self, rid: int, exit_open, exit_high, exit_low, exit_close1, exit_close2, nets: dict):
        self.conn.execute(
            "UPDATE paper SET exit_open=?, exit_high=?, exit_low=?, exit_close1=?, exit_close2=?, "
            "net_s0=?, net_s05=?, net_s10=?, settled=1 WHERE id=?",
            (exit_open, exit_high, exit_low, exit_close1, exit_close2,
             nets[0.0], nets[0.0005], nets[0.001], rid))
        self.conn.commit()

    def all_settled(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM paper WHERE settled=1")
        return [dict(r) for r in cur.fetchall()]
