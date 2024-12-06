from flask import Flask, render_template, request, jsonify, session, g
import sqlite3
from datetime import datetime
import os
import logging

# Flask setup
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
app.config['DEBUG'] = os.getenv('DEBUG', 'False') == 'True'  # Ensure Debug is False in production
app.config['DATABASE'] = os.getenv('DATABASE', 'data/votes.db')

# Set up logging for production
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the data directory exists
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE = os.path.join(DATA_DIR, 'votes.db')

# Database helper functions
def get_db():
    """Return a database connection."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def init_db():
    """Initialize the database and create tables if necessary."""
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

        # Create table for user votes (session-based)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                vote_time TIMESTAMP
            )
        ''')

        # Check if the session_id column exists, and add it if missing
        cursor.execute("PRAGMA table_info(user_votes);")
        columns = cursor.fetchall()
        if not any(column[1] == "session_id" for column in columns):
            cursor.execute('ALTER TABLE user_votes ADD COLUMN session_id TEXT')

        # Insert initial vote count if table is empty
        cursor.execute('SELECT COUNT(*) FROM votes')
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO votes (upvotes, downvotes) VALUES (0, 0)')
        db.commit()

@app.teardown_appcontext
def close_connection(exception):
    """Close the database connection after each request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Helper to get current vote counts
def get_vote_counts():
    """Fetch the current vote counts from the database."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('SELECT upvotes, downvotes FROM votes LIMIT 1')
        result = cursor.fetchone()
        if result:
            return result
        else:
            logger.error("No vote data found in the 'votes' table.")
            return (0, 0)  # Return default values if no data found
    except Exception as e:
        logger.error(f"Error fetching vote counts: {e}", exc_info=True)
        return (0, 0)  # Return default values on error

# Helper to check if the user can vote (max 3 votes per day)
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
    """Render the homepage with the current vote counts."""
    try:
        upvotes, downvotes = get_vote_counts()
        return render_template('index.html', upvotes=upvotes, downvotes=downvotes)
    except Exception as e:
        logger.error(f"Error loading homepage: {e}", exc_info=True)
        return jsonify({'error': 'Failed to load vote counts.'}), 500

# Route to handle voting
@app.route('/vote', methods=['POST'])
def vote():
    """Handle the vote submission."""
    try:
        session_id = session.get('session_id')  # Retrieve session ID (auto handled by Flask)
        
        if not session_id:
            session_id = str(datetime.now().timestamp())  # Generate a new session ID if not set
            session['session_id'] = session_id  # Save session ID in session

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
    
    except Exception as e:
        # Log the error for debugging purposes
        logger.error(f"Error during voting: {e}", exc_info=True)
        return jsonify({'error': 'An error occurred during voting.'}), 500

if __name__ == '__main__':
    # Ensure the database is initialized when the app starts
    if not os.path.exists(DATABASE):
        logger.info("Database not found, initializing...")
        init_db()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
