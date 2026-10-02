import os
import sqlite3
from datetime import datetime, timedelta

import uuid
import json

import platform


import time
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_cors import CORS
import requests
import hashlib
import hmac
import secrets

FOOTBALL_API_KEY = "e1c859a9b58f4b64ae66a0ec14f07b07"  # Get from https://www.football-data.org/
FOOTBALL_API_BASE = "https://api.football-data.org/v4"


APP_VERSION = "8.4.3"

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("KAERU_SECRET", "kaeru-dev-secret-2026")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=1),
)
CORS(app)
DEVICE_COOKIE = "kaeru_device"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "kaeru.db")
PASSWORD_FILE = os.path.join(BASE_DIR, "password.txt")





# Team IDs for Football-Data.org
TEAM_IDS = {
    "Real Madrid": 86,
    "Barcelona": 81,
    "Brazil": 764,
    "Argentina": 760
}

# Competition IDs
COMPETITION_IDS = {
    "UCL": 2001,  # UEFA Champions League
    "LaLiga": 2014,  # LaLiga
    "World Cup": 2000,  # FIFA World Cup
    "Friendlies": 2003  # International Friendlies
}

# Team short names for display
TEAM_SHORT_NAMES = {
    "Real Madrid": "RMA",
    "Barcelona": "BAR",
    "Brazil": "BRA",
    "Argentina": "ARG"
}

def get_existing_match_hash(title, due_date):
    """Generate a unique hash for a match to check for duplicates"""
    match_string = f"{title}_{due_date}"
    return hashlib.md5(match_string.encode()).hexdigest()

def is_match_already_exists(title, due_date):
    """Check if a match already exists in tasks to avoid duplicates"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM tasks WHERE title = ? AND due_date = ?",
            (title, due_date)
        ).fetchone()
        
        # Also check for similar matches within 1 day
        if not row:
            due_date_obj = datetime.strptime(due_date, '%Y-%m-%d').date()
            start_date = due_date_obj - timedelta(days=1)
            end_date = due_date_obj + timedelta(days=1)
            
            teams_match = re.search(r'([A-Z]+) vs ([A-Z]+)', title)
            if teams_match:
                team1, team2 = teams_match.groups()
                rows = conn.execute(
                    """SELECT id FROM tasks 
                       WHERE title LIKE ? 
                       AND due_date BETWEEN ? AND ?""",
                    (f'%{team1} vs {team2}%', start_date.isoformat(), end_date.isoformat())
                ).fetchall()
                return len(rows) > 0
        
        return row is not None

def convert_to_bst_plus6(utc_time_str):
    """Convert UTC time to BST+6 (Bangladesh Time)"""
    try:
        utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        local_time = utc_time + timedelta(hours=6)
        return local_time.strftime("%I:%M %p").lstrip('0').lower()
    except:
        return "Time TBD"


def fetch_matches_from_api(competition_id, team_names, days_ahead=7):
    """Fetch matches from Football-Data.org API for specific teams"""
    matches = []
    
    # ---------------------------------------------------------------------
    # REAL-TIME FIX: 
    # Grab the actual current date from your system clock
    # ---------------------------------------------------------------------
    today = datetime.now().date() 
    end_date = today + timedelta(days=days_ahead)
    
    headers = {'X-Auth-Token': FOOTBALL_API_KEY.strip()}
    
    url = f"{FOOTBALL_API_BASE}/competitions/{competition_id}/matches"
    
    params = {
        'dateFrom': today.isoformat(),
        'dateTo': end_date.isoformat()
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            target_team_ids = {TEAM_IDS[name]: name for name in team_names if name in TEAM_IDS}
            
            for match in data.get('matches', []):
                # ---------------------------------------------------------
                # UNCOMMENTED FIX: 
                # Turn this back on so it hides games that are already over
                # ---------------------------------------------------------
                if match.get('status') in ['FINISHED', 'AWARDED', 'CANCELLED']:
                    continue

                home_team_data = match.get('homeTeam', {})
                away_team_data = match.get('awayTeam', {})
                
                home_id = home_team_data.get('id')
                away_id = away_team_data.get('id')
                
                if home_id in target_team_ids or away_id in target_team_ids:
                    home_team = target_team_ids.get(home_id, home_team_data.get('shortName', home_team_data.get('name', '')))
                    away_team = target_team_ids.get(away_id, away_team_data.get('shortName', away_team_data.get('name', '')))
                    
                    # --- 1. THE TIMEZONE FIX ---
                    # First, get the exact UTC time
                    utc_dt = datetime.fromisoformat(match['utcDate'].replace('Z', '+00:00'))
                    
                    # Next, add 6 hours for Bangladesh Time BEFORE extracting the date
                    bst_dt = utc_dt + timedelta(hours=6)
                    
                    # Now extract both from the fully converted Bangladesh timestamp
                    match_date = bst_dt.date() # This will correctly roll over to April 8!
                    match_time = bst_dt.strftime('%I:%M %p').lstrip('0').lower() # "1:00 am"
                    
                    # --- 2. THE LALIGA FIX ---
                    competition_name = match.get('competition', {}).get('name', '')
                    
                    # The API uses "Primera Division", so we added it to the check!
                    comp_short = "UCL" if "Champions League" in competition_name else \
                                "LaLiga" if "Primera Division" in competition_name or "LaLiga" in competition_name else \
                                "World Cup" if "World Cup" in competition_name else \
                                "Friendly" if "Friendly" in competition_name else "Match"
                    
                    matches.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'date': match_date,
                        'time': match_time,
                        'competition': comp_short,
                        'competition_full': competition_name,
                        'status': match.get('status', 'TIMED')
                    })
        else:
            print(f"API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error fetching matches: {str(e)}")
    
    return matches

def get_relevant_matches():
    """Fetch all relevant matches for configured teams and competitions"""
    all_matches = []
    
    competitions_config = [
        {"comp_id": COMPETITION_IDS["UCL"], "teams": ["Real Madrid", "Barcelona"], "name": "UCL"},
        {"comp_id": COMPETITION_IDS["LaLiga"], "teams": ["Real Madrid", "Barcelona"], "name": "LaLiga"},
        {"comp_id": COMPETITION_IDS["World Cup"], "teams": ["Brazil", "Argentina"], "name": "World Cup"},
        {"comp_id": COMPETITION_IDS["Friendlies"], "teams": ["Brazil", "Argentina"], "name": "Friendlies"}
    ]
    
    for config in competitions_config:
        matches = fetch_matches_from_api(config["comp_id"], config["teams"], days_ahead=7)
        
        # ---------------------------------------------------------------------
        # THE FIX FOR 429 ERRORS:
        # Pause for 2 seconds after each API call to respect the 10 req/min limit
        # ---------------------------------------------------------------------
        time.sleep(2) 
        
        for match in matches:
            home_short = TEAM_SHORT_NAMES.get(match['home_team'], str(match['home_team'])[:3].upper())
            away_short = TEAM_SHORT_NAMES.get(match['away_team'], str(match['away_team'])[:3].upper())
            
            title = f"{match['competition']}: {home_short} vs {away_short} - {match['time']}"
            due_date = match['due_date'] if 'due_date' in match else match['date'].isoformat()
            
            all_matches.append({
                'title': title,
                'due_date': due_date,
                'home_team': match['home_team'],
                'away_team': match['away_team'],
                'competition': match['competition'],
                'raw_date': match['date']
            })
    
    # Remove duplicates
    unique_matches = {}
    for match in all_matches:
        key = f"{match['home_team']}_{match['away_team']}_{match['due_date']}"
        if key not in unique_matches:
            unique_matches[key] = match
    
    return list(unique_matches.values())


def add_matches_to_tasks():
    """Fetch matches and add them to tasks if not already present"""
    matches = get_relevant_matches()
    added_count = 0
    skipped_count = 0
    date_range = ""
    
    if matches:
        dates = [m['raw_date'] for m in matches]
        date_range = f"{min(dates).strftime('%b %d')} - {max(dates).strftime('%b %d, %Y')}"
    
    for match in matches:
        if not is_match_already_exists(match['title'], match['due_date']):
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO tasks (title, due_date, completed) VALUES (?, ?, 0)",
                    (match['title'], match['due_date'])
                )
                conn.commit()
                added_count += 1
                print(f"Added match: {match['title']} on {match['due_date']}")
        else:
            skipped_count += 1
    
    return added_count, skipped_count, date_range

@app.route('/api/sports/sync', methods=['POST'])
def sync_sports_matches():
    """Endpoint to manually trigger sports match sync"""
    try:
        added, skipped, date_range = add_matches_to_tasks()
        
        if added > 0:
            message = f"Added {added} new matches for {date_range}"
            if skipped > 0:
                message += f" (skipped {skipped} duplicates)"
        else:
            message = f"No new matches found for {date_range}"
        
        return jsonify({
            "success": True,
            "added": added,
            "skipped": skipped,
            "date_range": date_range,
            "message": message
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sports/matches', methods=['GET'])
def get_upcoming_matches():
    """Get upcoming matches without adding to tasks"""
    matches = get_relevant_matches()
    
    formatted_matches = []
    for match in matches:
        formatted_matches.append({
            'title': match['title'],
            'date': match['due_date'],
            'competition': match['competition'],
            'home_team': match['home_team'],
            'away_team': match['away_team']
        })
    
    return jsonify({
        'count': len(formatted_matches),
        'matches': formatted_matches
    })





def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        # Tasks
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                due_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Projects
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                added_date TEXT,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                position INTEGER DEFAULT 0
            )
        ''')

        cursor = conn.execute("PRAGMA table_info(projects);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'last_updated' not in columns:
            conn.execute('ALTER TABLE projects ADD COLUMN last_updated TEXT DEFAULT CURRENT_TIMESTAMP')

        # Subtasks
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')

        # Notes
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'Untitled Note',
                content TEXT DEFAULT '',
                pinned INTEGER DEFAULT 0,
                position INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor = conn.execute("PRAGMA table_info(notes);")
        note_cols = [row[1] for row in cursor.fetchall()]
        if 'pinned' not in note_cols:
            conn.execute('ALTER TABLE notes ADD COLUMN pinned INTEGER DEFAULT 0')
        if 'position' not in note_cols:
            conn.execute('ALTER TABLE notes ADD COLUMN position INTEGER DEFAULT 0')

        # Timeless nodes
        conn.execute('''
            CREATE TABLE IF NOT EXISTS timeless_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                gregorian_year INTEGER,
                hijri_year INTEGER,
                tags TEXT DEFAULT '',
                sidenote TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Add tags column if missing
        cursor = conn.execute("PRAGMA table_info(timeless_nodes);")
        tl_cols = [row[1] for row in cursor.fetchall()]
        if 'tags' not in tl_cols:
            conn.execute('ALTER TABLE timeless_nodes ADD COLUMN tags TEXT DEFAULT ""')

        # Timeless node sources
        conn.execute('''
            CREATE TABLE IF NOT EXISTS timeless_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL,
                display_text TEXT NOT NULL,
                url TEXT NOT NULL,
                FOREIGN KEY(node_id) REFERENCES timeless_nodes(id) ON DELETE CASCADE
            )
        ''')


        conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                click_count INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                pinned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor = conn.execute("PRAGMA table_info(links);")
        link_cols = [row[1] for row in cursor.fetchall()]
        if 'sort_order' not in link_cols:
            conn.execute('ALTER TABLE links ADD COLUMN sort_order INTEGER DEFAULT 0')
        if 'pinned' not in link_cols:
            conn.execute('ALTER TABLE links ADD COLUMN pinned INTEGER DEFAULT 0')


        # Add this inside init_db() function, after creating the tasks table

        # Add recurring task columns to tasks table (migration)
        cursor = conn.execute("PRAGMA table_info(tasks);")
        tasks_columns = [row[1] for row in cursor.fetchall()]

        if 'recurring' not in tasks_columns:
            conn.execute('ALTER TABLE tasks ADD COLUMN recurring INTEGER DEFAULT 0')
        if 'recurring_freq' not in tasks_columns:
            conn.execute('ALTER TABLE tasks ADD COLUMN recurring_freq TEXT DEFAULT "weekly"')
        if 'recurring_end' not in tasks_columns:
            conn.execute('ALTER TABLE tasks ADD COLUMN recurring_end TEXT')
        if 'recurring_paused' not in tasks_columns:
            conn.execute('ALTER TABLE tasks ADD COLUMN recurring_paused INTEGER DEFAULT 0')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS session_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                device_name TEXT,
                os_name TEXT,
                browser_name TEXT,
                ip_address TEXT,
                login_time TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                logout_time TEXT,
                status TEXT DEFAULT 'active'   -- active | logged_out
            )
        ''')

        # v7.4.3 : session_logs is now ONE row per device (session_id == device id)
        sl_cols = [row[1] for row in conn.execute("PRAGMA table_info(session_logs)").fetchall()]
        if 'token' not in sl_cols:
            conn.execute("DELETE FROM session_logs")      # old per-login rows are obsolete
            conn.execute("ALTER TABLE session_logs ADD COLUMN token TEXT")
            conn.execute("ALTER TABLE session_logs ADD COLUMN login_count INTEGER DEFAULT 1")

        # v7.4.3 : per-date completion of recurring occurrences
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recurring_done (
                task_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (task_id, date)
            )
        ''')
        # recurring tasks used one shared 'completed' flag -> move it to the per-date table
        conn.execute('''
            INSERT OR IGNORE INTO recurring_done (task_id, date)
            SELECT id, due_date FROM tasks
            WHERE recurring = 1 AND completed = 1 AND due_date IS NOT NULL
        ''')
        conn.execute("UPDATE tasks SET completed = 0 WHERE recurring = 1 AND completed = 1")


        # ==================== SEEDING LOGIC ====================
        # Only seed default tasks when the database file is newly created
        # (i.e. user deleted kaeru.db completely)
        db_existed_before = os.path.exists(DB_FILE)
        
        if not db_existed_before:
            if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
                utc_now = datetime.utcnow()
                dhaka_now = utc_now + timedelta(hours=6)
                today = dhaka_now.strftime("%Y-%m-%d")
                tomorrow = (dhaka_now + timedelta(days=1)).strftime("%Y-%m-%d")
                conn.executemany(
                    "INSERT INTO tasks (title, completed, due_date) VALUES (?, ?, ?)",
                    [
                        ("Code Force Contest 17", 0, today),
                        ("Leet Code Biweekly 233", 0, today),
                        ("Academic Assignment 455", 1, today),
                        ("SE exam 1st chapter and 2nd chapter", 0, tomorrow),
                        ("System Design Online Class", 0, tomorrow),
                    ]
                )

        conn.commit()


def get_password():
    if not os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'w') as f:
            f.write("kaeru2026")
    with open(PASSWORD_FILE, 'r') as f:
        return f.read().strip()


@app.context_processor
def inject_version():
    return {"version": APP_VERSION}


def _login_page(html):
    return html.replace('__VERSION__', APP_VERSION)


PUBLIC_PATHS = {'/login', '/manifest.webmanifest', '/sw.js', '/icon.svg', '/icon-maskable.svg', '/favicon.ico'}
_LOGIN_FAILS = {}   # ip -> [count, locked_until]


def _lock_seconds(ip):
    rec = _LOGIN_FAILS.get(ip)
    if rec and rec[1] > time.time():
        return int(rec[1] - time.time()) + 1
    return 0


def _record_fail(ip):
    rec = _LOGIN_FAILS.setdefault(ip, [0, 0])
    rec[0] += 1
    if rec[0] >= 5:
        rec[0] = 0
        rec[1] = time.time() + 60


def is_session_valid():
    """A request is authenticated only if its per-login token still matches the device row."""
    if not session.get('authenticated'):
        return False
    device_id = session.get('device_id')
    sid = session.get('sid')
    if not device_id or not sid:
        return False
    with get_db() as conn:
        row = conn.execute(
            "SELECT token, status, last_active FROM session_logs WHERE session_id = ?", (device_id,)
        ).fetchone()
        if not row or row['status'] != 'active' or not row['token']:
            return False
        if not hmac.compare_digest(str(row['token']), str(sid)):
            return False
        # throttle "last_active" writes to once a minute
        now = int(time.time())
        if now - int(session.get('la', 0)) > 60:
            conn.execute("UPDATE session_logs SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?", (device_id,))
            conn.commit()
            session['la'] = now
    return True


@app.before_request
def check_auth():
    if request.path.startswith('/static') or request.path in PUBLIC_PATHS:
        return
    if not is_session_valid():
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({"error": "Not authenticated"}), 401
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        wait = _lock_seconds(ip)
        if wait:
            return f"<h1 style='text-align:center;margin-top:100px;color:#ef4444'>Too many attempts. Try again in {wait}s</h1>", 429
        key = request.form.get('key') or ''
        remember = request.form.get('remember') == '1'
        if hmac.compare_digest(key.encode(), get_password().encode()):
            _LOGIN_FAILS.pop(ip, None)
            # Same device (cookie) => reuse the SAME row, no new session per login
            device_id = request.cookies.get(DEVICE_COOKIE) or str(uuid.uuid4())
            token = secrets.token_hex(24)
            register_login(device_id, token)
            session.clear()
            session['authenticated'] = True
            session['device_id'] = device_id
            session['sid'] = token
            session['la'] = int(time.time())
            session.permanent = remember
            resp = redirect(url_for('tasks'))
            resp.set_cookie(DEVICE_COOKIE, device_id, max_age=365 * 24 * 3600,
                            httponly=True, samesite='Lax')
            return resp
        _record_fail(ip)
        return "<h1 style='text-align:center;margin-top:100px;color:#ef4444'>Invalid access key</h1>", 401

    return _login_page('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kaeru — Access</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/?size=100&id=ySZcrXaaOavG&format=png&color=000000">
    <link rel="manifest" href="/manifest.webmanifest">
    <meta name="theme-color" content="#09090b">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <link rel="apple-touch-icon" href="https://img.icons8.com/?size=180&id=ySZcrXaaOavG&format=png&color=000000">
    <script>try{if(sessionStorage.getItem("kaeru_splash_login"))document.documentElement.classList.add("no-splash");else sessionStorage.setItem("kaeru_splash_login","1");}catch(e){}</script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Sora', sans-serif; }
        .glow { box-shadow: 0 0 20px rgba(16,185,129,0.25); }
        
        /* ===== v7.4.2 : DARK COLOR GLARE BACKGROUND ===== */
        .bg-glare { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; background: #09090b; }
        .bg-glare::before, .bg-glare::after {
            content: ''; position: absolute; width: 70vmax; height: 70vmax;
            border-radius: 50%; filter: blur(90px); opacity: .55;
        }
        .bg-glare::before {
            top: -25vmax; left: -20vmax;
            animation: glareA 12s infinite, glareMoveA 18s ease-in-out infinite alternate;
        }
        .bg-glare::after {
            bottom: -30vmax; right: -20vmax;
            animation: glareB 12s infinite, glareMoveB 22s ease-in-out infinite alternate;
        }
        @keyframes glareA {
            0%, 30%   { background: #064e3b; }
            35%, 65%  { background: #134e4a; }
            70%, 95%  { background: #365314; }
            100%      { background: #064e3b; }
        }
        @keyframes glareB {
            0%, 30%   { background: #164e63; }
            35%, 65%  { background: #14532d; }
            70%, 95%  { background: #134e4a; }
            100%      { background: #164e63; }
        }
        @keyframes glareMoveA { from { transform: translate(0,0) scale(1); } to { transform: translate(12vmax,8vmax) scale(1.15); } }
        @keyframes glareMoveB { from { transform: translate(0,0) scale(1); } to { transform: translate(-10vmax,-9vmax) scale(1.1); } }

        .pulse-border { animation: borderGlow 12s infinite; }
        @keyframes borderGlow {
            0%, 30%  { border-color: rgba(16,185,129,.45); box-shadow: 0 0 28px rgba(6,78,59,.45); }
            35%, 65% { border-color: rgba(20,184,166,.45); box-shadow: 0 0 28px rgba(19,78,74,.45); }
            70%, 95% { border-color: rgba(132,204,22,.35); box-shadow: 0 0 28px rgba(54,83,20,.45); }
            100%     { border-color: rgba(16,185,129,.45); box-shadow: 0 0 28px rgba(6,78,59,.45); }
        }

        .pulse-dot { animation: pulse-dot 2s ease-in-out infinite; }
        @keyframes pulse-dot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.2); }
        }

        /* Centered Password Dots & Anti-Save */
        .no-save-input {
            -webkit-text-security: disc;
            text-security: disc;
            text-align: center;
        }

        /* Shimmering Button Effect */
        .btn-shimmer {
            position: relative;
            overflow: hidden;
        }
        .btn-shimmer::after {
            content: '';
            position: absolute;
            top: -50%; left: -50%;
            width: 200%; height: 200%;
            background: linear-gradient(45deg, transparent, rgba(255,255,255,0.2), transparent);
            transform: rotate(45deg);
            animation: shimmer 3s infinite;
        }
        @keyframes shimmer {
            0% { transform: translateX(-100%) rotate(45deg); }
            100% { transform: translateX(100%) rotate(45deg); }
        }

        /* ONE-WAY Animation: Always In Left -> Out Right */
        @keyframes letterInLeft {
            0% { transform: translateX(-20px) scale(0.8); opacity: 0; filter: blur(4px); }
            100% { transform: translateX(0) scale(1); opacity: 1; filter: blur(0); }
        }
        @keyframes letterOutRight {
            0% { transform: translateX(0) scale(1); opacity: 1; filter: blur(0); }
            100% { transform: translateX(20px) scale(0.8); opacity: 0; filter: blur(4px); }
        }
        
        .text-container { position: relative; height: 42px; overflow: hidden; display: inline-block; }
        .switching-text { position: absolute; top: 0; left: 0; width: 100%; }
        .letter { display: inline-block; white-space: pre; }
        
        /* ===== v7.4.2 : NEW BADGE ANIMATION (shine sweep + float + ping) ===== */
        .badge-squash {
            position: relative; overflow: hidden;
            background: #064e3b !important;
            box-shadow: 1.5px 1.5px 0 0 #000;
            animation: badgeFloat 3.2s ease-in-out infinite;
        }
        .badge-squash::after {
            content: ''; position: absolute; top: 0; left: -60%;
            width: 40%; height: 100%;
            background: linear-gradient(100deg, transparent, rgba(255,255,255,.35), transparent);
            transform: skewX(-20deg);
            animation: badgeSweep 3.2s ease-in-out infinite;
        }
        .dot-status { background-color: #10b981; animation: dotPing 1.6s ease-out infinite; }
        @keyframes badgeFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-2px); } }
        @keyframes badgeSweep { 0%,55% { left: -60%; } 100% { left: 130%; } }
        @keyframes dotPing {
            0%   { box-shadow: 0 0 0 0 rgba(16,185,129,.7); }
            100% { box-shadow: 0 0 0 6px rgba(16,185,129,0); }
        }

        .repo-link {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 4px 12px;
            transition: all 0.3s ease;
            font-size: 12px;
        }

        .error-shake { animation: shake 0.5s ease-in-out; }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }

        #error-message {
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            max-height: 0;
            opacity: 0;
            transform: translateY(-10px);
            overflow: hidden;
        }
        #error-message.visible {
            max-height: 150px;
            opacity: 1;
            transform: translateY(0);
            margin-top: 1rem;
        }

        /* ===== v8.4.3 : LOGIN PET / MASCOT / SPLASH ===== */
        .kpet {
            --pc: #10b981; --pg: rgba(16,185,129,.4); --pe: #052e22; --es: 1;
            position: relative; width: var(--sz, 20px); height: var(--sz, 20px); border-radius: 50% 50% 46% 46%;
            background: var(--pc); box-shadow: 0 0 calc(var(--sz, 20px) * .35) var(--pg);
            transform-origin: 50% 100%; animation: kBreathe 3.8s ease-in-out infinite;
            transition: background-color .3s ease, box-shadow .3s ease; flex-shrink: 0;
        }
        .kpet .e { position: absolute; top: 31%; width: 14%; height: 20%; border-radius: 50%; background: var(--pe);
            translate: var(--lx, 0px) var(--ly, 0px); scale: var(--es);
            transition: scale .22s cubic-bezier(.3,1.7,.5,1), translate .12s linear; animation: kBlink 5s infinite; }
        .kpet .e.l { left: 27%; } .kpet .e.r { right: 27%; }
        .kpet .mo { position: absolute; left: 34%; top: 63%; width: 32%; height: 13%; border-bottom: 1.5px solid var(--pe);
            border-radius: 0 0 99px 99px; transition: all .25s ease; }
        .kpet:hover, .kpet.big { --es: 1.9; }
        .kpet:hover .mo, .kpet.big .mo { width: 42%; left: 29%; height: 18%; }
        .kpet.sad { --pc: #ef4444; --pg: rgba(239,68,68,.45); --pe: #3b0a0a; --es: 1.9; animation: kShake .5s ease-in-out 2; }
        .kpet.sad .mo { border-bottom: 0; border-top: 1.5px solid var(--pe); border-radius: 99px 99px 0 0; top: 70%; }
        .kpet.happy { --es: 1.9; animation: kHop .6s cubic-bezier(.3,.7,.4,1) 2; }
        .kpet.happy .mo { width: 46%; left: 27%; height: 22%; }
        .kpet.peek .e { --ly: 2px; }
        .kpet.wink .e.r { animation: kWink 1s ease-in-out; }
        .kpet.hop { animation: kHop .6s cubic-bezier(.3,.7,.4,1); }
        .kpet.dizzy { animation: kSpin 1.1s linear 2; }
        .kpet.dizzy .mo { border: 0; border-top: 1.5px solid var(--pe); border-radius: 0; height: 0; top: 70%; }
        @keyframes kBreathe { 0%,100% { transform: scale(1,1); } 50% { transform: scale(1.06,.94); } }
        @keyframes kBlink { 0%,92%,100% { transform: scaleY(1); } 95% { transform: scaleY(.1); } }
        @keyframes kWink { 0%,100% { transform: scaleY(1); } 30%,70% { transform: scaleY(.1); } }
        @keyframes kHop { 0% { transform: scale(1.1,.85); } 35% { transform: translateY(-9px) scale(.92,1.1); } 65% { transform: translateY(0) scale(1.12,.86); } 100% { transform: scale(1); } }
        @keyframes kShake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-3px); } 75% { transform: translateX(3px); } }
        @keyframes kSpin { to { transform: rotate(360deg); } }

        /* logo stage: pet <-> torii gate, driven by JS (synced with the word) */
        .mbox { position: relative; width: 88px; height: 88px; margin: 0 auto 16px; border-radius: 26px;
            background: linear-gradient(145deg, rgba(16,185,129,.13), rgba(20,184,166,.04));
            border: 1px solid rgba(16,185,129,.26); box-shadow: 0 12px 40px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.05);
            animation: mFloat 7s ease-in-out infinite; }
        @keyframes mFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
        .mascot { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: filter 1.2s ease; border-radius: 26px; }
        .mascot.torii { filter: hue-rotate(-95deg); }
        .mascot.poke { animation: mPoke .6s ease; }
        .m-petw { position: absolute; transition: transform .7s cubic-bezier(.5,0,.2,1), opacity .5s ease; }
        .mascot.torii .m-petw { transform: scale(.1,1.3); opacity: 0; }
        .m-torii { position: absolute; width: 62px; height: 62px; overflow: visible; opacity: 0; transform: scale(.4) rotate(-8deg);
            transition: transform .8s cubic-bezier(.3,1.5,.5,1) .1s, opacity .5s ease .1s; }
        .mascot.torii .m-torii { opacity: 1; transform: none; animation: mGlow 3.2s ease-in-out 1.4s infinite; }
        .m-torii .tp { fill: url(#tgrad); fill-opacity: 0; stroke: #a7f3d0; stroke-width: 1; stroke-dasharray: 1; stroke-dashoffset: 1;
            transition: stroke-dashoffset 1s ease, fill-opacity .7s ease 1s; }
        .mascot.torii .m-torii .tp { stroke-dashoffset: 0; fill-opacity: 1; }
        .m-torii .tp:nth-of-type(1) { transition-delay: .1s, 1s; }
        .m-torii .tp:nth-of-type(2) { transition-delay: .3s, 1.1s; }
        .m-torii .tp:nth-of-type(3) { transition-delay: .4s, 1.15s; }
        .m-torii .tp:nth-of-type(4) { transition-delay: .5s, 1.2s; }
        .m-torii .tp:nth-of-type(5) { transition-delay: .6s, 1.25s; }
        .m-torii .tp:nth-of-type(6) { transition-delay: .75s, 1.3s; }
        .m-torii .tp:nth-of-type(7) { transition-delay: .75s, 1.3s; }
        @keyframes mGlow { 0%,100% { filter: drop-shadow(0 0 3px rgba(52,211,153,.35)); } 50% { filter: drop-shadow(0 0 10px rgba(52,211,153,.75)); } }
        .mascot::before, .mascot::after { content: ''; position: absolute; inset: 14px; border-radius: 50%;
            border: 2px solid #34d399; opacity: 0; pointer-events: none; }
        .mascot.burst::before { animation: mBurst .9s ease-out; }
        .mascot.burst::after { animation: mBurst .9s ease-out .15s; }
        @keyframes mBurst { 0% { transform: scale(.4); opacity: .8; } 100% { transform: scale(2.1); opacity: 0; } }
        @keyframes mPoke { 0% { transform: scale(1); } 25% { transform: scale(.88,1.1); } 55% { transform: scale(1.1,.9) rotate(4deg); } 100% { transform: scale(1); } }
        .kfx { position: absolute; left: 50%; top: 0; font-size: 12px; line-height: 1; pointer-events: none; z-index: 5; color: #6ee7b7;
            animation: kFx 1s ease-out forwards; }
        @keyframes kFx { 0% { opacity: 0; transform: translate(-50%, 6px) scale(.5); } 20% { opacity: 1; }
            100% { opacity: 0; transform: translate(calc(-50% + var(--dx, 0px)), -34px) scale(1.15); } }

        /* thought bubble: starts in the pet's mind (dots) and stays open for the whole mascot session */
        .thought { position: absolute; left: 50%; bottom: calc(100% + 16px); width: max-content; max-width: min(236px, 78vw);
            padding: 7px 13px; border-radius: 16px; font-size: 10px; line-height: 1.45; color: #d4d4d8; text-align: center;
            background: rgba(24,24,27,.92); border: 1px solid rgba(255,255,255,.1); box-shadow: 0 8px 26px rgba(0,0,0,.5);
            opacity: 0; transform: translate(-50%, 8px) scale(.9); transform-origin: 50% 100%;
            transition: opacity .35s ease, transform .4s cubic-bezier(.3,1.4,.5,1); pointer-events: none; z-index: 6; }
        .thought.on { opacity: 1; transform: translate(-50%, 0); }
        .thought .t-text { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; min-height: 14px; }
        .thought .tv { background: linear-gradient(90deg,#34d399,#38bdf8,#fbbf24); -webkit-background-clip: text; background-clip: text;
            color: transparent; font-weight: 800; }
        .thought .caret { display: inline-block; width: 1px; height: 10px; background: #6ee7b7; margin-left: 1px; vertical-align: -1px;
            animation: kCaret .8s steps(1) infinite; }
        @keyframes kCaret { 50% { opacity: 0; } }
        .t-dots { position: absolute; left: 50%; top: 0; width: 0; height: 0; pointer-events: none; z-index: 6; }
        .t-dots i { position: absolute; border-radius: 50%; background: rgba(24,24,27,.95); border: 1px solid rgba(255,255,255,.12);
            opacity: 0; transform: scale(.3); transition: opacity .3s ease, transform .3s ease; }
        .t-dots i:nth-child(1) { width: 4px; height: 4px; left: -2px; top: 22px; }
        .t-dots i:nth-child(2) { width: 6px; height: 6px; left: -3px; top: 8px; transition-delay: .08s; }
        .t-dots i:nth-child(3) { width: 8px; height: 8px; left: -4px; top: -9px; transition-delay: .16s; }
        .mbox.thinking .t-dots i { opacity: 1; transform: none; }
        /* pet reactions */
        .kpet.wow { --es: 2.5; }
        .kpet.wow .mo { width: 22%; left: 39%; height: 22%; border: 1.5px solid var(--pe); border-radius: 50%; }
        .kpet.spin { animation: kSpin .8s cubic-bezier(.4,0,.2,1); --es: 1.8; }
        .kpet.bounce { animation: kBounce 1.2s ease-in-out; --es: 1.6; }
        @keyframes kBounce { 0%,100% { transform: translateY(0); } 15% { transform: translateY(-9px) scale(.94,1.08); } 30% { transform: translateY(0) scale(1.1,.9); }
            50% { transform: translateY(-5px); } 65% { transform: translateY(0) scale(1.06,.94); } 80% { transform: translateY(-2px); } }
        .mascot.gold .kpet { --pc: #fbbf24; --pg: rgba(251,191,36,.5); }

        /* version reveal */
        .ver-wrap { display: inline-flex; align-items: baseline; max-width: 0; overflow: hidden; opacity: 0; white-space: nowrap;
            transition: max-width .9s cubic-bezier(.2,.8,.2,1), opacity .5s ease; }
        .ver-wrap.on { max-width: 140px; opacity: 1; }
        .ver-num { margin-left: 1px; background: linear-gradient(90deg, #34d399, #38bdf8, #fbbf24, #34d399); background-size: 250% 100%;
            -webkit-background-clip: text; background-clip: text; color: transparent; font-weight: 900;
            animation: verFlow 3s linear infinite; }
        @keyframes verFlow { to { background-position: -250% 0; } }
        #mini-pet { cursor: pointer; }

        /* splash (very first screen) */
        #lsplash { position: fixed; inset: 0; z-index: 9999; background: #09090b; display: flex; flex-direction: column;
            align-items: center; justify-content: center; gap: 18px; animation: lsOut .5s ease 1.9s forwards; }
        html.no-splash #lsplash { display: none; }
        @keyframes lsOut { to { opacity: 0; visibility: hidden; } }
        #lsplash .sp-pet { animation: kBreathe 1.6s ease-in-out infinite; --es: 1.6; }
        #lsplash .sp-name { font-size: 26px; font-weight: 700; color: #f0f0f5; letter-spacing: .5px; }
        #lsplash .sp-name span { color: #10b981; margin-left: 8px; }
        #lsplash .sp-bar { width: 120px; height: 2px; border-radius: 2px; overflow: hidden; background: rgba(255,255,255,.06); }
        #lsplash .sp-bar i { display: block; height: 100%; width: 40%; background: linear-gradient(90deg,#10b981,#3b82f6); animation: lsBar 1.1s ease-in-out infinite; }
        @keyframes lsBar { 0% { transform: translateX(-100%); } 100% { transform: translateX(300%); } }
        #lsplash .sp-foot { position: absolute; bottom: 34px; text-align: center; font-size: 11px; color: #6b6b80; line-height: 1.8; }
        #lsplash .sp-foot b { color: #a8a8bc; font-weight: 600; }

        /* ===== modern, dim & professional login look ===== */
        body { background: #07070a; }
        .bg-glare { background: #07070a; }
        .bg-glare::before, .bg-glare::after { opacity: .24; filter: blur(120px); }
        .bg-grid { position: fixed; inset: 0; z-index: 0; pointer-events: none;
            background-image: radial-gradient(rgba(255,255,255,.07) 1px, transparent 1px); background-size: 30px 30px;
            -webkit-mask-image: radial-gradient(ellipse 60% 55% at 50% 45%, #000 20%, transparent 75%);
            mask-image: radial-gradient(ellipse 60% 55% at 50% 45%, #000 20%, transparent 75%); }
        .bg-vignette { position: fixed; inset: 0; z-index: 0; pointer-events: none;
            background: radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,.6) 100%); }
        body .login-card { background: linear-gradient(180deg, rgba(24,24,28,.72), rgba(14,14,17,.8)) !important;
            -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
            border: 1px solid rgba(255,255,255,.07) !important; animation: none !important;
            box-shadow: 0 24px 70px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.04) !important; position: relative; overflow: hidden; }
        body .login-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; pointer-events: none;
            background: linear-gradient(90deg, transparent, rgba(52,211,153,.55), rgba(56,189,248,.45), transparent);
            background-size: 220% 100%; animation: cardLine 9s linear infinite; }
        @keyframes cardLine { from { background-position: 220% 0; } to { background-position: -220% 0; } }
        body #access-key { background: rgba(9,9,11,.7); border-color: rgba(255,255,255,.09); transition: border-color .2s, box-shadow .2s; }
        body #access-key:focus { border-color: rgba(52,211,153,.55); box-shadow: 0 0 0 3px rgba(16,185,129,.12); }
        body #login-form button[type=submit] { background: linear-gradient(135deg, #059669, #0d9488); box-shadow: 0 6px 22px rgba(5,150,105,.22); }
        body #login-form button[type=submit]:hover { filter: brightness(1.12); }
        .owner-line { text-align: center; font-size: 12px; letter-spacing: .3px; color: #a1a1aa; margin-top: 18px; }
        .owner-line b { color: #e4e4e7; font-weight: 600; }
        .owner-line .star { background: linear-gradient(90deg,#34d399,#fbbf24); -webkit-background-clip: text; background-clip: text; color: transparent; margin: 0 2px; }
        .switching-text { text-align: center; }
    </style>
</head>
<body class="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
    <div id="lsplash" aria-hidden="true">
        <div class="kpet sp-pet" style="--sz:74px"><i class="e l"></i><i class="e r"></i><i class="mo"></i></div>
        <div class="sp-name">Kaeru<span>代える</span></div>
        <div class="sp-bar"><i></i></div>
        <div class="sp-foot"><b>Developer | Maintenance : Irshad Hossain</b><br>Personal Use Only</div>
    </div>
    <div class="bg-glare"></div>
    <div class="bg-grid"></div>
    <div class="bg-vignette"></div>
    <div class="w-full max-w-sm z-10">
        <div class="absolute top-4 right-4">
            <a href="https://github.com/Irshad-11/Kaeru" target="_blank" class="repo-link inline-flex items-center gap-2 text-zinc-400 hover:text-emerald-400 transition-all">
                <i class="fa-brands fa-github text-sm"></i>
                <span class="text-xs">Kaeru</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-xs"></i>
            </a>
        </div>
        
        <div class="text-center mb-8">
            <div class="mbox" id="mbox">
                <div id="mascot" class="mascot" title="Hi! Poke me">
                    <div class="m-petw"><div class="kpet m-pet" style="--sz:40px"><i class="e l"></i><i class="e r"></i><i class="mo"></i></div></div>
                    <svg class="m-torii" viewBox="0 0 64 64" stroke-linejoin="round">
                        <defs><linearGradient id="tgrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6ee7b7"/><stop offset="1" stop-color="#0d9488"/></linearGradient></defs>
                        <path class="tp" pathLength="1" d="M2 14 Q32 5 62 14 L60.5 19 Q32 11.5 3.5 19 Z"/>
                        <path class="tp" pathLength="1" d="M10 26 H54 V30.5 H10 Z"/>
                        <path class="tp" pathLength="1" d="M29.5 18 H34.5 V26 H29.5 Z"/>
                        <path class="tp" pathLength="1" d="M15 19 H21 V56 H15 Z"/>
                        <path class="tp" pathLength="1" d="M43 19 H49 V56 H43 Z"/>
                        <path class="tp" pathLength="1" d="M12.5 54.5 H23.5 V59 H12.5 Z"/>
                        <path class="tp" pathLength="1" d="M40.5 54.5 H51.5 V59 H40.5 Z"/>
                    </svg>
                </div>
                <div id="thought" class="thought" aria-hidden="true"><span class="t-text"></span></div>
                <div class="t-dots"><i></i><i></i><i></i></div>
            </div>
            <div class="text-container" style="width:100%;height:44px">
                <div id="english-text" class="switching-text">
                    <h1 class="text-3xl font-bold text-emerald-400 tracking-tight whitespace-nowrap" id="english-letters"></h1>
                </div>
                <div id="japanese-text" class="switching-text" style="display: none;">
                    <h1 class="text-3xl font-bold text-emerald-400 tracking-tight whitespace-nowrap" id="japanese-letters"></h1>
                </div>
            </div>
        </div>
        
        
<div class="login-card bg-zinc-900 border border-zinc-800 rounded-2xl p-6 pulse-border">
            <form method="post" class="space-y-4" id="login-form" autocomplete="off">
                <div>
                    <label class="text-xs font-medium text-zinc-400 uppercase tracking-wider">Access Key</label>
                    <input type="text" name="key" id="access-key" autofocus
                           placeholder="Access Protected"
                           autocomplete="off"
                           spellcheck="false"
                           class="no-save-input mt-2 w-full px-4 py-3 bg-zinc-950 border border-zinc-700 focus:border-emerald-500 rounded-xl outline-none text-white text-sm placeholder:text-zinc-600 transition-colors">
                </div>
                <div class="flex items-center gap-3 group cursor-pointer">
  <div class="relative flex items-center justify-center">
    <input 
      type="checkbox" 
      id="save-login" 
      class="
        peer appearance-none w-5 h-5 
        border-2 border-zinc-700 rounded-md bg-zinc-900
        checked:bg-emerald-600 checked:border-emerald-500
        hover:border-zinc-500 focus:outline-none focus:ring-2 
        focus:ring-emerald-500/20 focus:ring-offset-2 focus:ring-offset-black
        transition-all duration-200 ease-in-out cursor-pointer
      "
    >
    <svg 
      class="absolute w-3 h-3 text-white opacity-0 peer-checked:opacity-100 transition-opacity duration-200 pointer-events-none" 
      xmlns="http://www.w3.org/2000/svg" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      stroke-width="4" 
      stroke-linecap="round" 
      stroke-linejoin="round"
    >
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
  </div>
  
  <label 
    for="save-login" 
    class="text-sm font-medium text-zinc-400 group-hover:text-zinc-200 transition-colors cursor-pointer select-none"
  >
    Remember me <span class="text-zinc-600 text-xs font-normal">(1 day)</span>
  </label>
</div>
                <button type="submit"
                        class="w-full bg-emerald-600 hover:bg-emerald-400 text-zinc-950 font-semibold py-3 rounded-xl transition-all active:scale-95 glow group btn-shimmer">
                    <span>Get in</span>
                    <i class="fa-solid fa-arrow-right ml-2 group-hover:translate-x-1 transition-transform"></i>
                </button>
            </form>
            
            <div id="error-message">
                <div class="bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-center">
                    <p class="text-red-400 text-xs mb-1">
                        <i class="fa-solid fa-lock mr-1"></i>
                        This site is for personal use only.
                    </p>
                    <p class="text-red-400/80 text-xs">
                        Owner: Irshad Hossain | 
                        <a href="https://github.com/Irshad-11/Kaeru" target="_blank" class="underline hover:text-red-300">
                            Visit Repo for your own Kaeru
                        </a>
                    </p>
                </div>
            </div>
        </div>
        
        <div class="text-center mt-6 flex justify-center gap-5 text-zinc-600">
            <a href="https://github.com/Irshad-11" target="_blank" class="hover:text-emerald-400 transition-colors">
                <i class="fa-brands fa-github text-xl"></i>
            </a>
            <a href="https://www.linkedin.com/in/irshad-hossain-785548323/" target="_blank" class="hover:text-emerald-400 transition-colors">
                <i class="fa-brands fa-linkedin text-xl"></i>
            </a>
            <a href="https://www.facebook.com/irshad.risad" target="_blank" class="hover:text-emerald-400 transition-colors">
                <i class="fa-brands fa-facebook text-xl"></i>
            </a>
        </div>
        <p class="owner-line"><b>Irshad Hossain</b> <span class="star">★</span> Personal Use Only</p>
        <div class="flex justify-center mt-3">
            <span class="badge-squash font-mono inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border-2 border-zinc-950 bg-zinc-900 text-[10px] font-black italic tracking-tight">
                <div class="kpet" id="mini-pet" style="--sz:14px" title="Poke me"><i class="e l"></i><i class="e r"></i><i class="mo"></i></div>
                <span class="text-white/90 ver-wrap" id="ver-wrap"><span id="ver-pre" class="ver-pre">latest - v</span><span id="ver-num" class="ver-num"></span></span>
            </span>
        </div>

    </div>
    
    <script>
    // Animation Configuration (Your original beautiful animation - unchanged)
    const englishWord = 'Kaeru';
    const japaneseWord = '代える';
    const STAGGER = 60;
    const DURATION = 500;
    const WAIT_TIME = 4000;

    // v7.4.3 : "Remember me" is handled on the server (1 day session).
    // Old versions stored the key in localStorage - remove it.
    try { localStorage.removeItem('kaeru_key'); } catch (e) {}

    // ====================== LOGIN HANDLING (Merged) ======================
    const loginForm = document.getElementById('login-form');
    const errorDiv = document.getElementById('error-message');
    const accessInput = document.getElementById('access-key');

    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const key = document.getElementById('access-key').value.trim();
        const saveChecked = document.getElementById('save-login').checked;

        if (!key) return;

        const submitBtn = this.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;
        const formBox = document.querySelector('.bg-zinc-900');

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Verifying...';
        errorDiv.classList.remove('visible');

        try {
            await new Promise(r => setTimeout(r, 600));
            
            const formData = new FormData(this);
            formData.set('remember', saveChecked ? '1' : '0');
            const response = await fetch(window.location.href, { 
                method: 'POST', 
                body: formData 
            });
            accessInput.value = '';
            if (response.ok) {
                kMood('happy', 1200);
                await new Promise(r => setTimeout(r, 650));
                window.location.href = '/tasks';
            } else {
                errorDiv.classList.add('visible');
                kMood('sad', 1500);
                formBox.classList.add('error-shake');
                accessInput.value = '';
                accessInput.focus();
                setTimeout(() => formBox.classList.remove('error-shake'), 500);
                setTimeout(() => errorDiv.classList.remove('visible'), 5000);
            }
        } catch (error) {
            console.error(error);
            errorDiv.classList.add('visible');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        }
    });

    // ====================== ANIMATION (Your original) ======================
    function prepareLetters(text, containerId) {
        const container = document.getElementById(containerId);
        container.innerHTML = '';
        return text.split('').map(char => {
            const span = document.createElement('span');
            span.className = 'letter';
            span.textContent = char;
            span.style.opacity = '0';
            container.appendChild(span);
            return span;
        });
    }

    async function animateWord(letters, animName) {
        const promises = letters.map((l, i) => {
            return new Promise(resolve => {
                setTimeout(() => {
                    l.style.animation = 'none';
                    void l.offsetWidth;
                    l.style.animation = `${animName} ${DURATION}ms ease forwards`;
                    setTimeout(resolve, DURATION);
                }, i * STAGGER);
            });
        });
        return Promise.all(promises);
    }

    // ====================== v8.4.3 : PET / MASCOT / VERSION REVEAL ======================
    var K_VERSION = '__VERSION__';
    var K_TORII_TIME = 7500;
    var kPets = [], kMx = 0, kMy = 0, kTick = false, kClicks = [], kRevealing = false;
    var K_GAZE = { up: [0, -2.8], upl: [-2.6, -2.6], upr: [2.6, -2.6], down: [0, 2.8], l: [-3, 0], r: [3, 0] };

    // one mascot session = one single bubble that thinks all of these, one by one, each with its own reaction
    var K_PET_THOUGHTS = [
        { t: 'hmm… something feels different', r: 'lookup' },
        { t: 'did the login page just change?', r: 'wow' },
        { t: 'wait… is that a new version?', r: 'lookdown' },
        { t: '{v} ?!', r: 'version' },
        { t: 'new look, new pet — a massive update', r: 'spin' },
        { t: 'everything feels faster & smoother', r: 'bounce' },
        { t: 'oh! even the gate looks different…', r: 'lookside' }
    ];

    function kSleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    function kLook(p) {
        var m = p.closest && p.closest('.mascot');
        var g = m && m.getAttribute('data-gaze');
        if (g && K_GAZE[g]) {
            var sc = (p.clientWidth || 40) / 40;
            p.style.setProperty('--lx', (K_GAZE[g][0] * sc).toFixed(2) + 'px');
            p.style.setProperty('--ly', (K_GAZE[g][1] * sc).toFixed(2) + 'px');
            return;
        }
        var r = p.getBoundingClientRect();
        if (!r.width) return;
        var dx = kMx - (r.left + r.width / 2), dy = kMy - (r.top + r.height / 2);
        var d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 160), mm = r.width * 0.1;
        p.style.setProperty('--lx', (dx / d * mm * k).toFixed(2) + 'px');
        p.style.setProperty('--ly', (dy / d * mm * k * 0.75).toFixed(2) + 'px');
    }
    function kGaze(g) {
        var m = document.getElementById('mascot');
        if (!m) return;
        if (g) m.setAttribute('data-gaze', g); else m.removeAttribute('data-gaze');
        document.querySelectorAll('.m-pet').forEach(kLook);
    }
    function kFx(host, ch) {
        var s = document.createElement('span');
        s.className = 'kfx';
        s.textContent = ch;
        s.style.setProperty('--dx', (Math.random() * 30 - 15).toFixed(0) + 'px');
        host.appendChild(s);
        setTimeout(function () { s.remove(); }, 1000);
    }
    function kFlag(el, cls, ms) {
        el.classList.remove(cls);
        void el.offsetWidth;
        el.classList.add(cls);
        setTimeout(function () { el.classList.remove(cls); }, ms);
    }
    function kMood(mood, ms) {
        document.querySelectorAll('.m-pet, #mini-pet').forEach(function (p) { kFlag(p, mood, ms); });
        var m = document.getElementById('mascot');
        if (m) kFx(m, mood === 'happy' ? '✨' : '!');
    }

    // number "scramble" reveal: the pet unveils the version in the footer badge
    function kReveal() {
        if (kRevealing) return;
        kRevealing = true;
        var wrap = document.getElementById('ver-wrap'), num = document.getElementById('ver-num'), mini = document.getElementById('mini-pet');
        kFlag(mini, 'hop', 600);
        kFx(mini.parentNode, '★');
        wrap.classList.add('on');
        var target = K_VERSION, frame = 0, total = target.length * 7;
        var iv = setInterval(function () {
            frame++;
            var out = '';
            for (var i = 0; i < target.length; i++) {
                var ch = target.charAt(i);
                if (ch === '.' || frame > (i + 1) * 7) out += ch;
                else out += Math.floor(Math.random() * 10);
            }
            num.textContent = out;
            if (frame > total) { clearInterval(iv); num.textContent = target; kRevealing = false; kFlag(mini, 'wink', 1000); }
        }, 60);
    }

    // ---- thought bubble helpers ----
    function kShow(span, text, caret) {
        var part = text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
        span.innerHTML = part.replace(/(v[0-9][0-9.]*)/, '<b class="tv">$1</b>') + (caret ? '<i class="caret"></i>' : '');
    }
    function kType(span, text) {
        return new Promise(function (res) {
            var i = 0;
            var iv = setInterval(function () {
                i++;
                kShow(span, text.slice(0, i), true);
                if (i >= text.length) { clearInterval(iv); kShow(span, text, true); res(); }
            }, 40);
        });
    }
    function kErase(span, text) {
        return new Promise(function (res) {
            var i = text.length;
            var iv = setInterval(function () {
                i -= 2;
                if (i <= 0) { clearInterval(iv); span.innerHTML = '<i class="caret"></i>'; res(); return; }
                kShow(span, text.slice(0, i), true);
            }, 14);
        });
    }

    function kReact(name) {
        var m = document.getElementById('mascot'), pet = m.querySelector('.m-pet');
        if (name === 'lookup') { kGaze('upl'); }
        else if (name === 'wow') { kGaze('up'); kFlag(pet, 'wow', 1400); kFlag(pet, 'hop', 600); }
        else if (name === 'lookdown') { kGaze('down'); kFx(m, '?'); }
        else if (name === 'version') {
            kGaze('upr'); kFlag(pet, 'wow', 1600); kFlag(pet, 'hop', 600);
            kFlag(m, 'gold', 1800); kFx(m, '✨'); kReveal();
        }
        else if (name === 'spin') { kGaze('upr'); kFlag(pet, 'spin', 800); }
        else if (name === 'bounce') { kGaze('up'); kFlag(pet, 'bounce', 1200); kFx(m, '♪'); }
        else if (name === 'lookside') { kGaze('r'); setTimeout(function () { kGaze('l'); }, 650); setTimeout(function () { kGaze('r'); }, 1300); }
    }

    // the mascot session: bubble opens once, thoughts follow one after another, then it closes
    async function kPetSession() {
        var th = document.getElementById('thought'), box = document.getElementById('mbox'), m = document.getElementById('mascot');
        if (!th || !m) { await kSleep(8000); return; }
        var span = th.querySelector('.t-text');
        span.innerHTML = '<i class="caret"></i>';
        box.classList.add('thinking');
        th.classList.add('on');
        kGaze('upr');
        await kSleep(600);
        for (var n = 0; n < K_PET_THOUGHTS.length; n++) {
            var it = K_PET_THOUGHTS[n];
            var text = it.t.replace('{v}', 'v' + K_VERSION);
            kGaze('upr');
            await kType(span, text);
            kReact(it.r);
            await kSleep(it.r === 'version' ? 2600 : 2000);
            await kErase(span, text);
            await kSleep(200);
        }
        th.classList.remove('on');
        box.classList.remove('thinking');
        kGaze(null);
        await kSleep(500);
    }

    // pet <-> classic torii gate
    function kPhase(name) {
        var m = document.getElementById('mascot');
        if (!m) return;
        m.classList.toggle('torii', name === 'torii');
        kFlag(m, 'burst', 1100);
    }

    // ONE continuous story: mascot session -> torii gate (with the Japanese word) -> mascot session ...
    async function runCycle() {
        var engDiv = document.getElementById('english-text');
        var japDiv = document.getElementById('japanese-text');
        var engSpans = prepareLetters(englishWord, 'english-letters');
        var japSpans = prepareLetters(japaneseWord, 'japanese-letters');

        engDiv.style.display = 'block';
        await animateWord(engSpans, 'letterInLeft');
        await kSleep(document.documentElement.classList.contains('no-splash') ? 500 : 2000);

        while (true) {
            await kPetSession();

            kPhase('torii');
            await animateWord(engSpans, 'letterOutRight');
            engDiv.style.display = 'none';
            japDiv.style.display = 'block';
            japSpans.forEach(function (s) { s.style.opacity = '0'; });
            await animateWord(japSpans, 'letterInLeft');
            await kSleep(K_TORII_TIME);

            kPhase('pet');
            await animateWord(japSpans, 'letterOutRight');
            japDiv.style.display = 'none';
            engDiv.style.display = 'block';
            engSpans.forEach(function (s) { s.style.opacity = '0'; });
            await animateWord(engSpans, 'letterInLeft');
            await kSleep(500);
        }
    }

    function kInit() {
        kPets = [].slice.call(document.querySelectorAll('.kpet'));
        var mascot = document.getElementById('mascot'), mini = document.getElementById('mini-pet');

        window.addEventListener('mousemove', function (e) {
            kMx = e.clientX; kMy = e.clientY;
            if (kTick) return;
            kTick = true;
            requestAnimationFrame(function () { kTick = false; kPets.forEach(kLook); });
        }, { passive: true });

        if (mascot) {
            var mp = mascot.querySelector('.m-pet');
            mascot.addEventListener('click', function () {
                var now = Date.now();
                kClicks = kClicks.filter(function (t) { return now - t < 2000; });
                kClicks.push(now);
                if (kClicks.length >= 5) { kClicks = []; kFlag(mp, 'dizzy', 2200); kFx(mascot, '💫'); return; }
                kFlag(mascot, 'poke', 650);
                kFx(mascot, ['❤', '✨', '★'][Math.floor(Math.random() * 3)]);
            });
        }
        if (mini) mini.addEventListener('click', function (e) { e.stopPropagation(); kReveal(); });
        var vw = document.getElementById('ver-wrap');
        if (vw) vw.addEventListener('click', kReveal);

        // interactivity with the form
        var inp = document.getElementById('access-key');
        if (inp) {
            inp.addEventListener('focus', function () { document.querySelectorAll('.m-pet,#mini-pet').forEach(function (p) { p.classList.add('big'); }); });
            inp.addEventListener('blur', function () { document.querySelectorAll('.m-pet,#mini-pet').forEach(function (p) { p.classList.remove('big', 'peek'); }); });
            inp.addEventListener('input', function () {
                document.querySelectorAll('.m-pet,#mini-pet').forEach(function (p) { p.classList.add('peek'); });
                clearTimeout(inp._t);
                inp._t = setTimeout(function () { document.querySelectorAll('.m-pet,#mini-pet').forEach(function (p) { p.classList.remove('peek'); }); }, 700);
            });
        }

        // the footer mini pet does little things on its own
        setInterval(function () {
            if (document.hidden || !mini) return;
            kFlag(mini, ['wink', 'hop'][Math.floor(Math.random() * 2)], 1000);
        }, 6000);
    }

    // Initialize everything
    window.addEventListener('DOMContentLoaded', () => {
        runCycle();
        kInit();
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(function(){});
    });
</script>
</body>
</html>
''')


@app.route('/logout')
def logout():
    dev_id = session.get('device_id')
    if dev_id:
        end_session(dev_id)
    session.clear()
    return '''
    <script>
        localStorage.removeItem('kaeru_key');
        window.location.href = '/login';
    </script>
    '''


# ====================== ROUTES ======================

@app.route('/')
def index():
    return redirect(url_for('tasks'))


@app.route('/tasks')
def tasks():
    init_db()
    return render_template('index.html', tab='tasks')


@app.route('/notes')
def notes():
    init_db()
    return render_template('index.html', tab='notes')


@app.route('/timeless')
def timeless():
    init_db()
    return render_template('index.html', tab='timeless')

@app.route('/planner')
def planner():
    init_db()
    return render_template('index.html', tab='planner')

# ====================== TASKS API ======================

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    # Force Dhaka time (UTC+6)
    utc_now = datetime.utcnow()
    dhaka_now = utc_now + timedelta(hours=6)
    today_dhaka = dhaka_now.date()
    tomorrow_dhaka = (dhaka_now + timedelta(days=1)).date()

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY due_date ASC, id ASC").fetchall()
        tasks = []
        for row in rows:
            task = dict(row)
            if task['due_date'] and not task.get('recurring'):
                due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
                task['is_overdue'] = (due_date_obj < today_dhaka) and not task['completed']
            else:
                task['is_overdue'] = False
            tasks.append(task)

        done = [dict(r) for r in conn.execute("SELECT task_id, date FROM recurring_done").fetchall()]
        return jsonify({
            "tasks": tasks,
            "recurring_done": done,
            "today": today_dhaka.strftime('%Y-%m-%d'),
            "tomorrow": tomorrow_dhaka.strftime('%Y-%m-%d')
        })


@app.route('/api/tasks', methods=['POST'])
def add_task():
    data = request.get_json()
    title = data.get('title', '').strip()
    due_date = data.get('due_date')
    if not title:
        return jsonify({"error": "Title required"}), 400

    recurring = 1 if data.get('recurring') else 0
    recurring_freq = data.get('recurring_freq') or 'weekly'
    recurring_end = data.get('recurring_end') or None

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (title, due_date, recurring, recurring_freq, recurring_end)
               VALUES (?, ?, ?, ?, ?)""",
            (title, due_date, recurring, recurring_freq, recurring_end)
        )
        conn.commit()
        new_id = cur.lastrowid
    return jsonify({"success": True, "id": new_id})


def set_completion(conn, task_id, completed, date=None):
    """Recurring tasks complete PER DATE (recurring_done); normal tasks use tasks.completed."""
    row = conn.execute("SELECT recurring, due_date FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    if row['recurring'] and (date or row['due_date']):
        d = date or row['due_date']
        if completed is None:
            completed = 0 if conn.execute(
                "SELECT 1 FROM recurring_done WHERE task_id = ? AND date = ?", (task_id, d)).fetchone() else 1
        if completed:
            conn.execute("INSERT OR IGNORE INTO recurring_done (task_id, date) VALUES (?, ?)", (task_id, d))
        else:
            conn.execute("DELETE FROM recurring_done WHERE task_id = ? AND date = ?", (task_id, d))
        return 1 if completed else 0
    if completed is None:
        conn.execute("UPDATE tasks SET completed = NOT completed WHERE id = ?", (task_id,))
    else:
        conn.execute("UPDATE tasks SET completed = ? WHERE id = ?", (1 if completed else 0, task_id))
    return completed


@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    data = request.get_json(silent=True) or {}
    with get_db() as conn:
        set_completion(conn, task_id, None, data.get('date'))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    with get_db() as conn:
        conn.execute("DELETE FROM recurring_done WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/tasks/overdue/complete', methods=['POST'])
def complete_all_overdue():
    today = (datetime.utcnow() + timedelta(hours=6)).strftime('%Y-%m-%d')
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE tasks SET completed = 1 WHERE completed = 0 AND COALESCE(recurring, 0) = 0 AND due_date IS NOT NULL AND due_date < ?",
            (today,)
        )
        conn.commit()
    return jsonify({"success": True, "count": cur.rowcount})


@app.route('/api/tasks/overdue/delete', methods=['POST'])
def delete_all_overdue():
    today = (datetime.utcnow() + timedelta(hours=6)).strftime('%Y-%m-%d')
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM tasks WHERE completed = 0 AND COALESCE(recurring, 0) = 0 AND due_date IS NOT NULL AND due_date < ?",
            (today,)
        )
        conn.commit()
    return jsonify({"success": True, "count": cur.rowcount})


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def edit_task(task_id):
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400

    fields = ["title = ?"]
    params = [title]

    if data.get('due_date') is not None:
        fields.append("due_date = ?")
        params.append(data['due_date'])

    if 'recurring' in data:
        rec = 1 if data['recurring'] else 0
        fields += ["recurring = ?", "recurring_freq = ?", "recurring_end = ?"]
        params += [rec, data.get('recurring_freq') or 'weekly', data.get('recurring_end') or None]
        if not rec:
            fields.append("recurring_paused = 0")

    params.append(task_id)
    with get_db() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/tasks/history', methods=['GET'])
def get_task_history():
    # Use Dhaka time (UTC+6) for 30-day calculation
    utc_now = datetime.utcnow()
    dhaka_now = utc_now + timedelta(hours=6)
    thirty_days_ago_dhaka = (dhaka_now - timedelta(days=30)).strftime("%Y-%m-%d")
    
    with get_db() as conn:
        rows = conn.execute('''
            SELECT id, title, due_date, completed, created_at
            FROM tasks
            WHERE completed = 1 AND COALESCE(recurring, 0) = 0 AND due_date >= ?
            UNION ALL
            SELECT t.id, t.title, d.date AS due_date, 1 AS completed, t.created_at
            FROM recurring_done d JOIN tasks t ON t.id = d.task_id
            WHERE d.date >= ?
            ORDER BY due_date DESC, id DESC
        ''', (thirty_days_ago_dhaka, thirty_days_ago_dhaka)).fetchall()
        return jsonify([dict(row) for row in rows])


# ====================== PROJECTS API ======================

@app.route('/api/projects', methods=['GET'])
def get_projects():
    with get_db() as conn:
        # Ensure position column exists
        cursor = conn.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'position' not in columns:
            conn.execute("ALTER TABLE projects ADD COLUMN position INTEGER DEFAULT 0")
        
        projects = []
        rows = conn.execute("""
            SELECT * FROM projects 
            ORDER BY position ASC, id ASC
        """).fetchall()
        
        for row in rows:
            p = dict(row)
            subs = conn.execute(
                "SELECT * FROM subtasks WHERE project_id = ? ORDER BY id", 
                (p['id'],)
            ).fetchall()
            sub_list = [dict(s) for s in subs]
            completed_count = sum(1 for s in sub_list if s['completed'] == 1)
            total = len(sub_list) or 1
            p['subtasks'] = sub_list
            p['completed_count'] = completed_count
            p['total'] = len(sub_list)
            p['progress'] = round((completed_count / total) * 100)
            projects.append(p)
        
        return jsonify(projects)


# ====================== PROJECTS REORDER API (Drag & Drop) ======================

@app.route('/api/projects/reorder', methods=['POST'])
def reorder_projects():
    """Reorder projects based on drag & drop from frontend"""
    try:
        data = request.get_json()
        order = data.get('order', [])
        
        if not order:
            return jsonify({"error": "No order data provided"}), 400

        with get_db() as conn:
            for item in order:
                project_id = item.get('id')
                position = item.get('position')
                
                if project_id is not None and position is not None:
                    conn.execute(
                        "UPDATE projects SET id = id WHERE id = ?",  # dummy to allow position update
                        (project_id,)
                    )
                    # Actually we will add a 'position' column later if needed.
                    # For now we reorder by updating a new position column or by id order.
            
            # Better approach: Add position column if not exists and update positions
            # First ensure 'position' column exists
            cursor = conn.execute("PRAGMA table_info(projects)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'position' not in columns:
                conn.execute("ALTER TABLE projects ADD COLUMN position INTEGER DEFAULT 0")
            
            # Now update positions according to new order
            for idx, item in enumerate(order):
                conn.execute(
                    "UPDATE projects SET position = ? WHERE id = ?",
                    (idx, item['id'])
                )
            
            conn.commit()
        
        return jsonify({"success": True, "message": "Projects reordered successfully"})
        
    except Exception as e:
        print(f"Project reorder error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/projects', methods=['POST'])
def add_project():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    added_date = datetime.now().strftime("%Y-%m-%d")
    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("INSERT INTO projects (title, added_date, last_updated) VALUES (?, ?, ?)", 
                     (title, added_date, last_updated))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def edit_project(project_id):
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    with get_db() as conn:
        conn.execute("UPDATE projects SET title = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
                     (title, project_id))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    with get_db() as conn:
        conn.execute("DELETE FROM subtasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/projects/<int:project_id>/subtasks', methods=['POST'])
def add_subtask(project_id):
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO subtasks (project_id, title) VALUES (?, ?)", (project_id, title))
        conn.execute("UPDATE projects SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/subtasks/<int:sub_id>/toggle', methods=['POST'])
def toggle_subtask(sub_id):
    with get_db() as conn:
        # Get the project_id before updating
        row = conn.execute("SELECT project_id FROM subtasks WHERE id = ?", (sub_id,)).fetchone()
        if row:
            # Toggle the subtask
            conn.execute("UPDATE subtasks SET completed = NOT completed WHERE id = ?", (sub_id,))
            # Update the project's last_updated timestamp
            conn.execute("UPDATE projects SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", (row['project_id'],))
            conn.commit()
    return jsonify({"success": True})


@app.route('/api/subtasks/<int:sub_id>', methods=['PUT'])
def edit_subtask(sub_id):
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    with get_db() as conn:
        conn.execute("UPDATE subtasks SET title = ? WHERE id = ?", (title, sub_id))
        row = conn.execute("SELECT project_id FROM subtasks WHERE id = ?", (sub_id,)).fetchone()
        if row:
            conn.execute("UPDATE projects SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", (row['project_id'],))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/subtasks/<int:sub_id>', methods=['DELETE'])
def delete_subtask(sub_id):
    with get_db() as conn:
        row = conn.execute("SELECT project_id FROM subtasks WHERE id = ?", (sub_id,)).fetchone()
        if row:
            conn.execute("DELETE FROM subtasks WHERE id = ?", (sub_id,))
            conn.execute("UPDATE projects SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", (row['project_id'],))
        conn.commit()
    return jsonify({"success": True})


# ====================== NOTES API ======================

@app.route('/api/notes', methods=['GET'])
def get_notes():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at, pinned, position FROM notes ORDER BY pinned DESC, position ASC, updated_at DESC"
        ).fetchall()
        return jsonify([dict(row) for row in rows])


@app.route('/api/notes', methods=['POST'])
def create_note():
    data = request.get_json() or {}
    title = data.get('title', 'Untitled Note')
    with get_db() as conn:
        max_pos = conn.execute("SELECT MAX(position) FROM notes").fetchone()[0] or 0
        conn.execute("INSERT INTO notes (title, position) VALUES (?, ?)", (title, max_pos + 1))
        note_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    return jsonify({"id": note_id, "success": True})


@app.route('/api/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({"error": "Not found"}), 404


@app.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    pinned = data.get('pinned')
    position = data.get('position')
    with get_db() as conn:
        if pinned is not None:
            conn.execute("UPDATE notes SET pinned = ? WHERE id = ?", (1 if pinned else 0, note_id))
        if position is not None:
            conn.execute("UPDATE notes SET position = ? WHERE id = ?", (position, note_id))
        if title is not None or content is not None:
            conn.execute("""
                UPDATE notes
                SET title = COALESCE(?, title),
                    content = COALESCE(?, content),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (title, content, note_id))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    with get_db() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/notes/reorder', methods=['POST'])
def reorder_notes():
    data = request.get_json()
    order = data.get('order', [])
    with get_db() as conn:
        for item in order:
            conn.execute("UPDATE notes SET position = ? WHERE id = ?", (item['position'], item['id']))
        conn.commit()
    return jsonify({"success": True})

# ====================== TIMELESS API ======================

@app.route('/api/timeless', methods=['GET'])
def get_timeless():
    with get_db() as conn:
        nodes = conn.execute(
            "SELECT * FROM timeless_nodes ORDER BY hijri_year ASC, gregorian_year ASC, id ASC"
        ).fetchall()
        result = []
        for node in nodes:
            n = dict(node)
            # Get sources
            sources = conn.execute(
                "SELECT * FROM timeless_sources WHERE node_id = ? ORDER BY id", (n['id'],)
            ).fetchall()
            n['sources'] = [dict(s) for s in sources]
            
            # Parse tags safely - DEBUG
            print(f"Node {n['id']} - Raw tags from DB: '{n.get('tags', '')}'")
            
            if n.get('tags') and n['tags'].strip():
                n['tags_list'] = [t.strip() for t in n['tags'].split(',') if t.strip()]
            else:
                n['tags_list'] = []
            
            print(f"Node {n['id']} - Parsed tags_list: {n['tags_list']}")
            
            result.append(n)
        return jsonify(result)


@app.route('/api/timeless', methods=['POST'])
def add_timeless():
    data = request.get_json()
    print(f"=== ADD NODE - Received data: {data}")  # DEBUG
    
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    
    description = data.get('description', '')
    gregorian_year = data.get('gregorian_year')
    hijri_year = data.get('hijri_year')
    sidenote = data.get('sidenote', '')
    sources = data.get('sources', [])
    tags = data.get('tags', '')
    
    print(f"Tags before save: '{tags}'")  # DEBUG

    # Auto convert year if only one is provided
    if gregorian_year and not hijri_year:
        hijri_year = gregorian_to_hijri_year(int(gregorian_year))
    elif hijri_year and not gregorian_year:
        gregorian_year = hijri_to_gregorian_year(int(hijri_year))

    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO timeless_nodes 
               (title, description, gregorian_year, hijri_year, sidenote, tags) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, gregorian_year, hijri_year, sidenote, tags)
        )
        node_id = cursor.lastrowid
        
        print(f"Saved node {node_id} with tags: '{tags}'")  # DEBUG

        for src in sources:
            if src.get('url') and src.get('display_text'):
                conn.execute(
                    "INSERT INTO timeless_sources (node_id, display_text, url) VALUES (?, ?, ?)",
                    (node_id, src['display_text'], src['url'])
                )
        conn.commit()
    
    return jsonify({"id": node_id, "success": True})


@app.route('/api/timeless/<int:node_id>', methods=['PUT'])
def edit_timeless(node_id):
    data = request.get_json()
    print(f"=== EDIT NODE {node_id} - Received data: {data}")  # DEBUG
    
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400  # Fixed the string quote issue

    description = data.get('description', '')
    gregorian_year = data.get('gregorian_year')
    hijri_year = data.get('hijri_year')
    sidenote = data.get('sidenote', '')
    sources = data.get('sources', [])
    tags = data.get('tags', '')
    
    print(f"Tags for update: '{tags}'")  # DEBUG

    if gregorian_year and not hijri_year:
        hijri_year = gregorian_to_hijri_year(int(gregorian_year))
    elif hijri_year and not gregorian_year:
        gregorian_year = hijri_to_gregorian_year(int(hijri_year))

    with get_db() as conn:
        conn.execute(
            """UPDATE timeless_nodes 
               SET title=?, description=?, gregorian_year=?, hijri_year=?, 
                   sidenote=?, tags=?, updated_at=CURRENT_TIMESTAMP 
               WHERE id=?""",
            (title, description, gregorian_year, hijri_year, sidenote, tags, node_id)
        )
        conn.execute("DELETE FROM timeless_sources WHERE node_id = ?", (node_id,))
        
        for src in sources:
            if src.get('url') and src.get('display_text'):
                conn.execute(
                    "INSERT INTO timeless_sources (node_id, display_text, url) VALUES (?, ?, ?)",
                    (node_id, src['display_text'], src['url'])
                )
        conn.commit()
    
    print(f"Updated node {node_id} with tags: '{tags}'")  # DEBUG
    return jsonify({"success": True})


@app.route('/api/timeless/<int:node_id>', methods=['DELETE'])
def delete_timeless(node_id):
    with get_db() as conn:
        conn.execute("DELETE FROM timeless_sources WHERE node_id = ?", (node_id,))
        conn.execute("DELETE FROM timeless_nodes WHERE id = ?", (node_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/timeless/tags', methods=['GET'])
def get_all_tags():
    with get_db() as conn:
        rows = conn.execute("SELECT tags FROM timeless_nodes WHERE tags != ''").fetchall()
        all_tags = set()
        for row in rows:
            for tag in row['tags'].split(','):
                t = tag.strip()
                if t:
                    all_tags.add(t)
        return jsonify(sorted(list(all_tags)))
    




# ====================== LINKS API ======================

@app.route('/links')
def links():

    return render_template('index.html', tab='links')


@app.route('/api/links', methods=['GET'])
def get_links():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM links ORDER BY pinned DESC, sort_order ASC, id ASC"   # ← This line must say DESC
        ).fetchall()
        return jsonify([dict(row) for row in rows])


@app.route('/api/links', methods=['POST'])
def add_link():
    data = request.get_json()
    title = data.get('title', '').strip()
    url = data.get('url', '').strip()
    
    if not title or not url:
        return jsonify({"error": "Title and URL are required"}), 400
    
    with get_db() as conn:
        # Shift all unpinned links down so new one becomes the first unpinned
        conn.execute("UPDATE links SET sort_order = sort_order + 1 WHERE pinned = 0")
        
        conn.execute(
            """INSERT INTO links (title, url, click_count, sort_order, pinned) 
               VALUES (?, ?, ?, ?, ?)""",
            (title, url, 0, 0, 0)   # new link = unpinned + sort_order 0
        )
        conn.commit()
        
        link_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
    return jsonify({"id": link_id, "success": True})

@app.route('/api/links/<int:link_id>', methods=['PUT'])
def update_link(link_id):
    data = request.get_json()
    title = data.get('title', '').strip()
    url = data.get('url', '').strip()
    
    if not title or not url:
        return jsonify({"error": "Title and URL are required"}), 400
    
    with get_db() as conn:
        conn.execute(
            "UPDATE links SET title = ?, url = ? WHERE id = ?",
            (title, url, link_id)
        )
        conn.commit()
        
    return jsonify({"success": True})


@app.route('/api/links/<int:link_id>', methods=['DELETE'])
def delete_link(link_id):
    with get_db() as conn:
        conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
        conn.commit()
        
    return jsonify({"success": True})


@app.route('/api/links/<int:link_id>/click', methods=['POST'])
def increment_link_click(link_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE links SET click_count = click_count + 1 WHERE id = ?",
            (link_id,)
        )
        conn.commit()
        
    return jsonify({"success": True})


@app.route('/api/links/<int:link_id>/pin', methods=['POST'])
def toggle_link_pin(link_id):
    data = request.get_json()
    pinned = data.get('pinned', False)
    
    with get_db() as conn:
        conn.execute(
            "UPDATE links SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, link_id)
        )
        conn.commit()
        
    return jsonify({"success": True})


@app.route('/api/links/reorder', methods=['POST'])
def reorder_links():
    data = request.get_json()
    order = data.get('order', [])
    
    with get_db() as conn:
        for item in order:
            conn.execute(
                "UPDATE links SET sort_order = ? WHERE id = ?",
                (item['order'], item['id'])
            )
        conn.commit()
        
    return jsonify({"success": True})


@app.route('/api/links/import', methods=['POST'])
def import_links():
    data = request.get_json()
    imported_links = data.get('links', [])
    
    if not isinstance(imported_links, list):
        return jsonify({"error": "Invalid data format"}), 400
    
    with get_db() as conn:
        # Clear existing links
        conn.execute("DELETE FROM links")
        
        # Insert imported links
        for idx, link in enumerate(imported_links):
            conn.execute(
                """INSERT INTO links (title, url, click_count, sort_order, pinned) 
                   VALUES (?, ?, ?, ?, ?)""",
                (link.get('title', ''), 
                 link.get('url', ''), 
                 link.get('click_count', 0),
                 idx,
                 1 if link.get('pinned') else 0)
            )
        conn.commit()
        
    return jsonify({"success": True})





# ====================== IMPORT/EXPORT API ======================
@app.route('/api/export', methods=['POST'])
def export_data():
    """Export all data as JSON (updated with recurring task fields)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        access_key = data.get('access_key', '')
        
        print(f"Export attempt - Received key: '{access_key}'")  # Debug
        print(f"Expected key: '{get_password()}'")  # Debug
        
        # Verify access key
        if access_key != get_password():
            return jsonify({"error": "Invalid access key"}), 401
        
        with get_db() as conn:
            # Export all tables with updated schema
            export = {
                "version": "2.0",  # Version bump for recurring tasks
                "export_date": datetime.now().isoformat(),
                "tasks": [dict(row) for row in conn.execute("SELECT * FROM tasks").fetchall()],
                "projects": [dict(row) for row in conn.execute("SELECT * FROM projects").fetchall()],
                "subtasks": [dict(row) for row in conn.execute("SELECT * FROM subtasks").fetchall()],
                "notes": [dict(row) for row in conn.execute("SELECT * FROM notes").fetchall()],
                "timeless_nodes": [dict(row) for row in conn.execute("SELECT * FROM timeless_nodes").fetchall()],
                "timeless_sources": [dict(row) for row in conn.execute("SELECT * FROM timeless_sources").fetchall()],
                "links": [dict(row) for row in conn.execute("SELECT * FROM links").fetchall()],
                "recurring_done": [dict(row) for row in conn.execute("SELECT * FROM recurring_done").fetchall()]
            }
            
        print(f"Export successful - {len(export['tasks'])} tasks, {len(export['projects'])} projects")  # Debug
        return jsonify(export)
        
    except Exception as e:
        print(f"Export error: {str(e)}")  # Debug
        return jsonify({"error": f"Export failed: {str(e)}"}), 500



@app.route('/api/import', methods=['POST'])
def import_data():
    """Import data from JSON backup (handles both v1 and v2 formats)"""
    data = request.get_json()
    access_key = data.get('access_key', '')
    backup_data = data.get('data', {})
    
    # Verify access key
    if access_key != get_password():
        return jsonify({"error": "Invalid access key"}), 401
    
    # Validate data structure
    required_tables = ['tasks', 'projects', 'subtasks', 'notes', 'timeless_nodes', 'timeless_sources', 'links']
    for table in required_tables:
        if table not in backup_data:
            return jsonify({"error": f"Invalid backup format: missing {table}"}), 400
    
    with get_db() as conn:
        try:
            # Clear all existing data (disable foreign keys temporarily)
            conn.execute("PRAGMA foreign_keys = OFF")
            
            # Clear all tables in correct order
            conn.execute("DELETE FROM timeless_sources")
            conn.execute("DELETE FROM timeless_nodes")
            conn.execute("DELETE FROM subtasks")
            conn.execute("DELETE FROM projects")
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM recurring_done")
            conn.execute("DELETE FROM notes")
            conn.execute("DELETE FROM links")
            
            # Reset autoincrement counters
            conn.execute("DELETE FROM sqlite_sequence")
            
            # Check tasks table columns for recurring fields
            cursor = conn.execute("PRAGMA table_info(tasks)")
            task_columns = [row[1] for row in cursor.fetchall()]
            has_recurring_fields = all(col in task_columns for col in ['recurring', 'recurring_freq', 'recurring_end', 'recurring_paused'])
            
            # Import tasks (handle both old and new format)
            for task in backup_data.get('tasks', []):
                # Check if task has recurring fields, add defaults if missing
                if has_recurring_fields:
                    conn.execute(
                        """INSERT INTO tasks (id, title, completed, due_date, created_at, 
                           recurring, recurring_freq, recurring_end, recurring_paused) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (task.get('id'), task.get('title'), task.get('completed', 0), 
                         task.get('due_date'), task.get('created_at'),
                         task.get('recurring', 0), task.get('recurring_freq', 'weekly'),
                         task.get('recurring_end'), task.get('recurring_paused', 0))
                    )
                else:
                    conn.execute(
                        "INSERT INTO tasks (id, title, completed, due_date, created_at) VALUES (?, ?, ?, ?, ?)",
                        (task.get('id'), task.get('title'), task.get('completed', 0), 
                         task.get('due_date'), task.get('created_at'))
                    )
            
            for rd in backup_data.get('recurring_done', []):
                conn.execute("INSERT OR IGNORE INTO recurring_done (task_id, date) VALUES (?, ?)", (rd.get('task_id'), rd.get('date')))

            # Import projects
            for project in backup_data.get('projects', []):
                conn.execute(
                    "INSERT INTO projects (id, title, added_date, last_updated) VALUES (?, ?, ?, ?)",
                    (project.get('id'), project.get('title'), project.get('added_date'), project.get('last_updated'))
                )
            
            # Import subtasks
            for subtask in backup_data.get('subtasks', []):
                conn.execute(
                    "INSERT INTO subtasks (id, project_id, title, completed) VALUES (?, ?, ?, ?)",
                    (subtask.get('id'), subtask.get('project_id'), subtask.get('title'), subtask.get('completed', 0))
                )
            
            # Import notes
            for note in backup_data.get('notes', []):
                conn.execute(
                    "INSERT INTO notes (id, title, content, pinned, position, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (note.get('id'), note.get('title'), note.get('content'), note.get('pinned', 0),
                     note.get('position', 0), note.get('created_at'), note.get('updated_at'))
                )
            
            # Import timeless nodes
            for node in backup_data.get('timeless_nodes', []):
                conn.execute(
                    "INSERT INTO timeless_nodes (id, title, description, gregorian_year, hijri_year, tags, sidenote, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (node.get('id'), node.get('title'), node.get('description'), node.get('gregorian_year'),
                     node.get('hijri_year'), node.get('tags'), node.get('sidenote'), node.get('created_at'), node.get('updated_at'))
                )
            
            # Import timeless sources
            for source in backup_data.get('timeless_sources', []):
                conn.execute(
                    "INSERT INTO timeless_sources (id, node_id, display_text, url) VALUES (?, ?, ?, ?)",
                    (source.get('id'), source.get('node_id'), source.get('display_text'), source.get('url'))
                )
            
            # Import links
            for link in backup_data.get('links', []):
                conn.execute(
                    "INSERT INTO links (id, title, url, click_count, sort_order, pinned, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (link.get('id'), link.get('title'), link.get('url'), link.get('click_count', 0),
                     link.get('sort_order', 0), link.get('pinned', 0), link.get('created_at'), link.get('updated_at'))
                )
            
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            
        except Exception as e:
            conn.execute("PRAGMA foreign_keys = ON")
            return jsonify({"error": f"Import failed: {str(e)}"}), 500
    
    return jsonify({"success": True, "message": "Data imported successfully"})



@app.route('/api/server-time', methods=['GET'])
def get_server_time():
    """Return server's current time in Dhaka timezone (UTC+6)"""
    utc_now = datetime.utcnow()
    dhaka_time = utc_now + timedelta(hours=6)
    
    return jsonify({
        'datetime': dhaka_time.isoformat(),
        'date': dhaka_time.strftime('%Y-%m-%d'),
        'time': dhaka_time.strftime('%I:%M %p').lstrip('0').lower(),
        'datetime_formatted': dhaka_time.strftime('%a %b %d, %I:%M %p').lstrip('0').replace(' 0', ' '),
        'weekday_short': dhaka_time.strftime('%a'),
        'day': int(dhaka_time.strftime('%d')),
        'month_short': dhaka_time.strftime('%b'),
        'hour_12': dhaka_time.strftime('%I').lstrip('0'),
        'minute': dhaka_time.strftime('%M'),
        'ampm': dhaka_time.strftime('%p').lower()
    })



@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    try:
        # Just check if we can import and basic response
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat(),
            'server': 'running'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/sync/status', methods=['GET'])
def sync_status():
    """Check if database is accessible and return status"""
    try:
        with get_db() as conn:
            # Check if tables exist and get counts (don't rely on updated_at columns)
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            project_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            note_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            
            # Get the most recent task by id (as a proxy for last update)
            latest_task = conn.execute(
                "SELECT id, due_date, created_at FROM tasks ORDER BY id DESC LIMIT 1"
            ).fetchone()
            
            latest_project = conn.execute(
                "SELECT id, added_date, last_updated FROM projects ORDER BY id DESC LIMIT 1"
            ).fetchone()
            
            return jsonify({
                'status': 'ok',
                'database_accessible': True,
                'counts': {
                    'tasks': task_count,
                    'projects': project_count,
                    'notes': note_count
                },
                'latest': {
                    'task_id': latest_task['id'] if latest_task else None,
                    'task_date': latest_task['due_date'] if latest_task else None,
                    'project_id': latest_project['id'] if latest_project else None
                },
                'server_time': datetime.utcnow().isoformat()
            })
    except Exception as e:
        print(f"Sync status error: {str(e)}")  # Debug log
        return jsonify({
            'status': 'error',
            'database_accessible': False,
            'error': str(e)
        }), 500

@app.route('/api/sync/verify', methods=['POST'])
def verify_sync():
    """Verify frontend data matches backend"""
    try:
        frontend_data = request.get_json()
        
        with get_db() as conn:
            # Get actual backend data for comparison
            backend_tasks = [dict(row) for row in conn.execute(
                "SELECT id, title, completed, due_date FROM tasks ORDER BY id"
            ).fetchall()]
            
            backend_projects = [dict(row) for row in conn.execute(
                "SELECT id, title FROM projects ORDER BY id"
            ).fetchall()]
            
            # Create simple hash for comparison
            import hashlib
            import json
            
            backend_string = json.dumps({
                'tasks': backend_tasks,
                'projects': backend_projects
            }, sort_keys=True)
            backend_hash = hashlib.md5(backend_string.encode()).hexdigest()
            
            frontend_string = json.dumps({
                'tasks': frontend_data.get('tasks', []),
                'projects': frontend_data.get('projects', [])
            }, sort_keys=True)
            frontend_hash = hashlib.md5(frontend_string.encode()).hexdigest()
            
            return jsonify({
                'is_synced': backend_hash == frontend_hash,
                'backend_tasks_count': len(backend_tasks),
                'backend_projects_count': len(backend_projects),
                'frontend_tasks_count': len(frontend_data.get('tasks', []))
            })
    except Exception as e:
        print(f"Verify sync error: {str(e)}")  # Debug log
        return jsonify({
            'error': str(e),
            'is_synced': False
        }), 500

# ====================== YEAR CONVERSION HELPERS ======================

def gregorian_to_hijri_year(g_year):
    """Approximate Gregorian year to Hijri year conversion."""
    return round((g_year - 622) * (33 / 32))


def hijri_to_gregorian_year(h_year):
    """Approximate Hijri year to Gregorian year conversion."""
    return round(h_year * (32 / 33) + 622)

@app.route('/debug/schema')
def debug_schema():
    with get_db() as conn:
        cursor = conn.execute("PRAGMA table_info(timeless_nodes)")
        columns = cursor.fetchall()
        return jsonify([dict(col) for col in columns])
    



# ====================== PLANNER API ======================

@app.route('/api/planner/tasks', methods=['GET'])
def get_planner_tasks():
    # Get range from query params (e.g., start=2026-04-01&end=2026-04-30)
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    with get_db() as conn:
        # 1. Fetch regular tasks in range
        query = "SELECT * FROM tasks WHERE (due_date BETWEEN ? AND ?) OR (recurring = 1 AND recurring_paused = 0)"
        rows = conn.execute(query, (start_date, end_date)).fetchall()
        
        # Convert to list of dicts
        tasks = [dict(row) for row in rows]
        
    return jsonify(tasks)


@app.route('/api/planner/tasks/<int:task_id>', methods=['PUT'])
def update_planner_task(task_id):
    """Update task with recurring settings"""
    data = request.get_json()
    
    with get_db() as conn:
        # Build update query dynamically
        updates = []
        params = []
        
        if 'title' in data:
            updates.append("title = ?")
            params.append(data['title'])
        if 'completed' in data:
            set_completion(conn, task_id, 1 if data['completed'] else 0, data.get('date'))
        if 'due_date' in data:
            updates.append("due_date = ?")
            params.append(data['due_date'])
        if 'recurring' in data:
            updates.append("recurring = ?")
            params.append(1 if data['recurring'] else 0)
        if 'recurring_freq' in data:
            updates.append("recurring_freq = ?")
            params.append(data['recurring_freq'])
        if 'recurring_end' in data:
            updates.append("recurring_end = ?")
            params.append(data['recurring_end'] if data['recurring_end'] else None)
        if 'recurring_paused' in data:
            updates.append("recurring_paused = ?")
            params.append(1 if data['recurring_paused'] else 0)
        
        if updates:
            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
            params.append(task_id)
            conn.execute(query, params)
            conn.commit()
    
    return jsonify({"success": True})


@app.route('/api/planner/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_planner_task(task_id):
    data = request.get_json()
    # Use 1 for true, 0 for false for SQLite compatibility
    completed = 1 if data.get('completed') else 0
    
    with get_db() as conn:
        set_completion(conn, task_id, completed, data.get('date'))
        conn.commit()
    
    return jsonify({"success": True})


@app.route('/api/recurring/bulk', methods=['POST'])
def recurring_bulk():
    """Recurring Task Manager bulk actions: pause_all | resume_all | delete_ended"""
    action = (request.get_json(silent=True) or {}).get('action')
    today = (datetime.utcnow() + timedelta(hours=6)).strftime('%Y-%m-%d')
    with get_db() as conn:
        if action == 'pause_all':
            cur = conn.execute("UPDATE tasks SET recurring_paused = 1 WHERE recurring = 1 AND recurring_paused = 0")
        elif action == 'resume_all':
            cur = conn.execute("UPDATE tasks SET recurring_paused = 0 WHERE recurring = 1 AND recurring_paused = 1")
        elif action == 'delete_ended':
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM tasks WHERE recurring = 1 AND recurring_end IS NOT NULL AND recurring_end < ?", (today,)).fetchall()]
            for i in ids:
                conn.execute("DELETE FROM recurring_done WHERE task_id = ?", (i,))
                conn.execute("DELETE FROM tasks WHERE id = ?", (i,))
            conn.commit()
            return jsonify({"success": True, "count": len(ids)})
        else:
            return jsonify({"error": "Unknown action"}), 400
        conn.commit()
    return jsonify({"success": True, "count": cur.rowcount})


@app.route('/api/planner/tasks/<int:task_id>/recurring', methods=['PUT'])
def toggle_planner_recurring(task_id):
    """Pause or resume recurring task"""
    data = request.get_json()
    paused = data.get('recurring_paused', 0)
    
    with get_db() as conn:
        conn.execute("UPDATE tasks SET recurring_paused = ? WHERE id = ?", (paused, task_id))
        conn.commit()
    
    return jsonify({"success": True})




def get_client_info():
    """Simple UA parsing (order matters: iOS/Android UAs also contain 'Mac'/'Linux')."""
    ua = request.headers.get('User-Agent', '')
    if "iPhone" in ua or "iPad" in ua or "iPod" in ua: os_name = "iOS"
    elif "Android" in ua: os_name = "Android"
    elif "Windows" in ua: os_name = "Windows"
    elif "Mac OS" in ua or "Macintosh" in ua: os_name = "macOS"
    elif "CrOS" in ua: os_name = "ChromeOS"
    elif "Linux" in ua: os_name = "Linux"
    else: os_name = "Unknown"

    if "Edg" in ua: browser = "Edge"
    elif "OPR" in ua or "Opera" in ua: browser = "Opera"
    elif "Firefox" in ua or "FxiOS" in ua: browser = "Firefox"
    elif "Chrome" in ua or "CriOS" in ua: browser = "Chrome"
    elif "Safari" in ua: browser = "Safari"
    else: browser = "Unknown"

    device = "Mobile" if ("Mobile" in ua or "Android" in ua or "iPhone" in ua) else "Desktop"
    if "iPad" in ua or ("Android" in ua and "Mobile" not in ua): device = "Tablet"

    return {
        "device_name": f"{device} · {os_name}",
        "os_name": os_name,
        "browser_name": browser,
        "ip": request.remote_addr
    }


def register_login(device_id, token):
    """One row per device: logging in again on the same device updates it, never adds a new one."""
    info = get_client_info()
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM session_logs WHERE session_id = ?", (device_id,)).fetchone()
        if exists:
            conn.execute('''
                UPDATE session_logs SET device_name=?, os_name=?, browser_name=?, ip_address=?,
                    login_time=CURRENT_TIMESTAMP, last_active=CURRENT_TIMESTAMP, logout_time=NULL,
                    status='active', token=?, login_count=COALESCE(login_count,0)+1
                WHERE session_id=?
            ''', (info['device_name'], info['os_name'], info['browser_name'], info['ip'], token, device_id))
        else:
            conn.execute('''
                INSERT INTO session_logs
                (session_id, device_name, os_name, browser_name, ip_address, status, token, login_count)
                VALUES (?, ?, ?, ?, ?, 'active', ?, 1)
            ''', (device_id, info['device_name'], info['os_name'], info['browser_name'], info['ip'], token))
        conn.commit()


def end_session(session_id):
    with get_db() as conn:
        conn.execute("UPDATE session_logs SET status='logged_out', token=NULL, logout_time=CURRENT_TIMESTAMP WHERE session_id=?", (session_id,))
        conn.commit()


def clear_session_logs():
    """Clear history = remove devices that are logged out (active devices stay)."""
    with get_db() as conn:
        conn.execute("DELETE FROM session_logs WHERE status != 'active'")
        conn.commit()


@app.route('/api/settings/sessions', methods=['GET'])
def get_sessions():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, session_id, device_name, os_name, browser_name, ip_address,
                   login_time, last_active, logout_time, status, COALESCE(login_count, 1) AS login_count,
                   CASE WHEN session_id = ? THEN 1 ELSE 0 END as is_current
            FROM session_logs
            ORDER BY is_current DESC, login_time DESC
        """, (session.get('device_id'),)).fetchall()
        return jsonify([dict(row) for row in rows])


@app.route('/api/settings/sessions/<session_id>', methods=['DELETE'])
def terminate_session(session_id):
    """End a specific device session (really invalidates its token)"""
    try:
        is_current = session.get('device_id') == session_id
        end_session(session_id)
        if is_current:
            session.clear()
        return jsonify({
            "success": True,
            "message": "Session terminated successfully",
            "is_current_device": is_current
        })
    except Exception as e:
        print(f"Error terminating session: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/settings/sessions/clear', methods=['POST'])
def clear_all_logs():
    clear_session_logs()
    return jsonify({"success": True})


@app.route('/api/settings/password', methods=['POST'])
def change_password():
    data = request.get_json()
    current_key = data.get('current_key') or ''
    new_key = data.get('new_key')

    if not hmac.compare_digest(current_key.encode(), get_password().encode()):
        return jsonify({"error": "Current password incorrect"}), 401

    if not new_key or len(new_key) < 4:
        return jsonify({"error": "New password too short"}), 400

    with open(PASSWORD_FILE, 'w') as f:
        f.write(new_key)

    # Logout ALL devices (force re-login everywhere)
    with get_db() as conn:
        conn.execute("UPDATE session_logs SET status='logged_out', token=NULL, logout_time=CURRENT_TIMESTAMP WHERE status='active'")
        conn.commit()

    session.clear()
    return jsonify({"success": True, "message": "Password changed. All devices logged out."})


# ====================== PWA (v7.4.3) ======================

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="112" fill="#09090b"/><circle cx="256" cy="256" r="150" fill="none" stroke="#10b981" stroke-width="18" opacity=".35"/><circle cx="256" cy="256" r="84" fill="#10b981"/><circle cx="232" cy="240" r="12" fill="#09090b"/><circle cx="280" cy="240" r="12" fill="#09090b"/><path d="M228 280 Q256 304 284 280" stroke="#09090b" stroke-width="10" fill="none" stroke-linecap="round"/></svg>'''

ICON_MASKABLE_SVG = ICON_SVG.replace('rx="112"', 'rx="0"').replace('r="84"', 'r="70"').replace('r="150"', 'r="125"')

SW_JS = '''
const VERSION = 'kaeru-__VERSION__';
const OFFLINE_HTML = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kaeru - Offline</title><body style="background:#09090b;color:#a8a8bc;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center"><div><div style="font-size:42px">&#9679;</div><h2 style="color:#f0f0f5">You are offline</h2><p>Kaeru will reconnect when the network is back.</p><button onclick="location.reload()" style="margin-top:12px;padding:8px 18px;border-radius:10px;border:0;background:#10b981;color:#09090b;font-weight:600">Retry</button></div></body>';

self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim())
));

self.addEventListener('fetch', e => {
    const req = e.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);
    if (url.origin === location.origin) {
        if (url.pathname.startsWith('/api/')) return;            // API: never cached
        if (req.mode === 'navigate') {                            // pages: network first, offline fallback
            e.respondWith(fetch(req).catch(() => new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html' } })));
        }
        return;
    }
    // CDN assets (fonts / icons / libs): stale-while-revalidate
    e.respondWith(caches.open(VERSION).then(cache => cache.match(req).then(hit => {
        const net = fetch(req).then(res => { if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone()); return res; }).catch(() => hit);
        return hit || net;
    })));
});
'''


@app.route('/icon.svg')
def pwa_icon():
    return Response(ICON_SVG, mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})


@app.route('/icon-maskable.svg')
def pwa_icon_maskable():
    return Response(ICON_MASKABLE_SVG, mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})


@app.route('/manifest.webmanifest')
def pwa_manifest():
    manifest = {
        "name": "Kaeru", "short_name": "Kaeru",
        "description": "Kaeru - personal workspace. Personal use only.",
        "start_url": "/tasks", "scope": "/", "display": "standalone",
        "background_color": "#09090b", "theme_color": "#09090b",
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": "/icon-maskable.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"}
        ]
    }
    return Response(json.dumps(manifest), mimetype='application/manifest+json')


@app.route('/sw.js')
def pwa_sw():
    return Response(SW_JS.replace('__VERSION__', APP_VERSION), mimetype='application/javascript',
                    headers={'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/'})


init_db()

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', debug=True, port=5000)