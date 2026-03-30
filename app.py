import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
app.secret_key = "kaeru-dev-secret-2026"
CORS(app)  # As specified in instructions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "kaeru.db")
PASSWORD_FILE = os.path.join(BASE_DIR, "password.txt")

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Tasks table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                due_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Projects table
        

        # First, ensure the table is created (this is safe to run multiple times)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                added_date TEXT
            )
        ''')

        # Then, add the column with a default timestamp (check first to avoid errors)
        cursor = conn.execute("PRAGMA table_info(projects);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'last_updated' not in columns:
            conn.execute('''
                ALTER TABLE projects ADD COLUMN last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            ''')
            conn.commit()   
        
        # Subtasks table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')

        
        # Seed sample data exactly matching the screenshot (March 28, 2026)
        if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            today = "2026-03-28"
            conn.executemany(
                "INSERT INTO tasks (title, completed, due_date) VALUES (?, ?, ?)",
                [
                    ("Code Force Contest 17", 0, today),
                    ("Leet Code Biweekly 233", 0, today),
                    ("Academic Assignment 455", 1, today),
                    ("Real Madrid vs Barcelona 28 March", 0, today),
                    ("SE exam 1st chapter and 2nd chapter", 0, "2026-03-29"),
                    ("System Design Online Class", 0, "2026-03-29"),
                    ("Bus Ticket", 1, "2026-03-29"),
                    ("Mid Term Exam will start", 0, "2026-03-30"),
                ]
            )

        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'Untitled Note',
                content TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Seed projects exactly as in screenshot
        
        
        conn.commit()

def get_password():
    if not os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'w') as f:
            f.write("kaeru2026")  # default access key
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
        return "<h1 style='text-align:center;margin-top:100px;color:red'>Invalid access key</h1>", 401

    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kaeru</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;display=swap');
        body { font-family: 'Inter', system_ui, sans-serif; }
        
        .neon-text {
            text-shadow: 0 0 8px rgb(134 239 172);
        }
        
        .neon-border {
            box-shadow: 0 0 15px -3px rgb(134 239 172);
        }
    </style>
</head>
<body class="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
    <div class="w-full max-w-xs bg-zinc-900 border border-emerald-500/30 rounded-2xl overflow-hidden">
        
        <!-- Top bar - ultra minimal -->
        <div class="px-5 pt-4 pb-1 flex items-center justify-end">
            <a href="https://github.com/Irshad-11/Kaeru" 
               target="_blank"
               class="flex items-center gap-x-1 text-xs font-medium text-emerald-300 hover:text-emerald-400 transition-colors">
                <i class="fa-brands fa-github"></i>
                <span>Repo: Kaeru</span>
            </a>
        </div>

        <!-- Title + Animated Version Badge -->
        <div class="px-5 text-center -mt-1">
            <h1 class="text-3xl font-semibold text-white tracking-tighter">Kaeru</h1>
            
            <!-- Animated Neon Version -->
            <div class="inline-flex items-center gap-x-1 mt-2 px-4 py-1 text-[10px] font-medium bg-zinc-800 border border-emerald-400/40 text-emerald-300 rounded-3xl">
                <div class="flex items-center">
                    <!-- Pulsing green dot -->
                    <span class="relative flex h-2 w-2">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
                    </span>
                </div>
                latest
                <span class="font-semibold text-emerald-100">v4.1.0</span>
            </div>
        </div>

        <div class="px-5 pb-6 pt-8">
            <form method="post" class="space-y-4">
                <!-- Input - dark neon style -->
                <input type="password" 
                       name="key" 
                       placeholder="Access Protected"
                       class="w-full px-3 py-3 text-base bg-zinc-950 border border-emerald-500/30 focus:border-emerald-400 rounded-2xl outline-none text-white text-center font-medium placeholder:text-emerald-300/60">

                <!-- Button - neon glow -->
                <button type="submit"
                        class="w-full bg-emerald-500 hover:bg-emerald-400 transition-all text-zinc-950 text-base font-semibold py-2 rounded-lg flex items-center justify-center gap-x-2 shadow-lg shadow-emerald-500/50">
                    Get Into
                    <i class="fa-solid fa-arrow-right"></i>
                </button>
            </form>
        </div>

        <!-- Footer - minimal neon -->
        <div class="px-5 py-5 border-t border-emerald-500/10 text-center text-xs">
            <p class="text-emerald-300/60 mb-3">By Irshad Hossain</p>
            
            <div class="flex justify-center gap-x-5 text-2xl text-emerald-300/70 mb-4">
                <a href="https://github.com/Irshad-11" target="_blank" class="hover:text-emerald-400 transition-colors">
                    <i class="fa-brands fa-github"></i>
                </a>
                <a href="https://www.linkedin.com/in/irshad-hossain-785548323/" target="_blank" class="hover:text-emerald-400 transition-colors">
                    <i class="fa-brands fa-linkedin"></i>
                </a>
                <a href="https://www.facebook.com/irshad.risad" target="_blank" class="hover:text-emerald-400 transition-colors">
                    <i class="fa-brands fa-facebook"></i>
                </a>
            </div>
            
            <p class="text-emerald-300/50">© 2024 — Personal Use Only</p>
        </div>
    </div>
</body>
</html>
    '''

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    with get_db() as conn:
        # Delete subtasks first (due to foreign key with CASCADE)
        conn.execute("DELETE FROM subtasks WHERE project_id = ?", (project_id,))
        # Then delete the project
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    return jsonify({"success": True})


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

# ====================== API ENDPOINTS ======================

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY due_date ASC, id ASC").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/tasks', methods=['POST'])
def add_task():
    data = request.get_json()
    title = data.get('title')
    due_date = data.get('due_date')
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
    title = data.get('title')
    with get_db() as conn:
        conn.execute("UPDATE tasks SET title = ? WHERE id = ?", (title, task_id))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/projects', methods=['GET'])
def get_projects():
    with get_db() as conn:
        projects = []
        rows = conn.execute("SELECT * FROM projects").fetchall()
        for row in rows:
            p = dict(row)
            subs = conn.execute(
                "SELECT * FROM subtasks WHERE project_id = ? ORDER BY id",
                (p['id'],)
            ).fetchall()
            sub_list = [dict(s) for s in subs]
            completed_count = sum(1 for s in sub_list if s['completed'] == 1)
            total = len(sub_list) or 1
            progress = round((completed_count / total) * 100)
            p['subtasks'] = sub_list
            p['completed_count'] = completed_count
            p['total'] = total
            p['progress'] = progress
            projects.append(p)
        return jsonify(projects)

@app.route('/api/tasks/history', methods=['GET'])
def get_task_history():
    with get_db() as conn:
        # Get completed tasks from last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        rows = conn.execute('''
            SELECT id, title, due_date, completed, 
                   created_at,
                   CURRENT_TIMESTAMP as completed_at
            FROM tasks 
            WHERE completed = 1 
              AND due_date >= ? 
            ORDER BY due_date DESC, id DESC
        ''', (thirty_days_ago,)).fetchall()
        
        return jsonify([dict(row) for row in rows])
    
# Delete subtask
@app.route('/api/subtasks/<int:sub_id>', methods=['DELETE'])
def delete_subtask(sub_id):
    with get_db() as conn:
        conn.execute("DELETE FROM subtasks WHERE id = ?", (sub_id,))
        conn.commit()
    return jsonify({"success": True})

# Edit subtask
@app.route('/api/subtasks/<int:sub_id>', methods=['PUT'])
def edit_subtask(sub_id):
    data = request.get_json()
    title = data.get('title')
    with get_db() as conn:
        conn.execute("UPDATE subtasks SET title = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?", 
                     (title, sub_id))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/projects', methods=['POST'])
def add_project():
    data = request.get_json()
    title = data.get('title')
    added_date = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        conn.execute("INSERT INTO projects (title, added_date) VALUES (?, ?)", (title, added_date))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/projects/<int:project_id>/subtasks', methods=['POST'])
def add_subtask(project_id):
    data = request.get_json()
    title = data.get('title')
    with get_db() as conn:
        conn.execute("INSERT INTO subtasks (project_id, title) VALUES (?, ?)", (project_id, title))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/subtasks/<int:sub_id>/toggle', methods=['POST'])
def toggle_subtask(sub_id):
    with get_db() as conn:
        conn.execute("UPDATE subtasks SET completed = NOT completed WHERE id = ?", (sub_id,))
        conn.commit()
    return jsonify({"success": True})

@app.route('/')
def index():
    return redirect(url_for('tasks'))


# ====================== NOTES API ======================

@app.route('/api/notes', methods=['GET'])
def get_notes():
    with get_db() as conn:
        rows = conn.execute("SELECT id, title, created_at, updated_at FROM notes ORDER BY updated_at DESC").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/notes', methods=['POST'])
def create_note():
    data = request.get_json() or {}
    title = data.get('title', 'Untitled Note')
    with get_db() as conn:
        conn.execute("INSERT INTO notes (title) VALUES (?)", (title,))
        note_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    return jsonify({"id": note_id, "success": True})

@app.route('/api/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({"error": "Note not found"}), 404

@app.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    with get_db() as conn:
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

init_db()

# if __name__ == '__main__':

#     app.run(host='0.0.0.0', debug=True, port=5000)