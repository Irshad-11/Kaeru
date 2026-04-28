

import os
import sqlite3
from datetime import datetime, timedelta

import time
import re
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import requests
import hashlib

FOOTBALL_API_KEY = "e1c859a9b58f4b64ae66a0ec14f07b07"  # Get from https://www.football-data.org/
FOOTBALL_API_BASE = "https://api.football-data.org/v4"


app = Flask(__name__, template_folder="templates")
app.secret_key = "kaeru-dev-secret-2026"
CORS(app)

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


@app.before_request
def check_auth():
    # Allow login page + static files
    if request.path.startswith(('/static', '/login')) or request.path in ['/favicon.ico']:
        return

    # 🔐 Get key from header
    client_key = request.headers.get('X-ACCESS-KEY')

    # ❌ Block everything if key missing or wrong
    if not client_key or client_key != get_password():
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        key = request.form.get('key')

        if key == get_password():
            return jsonify({"success": True})

        return jsonify({"success": False}), 401

    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kaeru — Access</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/?size=100&id=ySZcrXaaOavG&format=png&color=000000">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Sora', sans-serif; }
        .glow { box-shadow: 0 0 20px rgba(16,185,129,0.25); }
        
        @keyframes pulse-border {
            0%, 100% { border-color: rgba(16,185,129,0.3); }
            50% { border-color: rgba(16,185,129,0.7); }
        }
        .pulse-border { animation: pulse-border 2s ease-in-out infinite; }
        
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
        
        .badge-squash {
    /* Hard-edge cartoon shadow - subtle but deep */
    box-shadow: 1.5px 1.5px 0px 0px #000;
    animation: squash-pop 5s infinite;
}

.dot-status {
    animation: dot-color-change 5s infinite;
}

/* 1. The Squash & Stretch Animation */
@keyframes squash-pop {
    0%, 45%, 100% { 
        transform: scale(1, 1); 
        background-color: #450a0a; /* Deep Dark Red */
    }
    47% { 
        transform: scale(1.15, 0.85); /* Squash down */
    }
    50% { 
        transform: scale(0.9, 1.2); /* Stretch up */
        background-color: #064e3b; /* Deep Dark Green */
    }
    53%, 95% { 
        transform: scale(1, 1); 
        background-color: #064e3b;
    }
}

/* 2. The Dot Color - Matches the dark theme */
@keyframes dot-color-change {
    0%, 45%, 100% { 
        background-color: #b91c1c; /* Muted Red */
    }
    50%, 95% { 
        background-color: #059669; /* Muted Green */
    }
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
    </style>
</head>
<body class="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
    <div class="w-full max-w-sm">
        <div class="absolute top-4 right-4">
            <a href="https://github.com/Irshad-11/Kaeru" target="_blank" class="repo-link inline-flex items-center gap-2 text-zinc-400 hover:text-emerald-400 transition-all">
                <i class="fa-brands fa-github text-sm"></i>
                <span class="text-xs">Kaeru</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-xs"></i>
            </a>
        </div>
        
        <div class="text-center mb-8">
            <div class="flex items-center justify-center gap-3">
                <div class="inline-flex items-center justify-center w-14 h-14 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl">
                    <i class="fa-sharp-duotone fa-solid fa-torii-gate text-2xl text-emerald-400"></i>
                </div>
                <div class="text-left">
                    <div class="flex items-center gap-2">
                        <div class="text-container" style="min-width: 100px;">
                            <div id="english-text" class="switching-text">
                                <h1 class="text-3xl font-bold text-emerald-400 tracking-tight whitespace-nowrap" id="english-letters"></h1>
                            </div>
                            <div id="japanese-text" class="switching-text" style="display: none;">
                                <h1 class="text-3xl font-bold text-emerald-400 tracking-tight whitespace-nowrap" id="japanese-letters"></h1>
                            </div>
                        </div>
                        <div class="flex items-center">
    <span class="badge-squash font-mono inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border-2 border-zinc-950 bg-zinc-900 text-[10px] font-black italic tracking-tight">
        <div class="dot-status h-2 w-2 rounded-sm border border-black/40"></div>
        
        <span class="text-white/90">latest - v6.4.0</span>
    </span>
</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 pulse-border">
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
        <p class="text-center text-zinc-700 text-xs mt-4">Irshad Hossain ★ Personal Use Only</p>
    </div>
    
    <script>

    localStorage.removeItem('kaeru_key');
    window.__KAERU_KEY__ = null;



    // Animation Configuration (Your original beautiful animation - unchanged)
    const englishWord = 'Kaeru';
    const japaneseWord = '代える';
    const STAGGER = 60;
    const DURATION = 500;
    const WAIT_TIME = 4000;

    // ====================== SAVE LOGIN FEATURE ======================
    function encodeKey(key) {
        const expire = Date.now() + (24 * 60 * 60 * 1000); // 1 day
        const data = key + "|" + expire;
        return btoa(data.split('').map(c => String.fromCharCode(c.charCodeAt(0) + 5)).join(''));
    }

    function decodeKey(encoded) {
        try {
            const decoded = atob(encoded).split('').map(c => String.fromCharCode(c.charCodeAt(0) - 5)).join('');
            const [key, expire] = decoded.split('|');
            if (Date.now() > parseInt(expire)) {
                localStorage.removeItem('kaeru_key');
                return null;
            }
            return key;
        } catch(e) {
            return null;
        }
    }

    function tryAutoLogin() {
        const saved = localStorage.getItem('kaeru_key');
        if (saved) {
            const key = decodeKey(saved);
            if (key) {
                document.getElementById('access-key').value = key;
                document.getElementById('save-login').checked = true;
                // Auto submit after a small delay
                setTimeout(() => {
                    document.getElementById('login-form').dispatchEvent(new Event('submit'));
                }, 800);
            }
        }
    }

    // ====================== LOGIN HANDLING (Merged) ======================
    const loginForm = document.getElementById('login-form');
    const errorDiv = document.getElementById('error-message');
    const accessInput = document.getElementById('access-key');

    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const key = document.getElementById('access-key').value.trim();
        const saveChecked = document.getElementById('save-login').checked;

        if (!key) return;

        // Save to localStorage if checked
        if (saveChecked) {
            localStorage.setItem('kaeru_key', encodeKey(key));
        } else {
            localStorage.removeItem('kaeru_key');
        }

        const submitBtn = this.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;
        const formBox = document.querySelector('.bg-zinc-900');

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Verifying...';
        errorDiv.classList.remove('visible');

        try {
            await new Promise(r => setTimeout(r, 600));
            
            const formData = new FormData(this);
            const response = await fetch(window.location.href, { 
                method: 'POST', 
                body: formData 
            });
            accessInput.value = '';
            if (response.ok) {
                
                 window.__KAERU_KEY__ = key;

                window.location.href = '/tasks';
            } else {
                errorDiv.classList.add('visible');
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

    async function runCycle() {
        const engDiv = document.getElementById('english-text');
        const japDiv = document.getElementById('japanese-text');
        
        let engSpans = prepareLetters(englishWord, 'english-letters');
        let japSpans = prepareLetters(japaneseWord, 'japanese-letters');

        engDiv.style.display = 'block';
        await animateWord(engSpans, 'letterInLeft');

        while (true) {
            await new Promise(r => setTimeout(r, WAIT_TIME));
            await animateWord(engSpans, 'letterOutRight');
            engDiv.style.display = 'none';

            japDiv.style.display = 'block';
            japSpans.forEach(s => s.style.opacity = '0');
            await animateWord(japSpans, 'letterInLeft');

            await new Promise(r => setTimeout(r, WAIT_TIME));
            await animateWord(japSpans, 'letterOutRight');
            japDiv.style.display = 'none';

            engDiv.style.display = 'block';
            engSpans.forEach(s => s.style.opacity = '0');
            await animateWord(engSpans, 'letterInLeft');
        }
    }

    // Initialize everything
    window.addEventListener('DOMContentLoaded', () => {
        runCycle();
        tryAutoLogin();
    });
</script>
</body>
</html>
'''


@app.route('/logout')
def logout():
    session.clear()
    # Clear saved login
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
            if task['due_date']:
                due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
                task['is_overdue'] = (due_date_obj < today_dhaka) and not task['completed']
            else:
                task['is_overdue'] = False
            tasks.append(task)

        return jsonify({
            "tasks": tasks,
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
    with get_db() as conn:
        conn.execute("INSERT INTO tasks (title, due_date) VALUES (?, ?)", (title, due_date))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    with get_db() as conn:
        conn.execute("UPDATE tasks SET completed = NOT completed WHERE id = ?", (task_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return jsonify({"success": True})


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def edit_task(task_id):
    data = request.get_json()
    title = data.get('title', '').strip()
    due_date = data.get('due_date')
    if not title:
        return jsonify({"error": "Title required"}), 400
    with get_db() as conn:
        if due_date is not None:
            conn.execute("UPDATE tasks SET title = ?, due_date = ? WHERE id = ?", (title, due_date, task_id))
        else:
            conn.execute("UPDATE tasks SET title = ? WHERE id = ?", (title, task_id))
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
            WHERE completed = 1 AND due_date >= ?
            ORDER BY due_date DESC, id DESC
        ''', (thirty_days_ago_dhaka,)).fetchall()
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
                "links": [dict(row) for row in conn.execute("SELECT * FROM links").fetchall()]
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
        query = "SELECT * FROM tasks WHERE (due_date BETWEEN ? AND ?) OR (recurring_type IS NOT NULL AND recurring_paused = 0)"
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
            updates.append("completed = ?")
            params.append(data['completed'])
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
        conn.execute("UPDATE tasks SET completed = ? WHERE id = ?", (completed, task_id))
        conn.commit()
    
    return jsonify({"success": True})


@app.route('/api/planner/tasks/<int:task_id>/recurring', methods=['PUT'])
def toggle_planner_recurring(task_id):
    """Pause or resume recurring task"""
    data = request.get_json()
    paused = data.get('recurring_paused', 0)
    
    with get_db() as conn:
        conn.execute("UPDATE tasks SET recurring_paused = ? WHERE id = ?", (paused, task_id))
        conn.commit()
    
    return jsonify({"success": True})








init_db()

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', debug=True, port=5000)
