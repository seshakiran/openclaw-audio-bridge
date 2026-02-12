import sqlite3
import os

class FillerManager:
    def __init__(self):
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "filler.db")
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                text TEXT NOT NULL
            )
        ''')
        
        # Check if empty and seed
        cursor.execute('SELECT COUNT(*) FROM items')
        if cursor.fetchone()[0] == 0:
            # Seed Jokes
            jokes = [
                ("joke", "I'm afraid for the calendar. Its days are numbered."),
                ("joke", "Why do fathers take an extra pair of socks when they go golfing? In case they get a hole in one!"),
                ("joke", "What do you call a factory that makes okay products? A satisfactory."),
                ("joke", "I'm reading a book on anti-gravity. It's impossible to put down!"),
                ("joke", "What do you call a fake noodle? An impasta.")
            ]
            # Seed Small Talk / Questions
            small_talk = [
                ("chat", "So, how's your day going so far? Busy as usual?"),
                ("chat", "I was just thinking about how much technology has changed recently. It's wild, isn't it?"),
                ("chat", "You working on anything exciting today besides this?"),
                ("chat", "I'm always impressed by how OpenClaw handles these tasks. It's like watching a digital brain work."),
                ("chat", "By the way, did you see anything interesting in the news today?"),
                ("chat", "Sometimes I wish I had a physical claw so I could actually help you clean up the office."),
                ("chat", "I'm just over here crunching numbers while you relax. Living the dream, right?"),
                ("chat", "You know, being an AI assistant is pretty great, except I can't actually drink coffee.")
            ]
            cursor.executemany('INSERT INTO items (category, text) VALUES (?, ?)', jokes + small_talk)
            conn.commit()
        conn.close()

    def get_filler(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT text FROM items ORDER BY RANDOM() LIMIT 1')
        item = cursor.fetchone()
        conn.close()
        return item[0] if item else "I'm still thinking..."

filler = FillerManager()
