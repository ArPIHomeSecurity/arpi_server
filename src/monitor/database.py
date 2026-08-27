import logging
from contextlib import contextmanager
from os import environ

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

engine = None
logger = logging.getLogger("database")


def get_database_session():
    DB_HOST = environ.get("DB_HOST", "/var/run/postgresql")

    # database connection common to all threads
    db_user = environ.get("DB_USER")
    if db_user:
        url = f"postgresql://{db_user}@/{environ['DB_SCHEMA']}?host={DB_HOST}"
    else:
        url = f"postgresql:///{environ['DB_SCHEMA']}?host={DB_HOST}"

    global engine
    logger.debug("Creating new database connection: %s", url)
    if engine is None:
        engine = create_engine(url)

    session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)()
    return session


@contextmanager
def create_database_session():
    DB_HOST = environ.get("DB_HOST", "/var/run/postgresql")

    # database connection common to all threads
    db_user = environ.get("DB_USER")
    if db_user:
        url = f"postgresql://{db_user}@/{environ['DB_SCHEMA']}?host={DB_HOST}"
    else:
        url = f"postgresql:///{environ['DB_SCHEMA']}?host={DB_HOST}"

    global engine
    logger.debug("Creating new database connection: %s", url)
    if engine is None:
        engine = create_engine(url)

    session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)()
    try:
        yield session
    finally:
        session.close()
