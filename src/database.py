import json
import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import aiosqlite
from src.config import settings


def normalize_company_name(name: Optional[str]) -> str:
    """Normalize parent company string by removing ownership percentages and legal punctuation."""
    if not name:
        return ""
    # Extract before percentage parens e.g. "ASHLAND INC (100%)" -> "ASHLAND INC"
    clean = re.sub(r"\s*\(\s*\d+(\.\d+)?%\s*\)", "", name)
    # Take the primary parent if multiple are listed
    if ";" in clean:
        clean = clean.split(";")[0]
    # Remove punctuation
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", clean.lower())
    return " ".join(clean.split())


class DatabaseManager:
    """Manages SQLite database with WAL mode for carbon disclosures and facilities."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or settings.DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_sync_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facilities (
                    facility_id INTEGER PRIMARY KEY,
                    facility_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    city TEXT,
                    zip TEXT,
                    latitude REAL,
                    longitude REAL,
                    naics_code TEXT,
                    sector_name TEXT,
                    year INTEGER,
                    parent_company TEXT,
                    parent_company_norm TEXT,
                    facility_types TEXT,
                    reported_subparts TEXT,
                    estimated_emissions_mt_co2e REAL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS corporate_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    claimed_emissions REAL NOT NULL,
                    epa_emissions REAL NOT NULL,
                    discrepancy_score REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    audit_json TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_timestamp TEXT NOT NULL,
                    total_facilities INTEGER NOT NULL,
                    source_url TEXT NOT NULL
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_fac_parent_norm ON facilities(parent_company_norm);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fac_state ON facilities(state);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fac_naics ON facilities(naics_code);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fac_year ON facilities(year);")
            conn.commit()

    @asynccontextmanager
    async def get_connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
        finally:
            await conn.close()

    async def insert_facilities_batch(self, facilities: List[Dict[str, Any]], clear_existing: bool = False):
        async with self.get_connection() as conn:
            if clear_existing:
                await conn.execute("DELETE FROM facilities;")

            for f in facilities:
                p_norm = normalize_company_name(f.get("parent_company"))
                await conn.execute("""
                    INSERT OR REPLACE INTO facilities
                    (facility_id, facility_name, state, city, zip, latitude, longitude, naics_code, sector_name, year, parent_company, parent_company_norm, facility_types, reported_subparts, estimated_emissions_mt_co2e)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f["facility_id"],
                    f.get("facility_name", "UNKNOWN"),
                    f.get("state", ""),
                    f.get("city", ""),
                    f.get("zip", ""),
                    f.get("latitude"),
                    f.get("longitude"),
                    str(f.get("naics_code", "")),
                    f.get("sector_name", "Industrial"),
                    int(f.get("year", 2022)),
                    f.get("parent_company", ""),
                    p_norm,
                    f.get("facility_types", "Direct Emitter"),
                    f.get("reported_subparts", ""),
                    float(f.get("estimated_emissions_mt_co2e", 0.0))
                ))
            await conn.commit()

    async def get_total_facilities_count(self) -> int:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) as count FROM facilities;")
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def get_unique_parents_count(self) -> int:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(DISTINCT parent_company_norm) as count FROM facilities WHERE parent_company_norm != '';")
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def search_facilities(
        self,
        state: Optional[str] = None,
        parent: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM facilities WHERE 1=1"
        params = []
        if state:
            query += " AND state = ?"
            params.append(state.upper())
        if parent:
            norm_p = normalize_company_name(parent)
            query += " AND parent_company_norm LIKE ?"
            params.append(f"%{norm_p}%")
        query += " LIMIT ?"
        params.append(limit)

        async with self.get_connection() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def record_audit(self, audit: Dict[str, Any]) -> int:
        ts = datetime.now(timezone.utc).isoformat()
        audit_payload = json.dumps(audit)
        async with self.get_connection() as conn:
            cursor = await conn.execute("""
                INSERT INTO corporate_audits
                (timestamp, company_name, claimed_emissions, epa_emissions, discrepancy_score, risk_level, audit_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                audit["company_name"],
                audit["claimed_scope1_mt_co2e"],
                audit["epa_actual_scope1_mt_co2e"],
                audit["discrepancy_score"],
                audit["risk_level"],
                audit_payload
            ))
            await conn.commit()
            return cursor.lastrowid

    async def get_recent_audits(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT * FROM corporate_audits ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["details"] = json.loads(d["audit_json"])
                results.append(d)
            return results


db = DatabaseManager()
