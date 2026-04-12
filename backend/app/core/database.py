from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Base = declarative_base()

# 🔥 IMPORTANTE: importar modelos DESPUÉS de Base
from app.models import (
    user,
    user_profile,
    user_role,
    refresh_token,
    song,
    song_featured_artist,
    song_credit_entry,
    song_media_asset,
    ingestion_lock,
    listening_event,
    listening_session,
    listening_session_checkpoint,
    listening_aggregate,
    user_balance,
    artist,
    song_artist_split,
    global_listening_aggregate,
    payout_batch,
    payout_line,
    payout_input_snapshot,
    snapshot_user_pool,
    snapshot_listening_input,
    payout_settlement,
)