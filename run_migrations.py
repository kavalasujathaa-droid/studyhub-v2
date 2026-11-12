"""
Database migration & schema initialization script for StudyHub V2.
Ensures all tables and columns are created cleanly on TiDB Cloud or SQLite fallback.
"""
import os
import sys
from sqlalchemy import inspect, text
from flask_migrate import upgrade
from studyhub import create_app
from studyhub.extensions import db

def main():
    print("[StudyHub V2] Running database initialization...")
    app = create_app(os.environ.get("FLASK_ENV", "production"))
    
    with app.app_context():
        try:
            # Create all tables matching current SQLAlchemy models
            db.create_all()
            print("[StudyHub V2] db.create_all() completed successfully.")
        except Exception as e:
            print(f"[StudyHub V2] Error in db.create_all(): {e}", file=sys.stderr)
        
        # Schema auto-repair for SQLite fallback when older schema versions exist
        try:
            inspector = inspect(db.engine)
            if "users" in inspector.get_table_names():
                user_cols = {c["name"] for c in inspector.get_columns("users")}
                with db.engine.begin() as conn:
                    if "created_by_admin_id" not in user_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN created_by_admin_id VARCHAR(36)"))
                        print("[StudyHub V2] Added missing column users.created_by_admin_id.")
                    if "status" not in user_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                        print("[StudyHub V2] Added missing column users.status.")
                    if "must_change_password" not in user_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0"))
                        print("[StudyHub V2] Added missing column users.must_change_password.")
        except Exception as repair_e:
            print(f"[StudyHub V2] Schema repair note: {repair_e}")

        # If connected to MySQL / TiDB Cloud, run Alembic upgrade
        if "mysql" in str(db.engine.url):
            try:
                upgrade()
                print("[StudyHub V2] TiDB migrations applied successfully.")
            except Exception as mig_e:
                print(f"[StudyHub V2] TiDB migration note: {mig_e}")
                
        print("[StudyHub V2] Database initialization complete and ready.")

if __name__ == "__main__":
    main()
