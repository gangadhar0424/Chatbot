"""Sync SQLAlchemy engine for the web rebuild — separate from app/db.py.

app/db.py (async, Postgres/Neon) is untouched and stays the baseline's store.
This is its own local SQLite file so the two tracks can never collide.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web_dev.db")
_DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
