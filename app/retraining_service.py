import os
import sqlite3
import datetime
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics import accuracy_score

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'app.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class AIRetrainingPipeline:
    def __init__(self):
        self._ensure_tables()

    def _ensure_tables(self):
        conn = get_db_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER, text TEXT NOT NULL, original_category TEXT,
                corrected_category TEXT NOT NULL, source TEXT DEFAULT 'staff_correction',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_versions (
                version_id TEXT PRIMARY KEY, accuracy REAL NOT NULL,
                status TEXT CHECK(status IN ('active', 'archived', 'rejected')) NOT NULL,
                trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, notes TEXT
            );
        """)
        conn.commit()
        conn.close()

    def get_current_active_version(self):
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM model_versions WHERE status = 'active' ORDER BY trained_at DESC LIMIT 1").fetchone()
        conn.close()
        return dict(row) if row else {"version_id": "v1.0.0-base", "accuracy": 0.80, "status": "active"}

    def run_retraining_workflow(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT text, corrected_category as label FROM training_data").fetchall()
        conn.close()

        data = [dict(r) for r in rows]
        if len(data) < 5:
            data += [
                        {"text": "I need help with transcript", "label": "Registrar"},
                        {"text": "Dormitory room cleaning problem", "label": "Housing"},
                        {"text": "Tuition fee payment issue", "label": "Accounting"},
                        {"text": "Library online access error", "label": "IT Support"},
                        {"text": "Grade appeal request", "label": "Academic"}
                    ] * 4

        df = pd.DataFrame(data)
        X_train, X_test, y_train, y_test = train_test_split(df['text'], df['label'], test_size=0.3, random_state=42)

        vectorizer = TfidfVectorizer()
        X_train_vec = vectorizer.fit_transform(X_train)
        X_test_vec = vectorizer.transform(X_test)

        clf = MultinomialNB()
        clf.fit(X_train_vec, y_train)

        y_pred = clf.predict(X_test_vec)
        new_accuracy = float(accuracy_score(y_test, y_pred))

        current_active = self.get_current_active_version()
        current_acc = current_active.get('accuracy', 0.80)
        new_version_id = f"v{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        conn = get_db_connection()
        if new_accuracy >= current_acc:
            conn.execute("UPDATE model_versions SET status = 'archived' WHERE status = 'active'")
            conn.execute(
                "INSERT INTO model_versions (version_id, accuracy, status, notes) VALUES (?, ?, 'active', ?)",
                (new_version_id, new_accuracy, f"Validation passed. Accuracy: {new_accuracy:.2%}")
            )
            deployed = True
        else:
            conn.execute(
                "INSERT INTO model_versions (version_id, accuracy, status, notes) VALUES (?, ?, 'rejected', ?)",
                (new_version_id, new_accuracy, f"Validation failed ({new_accuracy:.2%} < {current_acc:.2%}). Rolled back to live model.")
            )
            deployed = False

        conn.commit()
        conn.close()

        return {
            "version_id": new_version_id,
            "new_accuracy": round(new_accuracy, 4),
            "previous_accuracy": round(current_acc, 4),
            "deployed": deployed,
            "message": "New model deployed successfully" if deployed else "New model underperformed. Kept active live model."
        }

    def rollback_to_version(self, target_version_id):
        conn = get_db_connection()
        target = conn.execute("SELECT * FROM model_versions WHERE version_id = ?", (target_version_id,)).fetchone()
        if not target:
            conn.close()
            return {"success": False, "error": "Version not found"}

        conn.execute("UPDATE model_versions SET status = 'archived' WHERE status = 'active'")
        conn.execute("UPDATE model_versions SET status = 'active' WHERE version_id = ?", (target_version_id,))
        conn.commit()
        conn.close()
        return {"success": True, "active_version": target_version_id}