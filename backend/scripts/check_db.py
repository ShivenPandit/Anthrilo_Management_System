"""Quick DB diagnostic script."""
import sys
sys.path.insert(0, ".")

from app.db.session import SessionLocal
from sqlalchemy import text, func

db = SessionLocal()
try:
    # Tables
    rows = db.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )).fetchall()
    print("=== Tables in DB ===")
    for r in rows:
        print(f"  {r[0]}")

    # Sales order record count and date range
    try:
        from app.db.export_models import SalesOrderRecord
        count = db.query(func.count(SalesOrderRecord.id)).scalar()
        min_date = db.query(func.min(SalesOrderRecord.order_date)).scalar()
        max_date = db.query(func.max(SalesOrderRecord.order_date)).scalar()
        print(f"\n=== SalesOrderRecord: {count} rows ===")
        print(f"  Date range: {min_date}  ->  {max_date}")
    except Exception as e:
        print(f"  SalesOrderRecord error: {e}")

    # SyncLog recent entries
    try:
        from app.db.export_models import SyncLog
        logs = db.query(SyncLog).order_by(SyncLog.id.desc()).limit(8).all()
        print("\n=== Last 8 SyncLog entries ===")
        for l in logs:
            print(f"  id={l.id} entity={l.entity} status={l.status} "
                  f"started={l.started_at} completed={l.completed_at}")
    except Exception as e:
        print(f"  SyncLog error: {e}")

    # Check sync_state table
    try:
        from app.db.sync_models import SyncState
        states = db.query(SyncState).all()
        print("\n=== sync_state rows ===")
        for s in states:
            print(f"  {s.entity}: status={s.sync_status} last_sync={s.last_successful_sync}")
    except Exception as e:
        print(f"  sync_state error: {e}")

finally:
    db.close()
