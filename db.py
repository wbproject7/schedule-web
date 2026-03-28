"""
Database Layer (Dual Mode)
===========================
- DATABASE_URL 환경변수 있음 → PostgreSQL (Supabase 배포용)
- DATABASE_URL 없음 → SQLite (로컬 개발용)

유지비용: 0원 (Supabase 무료 티어 500MB)
"""

import os
import json
import hashlib
import secrets

DATABASE_URL = os.environ.get('DATABASE_URL', '')
IS_PG = DATABASE_URL.startswith('postgres')

if IS_PG:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedule.db'))


# ============================================================
# Connection
# ============================================================

def get_db():
    if IS_PG:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _execute(conn, sql, params=None):
    """DB 엔진에 맞게 SQL 실행"""
    if IS_PG:
        sql = sql.replace('?', '%s')
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return cur
    else:
        return conn.execute(sql, params or ())


def _fetchone(conn, sql, params=None):
    if IS_PG:
        cur = _execute(conn, sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    else:
        row = conn.execute(sql, params or ()).fetchone()
        return dict(row) if row else None


def _fetchall(conn, sql, params=None):
    if IS_PG:
        cur = _execute(conn, sql, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    else:
        rows = conn.execute(sql, params or ()).fetchall()
        return [dict(r) for r in rows]


def _insert_returning_id(conn, sql, params=None):
    """INSERT 후 ID 반환. PG는 RETURNING id, SQLite는 lastrowid."""
    if IS_PG:
        sql = sql.replace('?', '%s')
        if 'RETURNING' not in sql.upper():
            sql += ' RETURNING id'
        cur = conn.cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    else:
        cur = conn.execute(sql, params or ())
        return cur.lastrowid


# ============================================================
# Schema Init
# ============================================================

_PG_SCHEMA = '''
CREATE TABLE IF NOT EXISTS stores (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    settings TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT DEFAULT 'staff',
    do_count INTEGER,
    active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(store_id, name)
);

CREATE TABLE IF NOT EXISTS schedules (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    schedule_data TEXT NOT NULL,
    constraints_data TEXT DEFAULT '{}',
    pre_requests_data TEXT DEFAULT '{}',
    verification_data TEXT DEFAULT '[]',
    conflicts_data TEXT DEFAULT '[]',
    file_excel TEXT,
    file_csv TEXT,
    note TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    expiry DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_emp_store ON employees(store_id, active);
CREATE INDEX IF NOT EXISTS idx_sch_store ON schedules(store_id, year DESC, month DESC);
CREATE INDEX IF NOT EXISTS idx_token_expiry ON auth_tokens(expiry);
'''

_SQLITE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    settings TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT DEFAULT 'staff',
    do_count INTEGER,
    active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, name)
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    schedule_data TEXT NOT NULL,
    constraints_data TEXT DEFAULT '{}',
    pre_requests_data TEXT DEFAULT '{}',
    verification_data TEXT DEFAULT '[]',
    conflicts_data TEXT DEFAULT '[]',
    file_excel TEXT,
    file_csv TEXT,
    note TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    expiry REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_emp_store ON employees(store_id, active);
CREATE INDEX IF NOT EXISTS idx_sch_store ON schedules(store_id, year DESC, month DESC);
CREATE INDEX IF NOT EXISTS idx_token_expiry ON auth_tokens(expiry);
'''


def init_db():
    conn = get_db()
    try:
        if IS_PG:
            cur = conn.cursor()
            cur.execute(_PG_SCHEMA)
            cur.close()
        else:
            conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# Password Hashing
# ============================================================

def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password, stored_hash):
    try:
        salt, hashed = stored_hash.split(':')
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except (ValueError, AttributeError):
        return False


# ============================================================
# Store CRUD
# ============================================================

def create_store(name, code, password, settings=None):
    conn = get_db()
    try:
        new_id = _insert_returning_id(
            conn,
            'INSERT INTO stores (name, code, password_hash, settings) VALUES (?, ?, ?, ?)',
            (name, code.strip().lower(), hash_password(password), json.dumps(settings or default_settings()))
        )
        conn.commit()
        return new_id
    except Exception as e:
        conn.rollback()
        err = str(e).lower()
        if 'unique' in err or 'duplicate' in err or 'integrity' in err:
            return None
        raise
    finally:
        conn.close()


def get_store_by_code(code):
    conn = get_db()
    try:
        return _fetchone(conn, 'SELECT * FROM stores WHERE code = ?', (code.strip().lower(),))
    finally:
        conn.close()


def get_store_by_id(store_id):
    conn = get_db()
    try:
        return _fetchone(conn, 'SELECT * FROM stores WHERE id = ?', (store_id,))
    finally:
        conn.close()


def update_store_settings(store_id, settings):
    conn = get_db()
    try:
        _execute(conn, 'UPDATE stores SET settings = ? WHERE id = ?', (json.dumps(settings), store_id))
        conn.commit()
    finally:
        conn.close()


def update_store_password(store_id, new_password):
    conn = get_db()
    try:
        _execute(conn, 'UPDATE stores SET password_hash = ? WHERE id = ?', (hash_password(new_password), store_id))
        conn.commit()
    finally:
        conn.close()


def default_settings():
    return {
        'doCount': 8,
        'maxConsecutive': 5,
        'maxConsecutiveOff': 4,
        'minWeekday': 4,
        'minWeekend': 6,
        'minWeekdayOff': 2,
        'fairWeekend': True,
    }


# ============================================================
# Employee CRUD
# ============================================================

def get_employees(store_id, active_only=True):
    conn = get_db()
    try:
        if active_only:
            return _fetchall(conn,
                'SELECT * FROM employees WHERE store_id = ? AND active = 1 ORDER BY sort_order, id',
                (store_id,))
        return _fetchall(conn,
            'SELECT * FROM employees WHERE store_id = ? ORDER BY active DESC, sort_order, id',
            (store_id,))
    finally:
        conn.close()


def add_employee(store_id, name, role='staff', do_count=None):
    conn = get_db()
    try:
        new_id = _insert_returning_id(
            conn,
            'INSERT INTO employees (store_id, name, role, do_count) VALUES (?, ?, ?, ?)',
            (store_id, name.strip(), role, do_count)
        )
        conn.commit()
        return new_id
    except Exception as e:
        conn.rollback()
        err = str(e).lower()
        if 'unique' in err or 'duplicate' in err or 'integrity' in err:
            return None
        raise
    finally:
        conn.close()


def update_employee(emp_id, store_id, **kwargs):
    conn = get_db()
    try:
        allowed = {'name', 'role', 'do_count', 'active', 'sort_order'}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        if IS_PG:
            set_clause = ', '.join(f'{k} = %s' for k in updates)
            values = list(updates.values()) + [emp_id, store_id]
            cur = conn.cursor()
            cur.execute(f'UPDATE employees SET {set_clause} WHERE id = %s AND store_id = %s', values)
            cur.close()
        else:
            set_clause = ', '.join(f'{k} = ?' for k in updates)
            values = list(updates.values()) + [emp_id, store_id]
            conn.execute(f'UPDATE employees SET {set_clause} WHERE id = ? AND store_id = ?', values)
        conn.commit()
        return True
    finally:
        conn.close()


def delete_employee(emp_id, store_id):
    return update_employee(emp_id, store_id, active=0)


def reactivate_employee(emp_id, store_id):
    return update_employee(emp_id, store_id, active=1)


def bulk_add_employees(store_id, names, role='staff'):
    conn = get_db()
    added = []
    try:
        for name in names:
            name = name.strip()
            if not name:
                continue
            try:
                new_id = _insert_returning_id(
                    conn,
                    'INSERT INTO employees (store_id, name, role) VALUES (?, ?, ?)',
                    (store_id, name, role)
                )
                added.append({'id': new_id, 'name': name})
            except Exception as e:
                err = str(e).lower()
                if 'unique' in err or 'duplicate' in err or 'integrity' in err:
                    if IS_PG:
                        conn.rollback()
                    continue
                raise
        conn.commit()
        return added
    finally:
        conn.close()


# ============================================================
# Schedule CRUD
# ============================================================

def save_schedule(store_id, year, month, schedule_data, constraints_data=None,
                  pre_requests_data=None, verification_data=None, conflicts_data=None,
                  file_excel=None, file_csv=None, note=''):
    conn = get_db()
    try:
        new_id = _insert_returning_id(
            conn,
            '''INSERT INTO schedules
               (store_id, year, month, schedule_data, constraints_data, pre_requests_data,
                verification_data, conflicts_data, file_excel, file_csv, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (store_id, year, month,
             json.dumps(schedule_data), json.dumps(constraints_data or {}),
             json.dumps(pre_requests_data or {}), json.dumps(verification_data or []),
             json.dumps(conflicts_data or []),
             file_excel, file_csv, note)
        )
        conn.commit()
        return new_id
    finally:
        conn.close()


def get_schedules(store_id, limit=20, offset=0):
    conn = get_db()
    try:
        return _fetchall(conn,
            '''SELECT id, year, month, note, created_at
               FROM schedules WHERE store_id = ?
               ORDER BY year DESC, month DESC, created_at DESC
               LIMIT ? OFFSET ?''',
            (store_id, limit, offset))
    finally:
        conn.close()


def get_schedule_by_id(schedule_id, store_id):
    conn = get_db()
    try:
        d = _fetchone(conn,
            'SELECT * FROM schedules WHERE id = ? AND store_id = ?',
            (schedule_id, store_id))
        if d:
            d['schedule_data'] = json.loads(d['schedule_data']) if isinstance(d['schedule_data'], str) else d['schedule_data']
            d['constraints_data'] = json.loads(d['constraints_data']) if isinstance(d.get('constraints_data'), str) and d['constraints_data'] else {}
            d['pre_requests_data'] = json.loads(d['pre_requests_data']) if isinstance(d.get('pre_requests_data'), str) and d['pre_requests_data'] else {}
            d['verification_data'] = json.loads(d['verification_data']) if isinstance(d.get('verification_data'), str) and d['verification_data'] else []
            d['conflicts_data'] = json.loads(d['conflicts_data']) if isinstance(d.get('conflicts_data'), str) and d['conflicts_data'] else []
            # created_at을 문자열로 변환 (PG는 datetime 객체)
            if d.get('created_at') and not isinstance(d['created_at'], str):
                d['created_at'] = str(d['created_at'])
            return d
        return None
    finally:
        conn.close()


def delete_schedule(schedule_id, store_id):
    conn = get_db()
    try:
        _execute(conn, 'DELETE FROM schedules WHERE id = ? AND store_id = ?', (schedule_id, store_id))
        conn.commit()
    finally:
        conn.close()


def get_schedule_count(store_id):
    conn = get_db()
    try:
        row = _fetchone(conn, 'SELECT COUNT(*) as cnt FROM schedules WHERE store_id = ?', (store_id,))
        return row['cnt'] if row else 0
    finally:
        conn.close()


def get_last_schedule(store_id, year, month):
    conn = get_db()
    try:
        row = _fetchone(conn,
            '''SELECT schedule_data FROM schedules
               WHERE store_id = ? AND year = ? AND month = ?
               ORDER BY created_at DESC LIMIT 1''',
            (store_id, year, month))
        if row:
            data = row['schedule_data']
            return json.loads(data) if isinstance(data, str) else data
        return None
    finally:
        conn.close()


# ============================================================
# Auth Token CRUD (DB-backed)
# ============================================================

def save_token(token, store_id, expiry):
    conn = get_db()
    try:
        _execute(conn, 'INSERT INTO auth_tokens (token, store_id, expiry) VALUES (?, ?, ?)',
                 (token, store_id, expiry))
        conn.commit()
    finally:
        conn.close()


def get_token(token):
    conn = get_db()
    try:
        return _fetchone(conn, 'SELECT * FROM auth_tokens WHERE token = ?', (token,))
    finally:
        conn.close()


def delete_token(token):
    conn = get_db()
    try:
        _execute(conn, 'DELETE FROM auth_tokens WHERE token = ?', (token,))
        conn.commit()
    finally:
        conn.close()


def cleanup_expired_tokens():
    import time
    conn = get_db()
    try:
        _execute(conn, 'DELETE FROM auth_tokens WHERE expiry < ?', (time.time(),))
        conn.commit()
    finally:
        conn.close()
