""" 
Appriciateable Things you have developed . But there are some technical improvement need here . Follow the instruction below

What you will do Now .
- in Tasks Section : I could not add tasks that i will do in next few days or task later. So you will Add a date picker to the Tasks section so users can assign future dates; display tasks grouped as Today and Tomorrow explicitly, while all later-dated tasks fall under “Upcoming Tasks,” where each date appears as a compact rounded rectangle (month in short form like Jan, Feb) aligned along a vertical timeline, with corresponding tasks shown to the right in a clean, structured layout.
- In Tasks Tab: Enable responsive behavior so that on mobile screens the Projects and Tasks sections stack vertically instead of side-by-side; additionally, make both sections independently collapsible/expandable with smooth animations using a CDN-hosted animation library, allowing users to hide Tasks for a cleaner Project view and hide Projects for a cleaner Tasks view.
- In Task Tab: enable inline editing of project names; enhance each project with metadata fields (Created At, Last Updated) and a smoothly animated circular completion progress indicator (visual only, no percentage text), and implement animated expand/collapse behavior for projects.
- In Note Tab: restructure and redesign the way you render the formatted text area . the Coloring - Bullet Item aren't working . the current rich text editor is functionally broken—color changes reset the cursor position, bullet lists fail to render despite spacing, and formatting is unreliable—so redesign the editor architecture to properly handle styled text; implement stable cursor behavior, working bullet/ordered lists, and a hyperlink insertion flow that prompts for display text and URL, rendering clickable links that open in a new tab.
- In Timeless tab . design a scalable timeline system that efficiently handles 1000+ nodes (using virtualization), with a centered vertical timeline on desktop where years (large Hijri date with muted Gregorian date) appear on the left and truncated node titles on the right; clicking a node shifts the timeline aside and opens a detailed panel on the right, while on mobile it opens a dismissible overlay (tap outside or close icon); enable smooth bidirectional scrolling, full-text search with results shown as “Hijri Date – Title – Tags” that navigate to nodes, tag-based filtering with a clear reset option, and a node creation system with fields for Title, Tags (with duplicate prevention suggestions), Description (rich text with clickable hyperlinks using display text + URL opening in new tabs), either Hijri or Gregorian year input (auto-converted and stored as both), and multiple source links rendered as a clickable list.
- On mobile screens, ensure the UI includes accessible controls for Dark/Light mode toggle, Task History, and Logout, displayed in a clear and reachable layout (e.g., top bar or menu drawer) without disrupting the primary workflow.

Follow Current Code and Modify this Code where Needed as my requirement . 

What you must NOT do:

Do not overhaul or replace the existing UI/UX architecture; preserve at least 90% of the current structure, layout hierarchy, and interaction patterns.
Do not introduce new design systems, component libraries, or styling paradigms that conflict with the current implementation.
Do not break or refactor stable, already-working features unless strictly necessary for the requested changes.
Do not compromise performance, responsiveness, or existing data flow while implementing new features.
Do not add unnecessary complexity, over-engineering, or redundant abstractions.
Do not alter core user workflows or navigation logic beyond the explicitly defined requirements.
Ensure all enhancements are incremental, backward-compatible, and seamlessly integrated into the current system.

Final Deliverable:

- Provide the complete templates/index.html with all specified requirements fully implemented, without deviating from the existing UI structure.
- Provide the complete app.py with all backend logic updated to support the new features and behaviors.
- Ensure the implementation strictly uses the following configuration and does not alter it:
app = Flask(__name__, template_folder="templates")
app.secret_key = "kaeru-dev-secret-2026"
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "kaeru.db")
PASSWORD_FILE = os.path.join(BASE_DIR, "password.txt")



"""
import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
app.secret_key = "kaeru-dev-secret-2026"
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "kaeru.db")
PASSWORD_FILE = os.path.join(BASE_DIR, "password.txt")


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
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
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

        # Seed tasks if empty
        if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
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
    if request.path.startswith(('/static', '/login')) or request.path in ['/favicon.ico']:
        return
    if 'authenticated' not in session:
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        key = request.form.get('key')
        if key == get_password():
            session['authenticated'] = True
            return redirect(url_for('tasks'))
        return "<h1 style='text-align:center;margin-top:100px;color:#ef4444'>Invalid access key</h1>", 401

    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kaeru — Access</title>
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
    </style>
</head>
<body class="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
    <div class="w-full max-w-sm">
        <div class="text-center mb-8">
            <div class="inline-flex items-center justify-center w-14 h-14 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl mb-4">
                <i class="fa-solid fa-frog text-2xl text-emerald-400"></i>
            </div>
            <h1 class="text-2xl font-bold text-white tracking-tight">Kaeru</h1>
            <p class="text-zinc-500 text-sm mt-1">Personal productivity workspace</p>
        </div>
        <div class="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 pulse-border">
            <form method="post" class="space-y-4">
                <div>
                    <label class="text-xs font-medium text-zinc-400 uppercase tracking-wider">Access Key</label>
                    <input type="password" name="key" autofocus
                           placeholder="Enter your access key"
                           class="mt-2 w-full px-4 py-3 bg-zinc-950 border border-zinc-700 focus:border-emerald-500 rounded-xl outline-none text-white text-sm placeholder:text-zinc-600 transition-colors">
                </div>
                <button type="submit"
                        class="w-full bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-semibold py-3 rounded-xl transition-all active:scale-95 glow">
                    Enter Workspace <i class="fa-solid fa-arrow-right ml-2"></i>
                </button>
            </form>
        </div>
        <div class="text-center mt-6 flex justify-center gap-5 text-zinc-600">
            <a href="https://github.com/Irshad-11" target="_blank" class="hover:text-zinc-400 transition-colors"><i class="fa-brands fa-github text-xl"></i></a>
            <a href="https://www.linkedin.com/in/irshad-hossain-785548323/" target="_blank" class="hover:text-zinc-400 transition-colors"><i class="fa-brands fa-linkedin text-xl"></i></a>
            <a href="https://www.facebook.com/irshad.risad" target="_blank" class="hover:text-zinc-400 transition-colors"><i class="fa-brands fa-facebook text-xl"></i></a>
        </div>
        <p class="text-center text-zinc-700 text-xs mt-4">By Irshad Hossain · Personal Use Only</p>
    </div>
</body>
</html>
    '''


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


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


# ====================== TASKS API ======================

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY due_date ASC, id ASC").fetchall()
        return jsonify([dict(row) for row in rows])


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
    with get_db() as conn:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        rows = conn.execute('''
            SELECT id, title, due_date, completed, created_at
            FROM tasks
            WHERE completed = 1 AND due_date >= ?
            ORDER BY due_date DESC, id DESC
        ''', (thirty_days_ago,)).fetchall()
        return jsonify([dict(row) for row in rows])


# ====================== PROJECTS API ======================

@app.route('/api/projects', methods=['GET'])
def get_projects():
    with get_db() as conn:
        projects = []
        rows = conn.execute("SELECT * FROM projects ORDER BY id ASC").fetchall()
        for row in rows:
            p = dict(row)
            subs = conn.execute(
                "SELECT * FROM subtasks WHERE project_id = ? ORDER BY id", (p['id'],)
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


@app.route('/api/projects', methods=['POST'])
def add_project():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    added_date = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        conn.execute("INSERT INTO projects (title, added_date) VALUES (?, ?)", (title, added_date))
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
        conn.execute("UPDATE subtasks SET completed = NOT completed WHERE id = ?", (sub_id,))
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
        conn.execute("DELETE FROM subtasks WHERE id = ?", (sub_id,))
        if row:
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
            "SELECT * FROM timeless_nodes ORDER BY hijri_year ASC, id ASC"
        ).fetchall()
        result = []
        for node in nodes:
            n = dict(node)
            sources = conn.execute(
                "SELECT * FROM timeless_sources WHERE node_id = ? ORDER BY id", (n['id'],)
            ).fetchall()
            n['sources'] = [dict(s) for s in sources]
            # Parse tags
            if n.get('tags'):
                n['tags_list'] = [t.strip() for t in n['tags'].split(',') if t.strip()]
            else:
                n['tags_list'] = []
            result.append(n)
        return jsonify(result)


@app.route('/api/timeless', methods=['POST'])
def add_timeless():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    description = data.get('description', '')
    gregorian_year = data.get('gregorian_year')
    hijri_year = data.get('hijri_year')
    sidenote = data.get('sidenote', '')
    sources = data.get('sources', [])
    tags = data.get('tags', '')

    if gregorian_year and not hijri_year:
        hijri_year = gregorian_to_hijri_year(int(gregorian_year))
    elif hijri_year and not gregorian_year:
        gregorian_year = hijri_to_gregorian_year(int(hijri_year))

    with get_db() as conn:
        conn.execute(
            "INSERT INTO timeless_nodes (title, description, gregorian_year, hijri_year, sidenote, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, gregorian_year, hijri_year, sidenote, tags)
        )
        node_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
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
    title = data.get('title', '').strip()
    description = data.get('description', '')
    gregorian_year = data.get('gregorian_year')
    hijri_year = data.get('hijri_year')
    sidenote = data.get('sidenote', '')
    sources = data.get('sources', [])
    tags = data.get('tags', '')

    if gregorian_year and not hijri_year:
        hijri_year = gregorian_to_hijri_year(int(gregorian_year))
    elif hijri_year and not gregorian_year:
        gregorian_year = hijri_to_gregorian_year(int(hijri_year))

    with get_db() as conn:
        conn.execute(
            "UPDATE timeless_nodes SET title=?, description=?, gregorian_year=?, hijri_year=?, sidenote=?, tags=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
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


# ====================== YEAR CONVERSION HELPERS ======================

def gregorian_to_hijri_year(g_year):
    """Approximate Gregorian year to Hijri year conversion."""
    return round((g_year - 622) * (33 / 32))


def hijri_to_gregorian_year(h_year):
    """Approximate Hijri year to Gregorian year conversion."""
    return round(h_year * (32 / 33) + 622)


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)