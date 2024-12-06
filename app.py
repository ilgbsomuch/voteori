from flask import Flask, render_template, request, jsonify, session
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
app.config['DEBUG'] = os.getenv('DEBUG', False)

# Ensure the data directory exists
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE = os.path.join(DATA_DIR, 'votes.db')

# Database helper functions
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Create table for vote count
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upvotes INTEGER DEFAULT 0,
                downvotes INTEGER DEFAULT 0
            )
        ''')
        # Create table for user votes (session-based, no need for IP-based now)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                vote_time TIMESTAMP
            )
        ''')
        # Insert initial vote count if table is empty
        cursor.execute('SELECT COUNT(*) FROM votes')
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO votes (upvotes, downvotes) VALUES (0, 0)')
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Helper to get current vote counts
def get_vote_counts():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT upvotes, downvotes FROM votes LIMIT 1')
    return cursor.fetchone()

# Helper to check if user can vote
def can_vote(session_id):
    db = get_db()
    cursor = db.cursor()
    today = datetime.now().date()
    start_of_today = datetime.combine(today, datetime.min.time())
    cursor.execute(
        'SELECT COUNT(*) FROM user_votes WHERE session_id = ? AND vote_time >= ?',
        (session_id, start_of_today)
    )
    vote_count = cursor.fetchone()[0]
    return vote_count < 3

# Route for the homepage
@app.route('/')
def index():
    upvotes, downvotes = get_vote_counts()
    return render_template('index.html', upvotes=upvotes, downvotes=downvotes)

# Route to handle voting
@app.route('/vote', methods=['POST'])
def vote():
    session_id = session.get('session_id')  # Retrieve session ID (auto handled by Flask)
    
    if not session_id:
        session_id = str(datetime.now().timestamp())  # Generate a new session ID
        session['session_id'] = session_id

    if not can_vote(session_id):
        return jsonify({'error': 'You can only vote 3 times per day.'}), 403

    vote_type = request.json.get('vote_type')
    if vote_type not in ['upvote', 'downvote']:
        return jsonify({'error': 'Invalid vote type.'}), 400

    db = get_db()
    cursor = db.cursor()
    if vote_type == 'upvote':
        cursor.execute('UPDATE votes SET upvotes = upvotes + 1')
    elif vote_type == 'downvote':
        cursor.execute('UPDATE votes SET downvotes = downvotes + 1')
    cursor.execute('INSERT INTO user_votes (session_id, vote_time) VALUES (?, ?)',
                   (session_id, datetime.now()))
    db.commit()
    upvotes, downvotes = get_vote_counts()
    return jsonify({'upvotes': upvotes, 'downvotes': downvotes})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
