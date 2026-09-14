"""Connexion à la base de données.

En production (Railway), DATABASE_URL pointe vers Postgres.
En local, à défaut, un fichier SQLite est créé dans le répertoire courant.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

RAW_URL = os.getenv("DATABASE_URL", "sqlite:///./dexter_suivi.db")

# Railway expose encore parfois le préfixe historique postgres://
if RAW_URL.startswith("postgres://"):
    RAW_URL = RAW_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif RAW_URL.startswith("postgresql://"):
    RAW_URL = RAW_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

DATABASE_URL = RAW_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
