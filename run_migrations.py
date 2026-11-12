"""
Database migration & schema initialization script for StudyHub V2 on Render Free.
Runs Alembic migrations against TiDB Cloud before Gunicorn starts.
"""
import os
import sys
from flask_migrate import upgrade
from studyhub import create_app
from studyhub.extensions import db

def main():
    print("[StudyHub V2] Running database migration against TiDB Cloud...")
    app = create_app(os.environ.get("FLASK_ENV", "production"))
    
    with app.app_context():
        try:
            # Run alembic migrations
            upgrade()
            print("[StudyHub V2] Database migrations applied successfully.")
        except Exception as e:
            print(f"[StudyHub V2] Migration note: {e}", file=sys.stderr)
            # Fallback to direct schema sync if migration repo state differs
            try:
                db.create_all()
                print("[StudyHub V2] Tables confirmed via db.create_all().")
            except Exception as inner_e:
                print(f"[StudyHub V2] Fatal database connection error: {inner_e}", file=sys.stderr)
                sys.exit(1)

if __name__ == "__main__":
    main()
