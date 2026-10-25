import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    display_name TEXT,
    household_size INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_periods (
    billing_period_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    period_start_date TEXT NOT NULL,
    period_end_date TEXT NOT NULL,
    target_units REAL NOT NULL,
    previous_period_units REAL,
    actual_final_units REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS daily_consumption (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    billing_period_id TEXT NOT NULL,
    date TEXT NOT NULL,
    daily_units REAL NOT NULL,
    input_method TEXT NOT NULL,
    data_type TEXT NOT NULL,
    is_complete INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(billing_period_id, date)
);
CREATE TABLE IF NOT EXISTS appliances (
    appliance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    appliance_name TEXT NOT NULL,
    appliance_type TEXT,
    rated_power_watts REAL NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    hours_per_day REAL NOT NULL,
    days_per_week REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)


# ---------- users ----------
def create_user(user_id, email, display_name, household_size):
    with get_conn() as c:
        c.execute(
            "INSERT INTO users (user_id, email, display_name, household_size, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, email, display_name, household_size, _now()),
        )


def update_user(user_id, email, display_name, household_size):
    """Update household profile fields. Returns True if a row was updated."""
    with get_conn() as c:
        cur = c.execute(
            "UPDATE users SET email=?, display_name=?, household_size=? "
            "WHERE user_id=?",
            (email, display_name, household_size, user_id),
        )
        return cur.rowcount > 0


def delete_user(user_id):
    """Delete a household and all related data. Returns True if deleted."""
    with get_conn() as c:
        row = c.execute(
            "SELECT user_id FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            return False
        c.execute("DELETE FROM daily_consumption WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM billing_periods WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM appliances WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        return True


def list_users():
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY created_at")]


def get_user(user_id):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


# ---------- billing periods ----------
def create_billing_period(bp_id, user_id, start, end, target, previous_units=None):
    with get_conn() as c:
        c.execute(
            "INSERT INTO billing_periods "
            "(billing_period_id, user_id, period_start_date, period_end_date, "
            " target_units, previous_period_units, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bp_id, user_id, start.isoformat(), end.isoformat(), target,
             previous_units, _now()),
        )


def update_billing_target(bp_id, new_target):
    with get_conn() as c:
        c.execute("UPDATE billing_periods SET target_units=? WHERE billing_period_id=?",
                  (new_target, bp_id))


def delete_billing_period(bp_id, user_id):
    """Delete a billing period and its daily records. Returns True if deleted."""
    with get_conn() as c:
        row = c.execute(
            "SELECT user_id FROM billing_periods WHERE billing_period_id=?",
            (bp_id,),
        ).fetchone()
        if not row or row["user_id"] != user_id:
            return False
        c.execute(
            "DELETE FROM daily_consumption WHERE billing_period_id=?",
            (bp_id,),
        )
        c.execute(
            "DELETE FROM billing_periods WHERE billing_period_id=?",
            (bp_id,),
        )
        return True


def list_billing_periods(user_id):
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM billing_periods WHERE user_id=? ORDER BY period_start_date DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_billing_period(bp_id):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM billing_periods WHERE billing_period_id=?", (bp_id,)
        ).fetchone()
        return dict(row) if row else None


def previous_completed_period(user_id, before_iso_date):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM billing_periods "
            "WHERE user_id=? AND period_end_date < ? AND actual_final_units IS NOT NULL "
            "ORDER BY period_end_date DESC LIMIT 1",
            (user_id, before_iso_date),
        ).fetchone()
        return dict(row) if row else None


# ---------- daily records ----------
def upsert_daily_record(user_id, bp_id, date_iso, units, input_method, data_type, is_complete=True):
    with get_conn() as c:
        c.execute(
            "INSERT INTO daily_consumption "
            "(user_id, billing_period_id, date, daily_units, input_method, data_type, is_complete, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(billing_period_id, date) DO UPDATE SET "
            "  daily_units=excluded.daily_units, "
            "  input_method=excluded.input_method, "
            "  data_type=excluded.data_type, "
            "  is_complete=excluded.is_complete",
            (user_id, bp_id, date_iso, units, input_method, data_type,
             int(is_complete), _now()),
        )


def list_daily_records(bp_id):
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM daily_consumption WHERE billing_period_id=? ORDER BY date",
            (bp_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_daily_record(bp_id, date_iso):
    with get_conn() as c:
        c.execute(
            "DELETE FROM daily_consumption WHERE billing_period_id=? AND date=?",
            (bp_id, date_iso),
        )


# ---------- appliances ----------
def create_appliance(user_id, name, atype, watts, qty, hours, days):
    with get_conn() as c:
        c.execute(
            "INSERT INTO appliances "
            "(user_id, appliance_name, appliance_type, rated_power_watts, "
            " quantity, hours_per_day, days_per_week, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, atype, watts, qty, hours, days, _now()),
        )


def list_appliances(user_id):
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM appliances WHERE user_id=? ORDER BY appliance_id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_appliance(appliance_id):
    with get_conn() as c:
        c.execute("DELETE FROM appliances WHERE appliance_id=?", (appliance_id,))