"""
Edu Tutor AI: Personalized Learning with Generative AI and LMS Integration
Single-file Flask application prototype.

Features:
- User profiles (SQLite)
- Lesson generation (uses OpenAI if API key present, otherwise uses a local template)
- Quiz creation and taking (store attempts, scores)
- Simulated LMS sync (prints payload or writes to a file)
- Export progress as CSV

Run:
    pip install flask requests openai
    export OPENAI_API_KEY=sk-...
    python Edu_Tutor_AI.py

Open http://127.0.0.1:5000

This is a minimal prototype meant for demonstration and extension.
"""

from flask import Flask, g, render_template_string, request, redirect, url_for, send_file, flash
import sqlite3
import os
import csv
import io
import json
from datetime import datetime

# Optional OpenAI integration: if openai is installed and OPENAI_API_KEY is set, we'll use it
USE_OPENAI = False
try:
    import openai
    if os.environ.get('OPENAI_API_KEY'):
        openai.api_key = os.environ.get('OPENAI_API_KEY')
        USE_OPENAI = True
except Exception:
    USE_OPENAI = False

DB_PATH = 'edu_tutor_ai.db'

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret')

# --- Database helpers ---

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY,
        title TEXT,
        topic TEXT,
        content TEXT,
        created_by INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY,
        title TEXT,
        lesson_id INTEGER,
        questions TEXT, -- json list of {q, choices, answer}
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        quiz_id INTEGER,
        answers TEXT,
        score REAL,
        taken_at TEXT
    );
    ''')
    db.commit()

# --- Simple Generative Functions ---

def generate_lesson_with_openai(topic):
    prompt = f"Create a concise lesson for learners about: {topic}. Include learning objectives, a short explanation, examples, and 3 quick quiz questions."
    resp = openai.Completion.create(
        model='text-davinci-003',
        prompt=prompt,
        max_tokens=600,
        temperature=0.6
    )
    return resp.choices[0].text.strip()


def generate_lesson_local(topic):
    # Template-based fallback
    title = f"Introduction to {topic.title()}"
    objectives = f"By the end of this lesson, learners will be able to: 1) Understand the basics of {topic}. 2) Apply a simple example. 3) Answer quick quiz questions about core ideas."
    body = (
        f"\nWhat is {topic}?\n"
        f"{topic.capitalize()} is an important topic that involves... (explain the core idea briefly).\n\n"
        "Example:\n"
        f"Consider a simple case of {topic} where... (add a short illustrative example).\n\n"
    )
    quick_quiz = (
        "Quick Quiz Questions:\n1) What is the main idea of the lesson?\n"
        "2) Pick the correct option about a key fact.\n3) True or False: ...\n"
    )
    content = f"{objectives}\n\n{body}\n{quick_quiz}"
    return title, content

# --- LMS Sync Simulation ---

def sync_with_lms_simulation(payload, lms_name='MockLMS'):
    # This function simulates sending data to an LMS. In a real implementation you'd
    # call the LMS API (Moodle, Canvas, Google Classroom). Here we write to a JSON file.
    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    filename = f'lms_sync_{lms_name}_{ts}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filename

# --- Routes ---

HOME_HTML = '''
<!doctype html>
<title>Edu Tutor AI</title>
<h1>Edu Tutor AI: Personalized Learning</h1>
<p>Welcome. Use the links below to manage users, generate lessons, create quizzes, and sync with an LMS.</p>
<ul>
  <li><a href="/users">Users</a></li>
  <li><a href="/lessons">Lessons</a></li>
  <li><a href="/quizzes">Quizzes</a></li>
  <li><a href="/progress/export">Export Progress (CSV)</a></li>
</ul>
'''

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

# Users
USER_LIST_HTML = '''
<h2>Users</h2>
<ul>
{% for u in users %}
  <li>{{u['id']}} - {{u['name']}} ({{u['email']}}) - <a href="/users/{{u['id']}}">Profile</a></li>
{% endfor %}
</ul>
<hr>
<h3>Create User</h3>
<form method="post">
  Name: <input name="name"> Email: <input name="email"> <button type="submit">Create</button>
</form>
<a href="/">Back</a>
'''

@app.route('/users', methods=['GET', 'POST'])
def users():
    db = get_db()
    cur = db.cursor()
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        cur.execute('INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)',
                    (name, email, datetime.utcnow().isoformat()))
        db.commit()
        flash('User created')
        return redirect(url_for('users'))
    cur.execute('SELECT * FROM users')
    users = cur.fetchall()
    return render_template_string(USER_LIST_HTML, users=users)

PROFILE_HTML = '''
<h2>User Profile</h2>
<p>{{user['name']}} ({{user['email']}})</p>
<p>Created: {{user['created_at']}}</p>
<h3>Attempts</h3>
<ul>
{% for a in attempts %}
  <li>Quiz {{a['quiz_id']}} - Score: {{a['score']}} - {{a['taken_at']}}</li>
{% endfor %}
</ul>
<a href="/users">Back</a>
'''

@app.route('/users/<int:user_id>')
def user_profile(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    cur.execute('SELECT * FROM attempts WHERE user_id = ?', (user_id,))
    attempts = cur.fetchall()
    return render_template_string(PROFILE_HTML, user=user, attempts=attempts)

# Lessons
LESSON_LIST_HTML = '''
<h2>Lessons</h2>
<ul>
{% for l in lessons %}
  <li>{{l['id']}} - <a href="/lessons/{{l['id']}}">{{l['title']}}</a> ({{l['topic']}})</li>
{% endfor %}
</ul>
<hr>
<h3>Generate Lesson</h3>
<form method="post">
  Topic: <input name="topic"> Created by (user id): <input name="created_by"> <button type="submit">Generate</button>
</form>
<a href="/">Back</a>
'''

@app.route('/lessons', methods=['GET', 'POST'])
def lessons():
    db = get_db()
    cur = db.cursor()
    if request.method == 'POST':
        topic = request.form.get('topic')
        created_by = request.form.get('created_by') or None
        if USE_OPENAI:
            content = generate_lesson_with_openai(topic)
            title = f"Lesson: {topic.title()}"
        else:
            title, content = generate_lesson_local(topic)
        cur.execute('INSERT INTO lessons (title, topic, content, created_by, created_at) VALUES (?, ?, ?, ?, ?)',
                    (title, topic, content, created_by, datetime.utcnow().isoformat()))
        db.commit()
        flash('Lesson generated')
        return redirect(url_for('lessons'))
    cur.execute('SELECT * FROM lessons ORDER BY id DESC')
    lessons = cur.fetchall()
    return render_template_string(LESSON_LIST_HTML, lessons=lessons)

LESSON_VIEW_HTML = '''
<h2>{{lesson['title']}}</h2>
<p><strong>Topic:</strong> {{lesson['topic']}}</p>
<pre>{{lesson['content']}}</pre>
<hr>
<a href="/lessons">Back</a>
'''

@app.route('/lessons/<int:lesson_id>')
def lesson_view(lesson_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM lessons WHERE id = ?', (lesson_id,))
    lesson = cur.fetchone()
    return render_template_string(LESSON_VIEW_HTML, lesson=lesson)

# Quizzes
QUIZ_LIST_HTML = '''
<h2>Quizzes</h2>
<ul>
{% for q in quizzes %}
  <li>{{q['id']}} - {{q['title']}} (Lesson {{q['lesson_id']}}) - <a href="/quizzes/{{q['id']}}">Take</a></li>
{% endfor %}
</ul>
<hr>
<h3>Create Quiz</h3>
<form method="post">
  Title: <input name="title"> Lesson ID: <input name="lesson_id"> Questions (JSON list): <br>
  <textarea name="questions" rows="6" cols="60">[{"q":"Sample?","choices":["A","B","C","D"],"answer":0}]</textarea>
  <br><button type="submit">Create</button>
</form>
<a href="/">Back</a>
'''

@app.route('/quizzes', methods=['GET', 'POST'])
def quizzes():
    db = get_db()
    cur = db.cursor()
    if request.method == 'POST':
        title = request.form.get('title')
        lesson_id = request.form.get('lesson_id')
        questions = request.form.get('questions')
        cur.execute('INSERT INTO quizzes (title, lesson_id, questions, created_at) VALUES (?, ?, ?, ?)',
                    (title, lesson_id, questions, datetime.utcnow().isoformat()))
        db.commit()
        flash('Quiz created')
        return redirect(url_for('quizzes'))
    cur.execute('SELECT * FROM quizzes ORDER BY id DESC')
    quizzes = cur.fetchall()
    return render_template_string(QUIZ_LIST_HTML, quizzes=quizzes)

QUIZ_TAKE_HTML = '''
<h2>{{quiz['title']}}</h2>
<form method="post">
  <input type="hidden" name="user_id" value="{{user_id}}">
  {% for i, q in enumerate(questions) %}
    <div>
      <p><strong>Q{{i+1}}: {{q['q']}}</strong></p>
      {% for j, c in enumerate(q['choices']) %}
        <label><input type="radio" name="q{{i}}" value="{{j}}"> {{c}}</label><br>
      {% endfor %}
    </div>
  {% endfor %}
  <p>Enter your user id: <input name="user_id"></p>
  <button type="submit">Submit Answers</button>
</form>
<a href="/quizzes">Back</a>
'''

@app.route('/quizzes/<int:quiz_id>', methods=['GET', 'POST'])
def quiz_take(quiz_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM quizzes WHERE id = ?', (quiz_id,))
    quiz = cur.fetchone()
    questions = json.loads(quiz['questions'])
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        answers = []
        correct = 0
        for i, q in enumerate(questions):
            ans = request.form.get(f'q{i}')
            ans_index = int(ans) if ans is not None else None
            answers.append(ans_index)
            if ans_index is not None and ans_index == q.get('answer'):
                correct += 1
        score = round(100.0 * correct / max(1, len(questions)), 2)
        cur.execute('INSERT INTO attempts (user_id, quiz_id, answers, score, taken_at) VALUES (?, ?, ?, ?, ?)',
                    (user_id, quiz_id, json.dumps(answers), score, datetime.utcnow().isoformat()))
        db.commit()
        flash(f'Quiz submitted. Score: {score}%')
        return redirect(url_for('quizzes'))
    return render_template_string(QUIZ_TAKE_HTML, quiz=quiz, questions=questions, user_id='')

# Progress export
@app.route('/progress/export')
def export_progress():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT a.id, u.name, u.email, a.quiz_id, a.score, a.taken_at FROM attempts a JOIN users u ON a.user_id = u.id')
    rows = cur.fetchall()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['attempt_id', 'user_name', 'user_email', 'quiz_id', 'score', 'taken_at'])
    for r in rows:
        writer.writerow([r['id'], r['name'], r['email'], r['quiz_id'], r['score'], r['taken_at']])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='progress.csv')

# LMS sync UI
LMS_HTML = '''
<h2>Sync Lesson/Quiz to LMS (Simulated)</h2>
<form method="post">
  Type: <select name="type"><option value="lesson">Lesson</option><option value="quiz">Quiz</option></select><br>
  ID: <input name="id"> LMS Name: <input name="lms_name" value="MockLMS"><br>
  <button type="submit">Sync</button>
</form>
<p>{{result}}</p>
<a href="/">Back</a>
'''

@app.route('/lms', methods=['GET', 'POST'])
def lms_sync():
    result = ''
    if request.method == 'POST':
        typ = request.form.get('type')
        _id = request.form.get('id')
        lms_name = request.form.get('lms_name') or 'MockLMS'
        db = get_db()
        cur = db.cursor()
        if typ == 'lesson':
            cur.execute('SELECT * FROM lessons WHERE id = ?', (_id,))
            obj = cur.fetchone()
            payload = dict(obj)
        else:
            cur.execute('SELECT * FROM quizzes WHERE id = ?', (_id,))
            obj = cur.fetchone()
            payload = dict(obj)
        payload['synced_at'] = datetime.utcnow().isoformat()
        fname = sync_with_lms_simulation(payload, lms_name=lms_name)
        result = f'Synced to {lms_name}, written to {fname}'
    return render_template_string(LMS_HTML, result=result)

# Initialize DB and run
if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        with app.app_context():
            init_db()
            print('Database initialized at', DB_PATH)
    app.run(debug=True)
