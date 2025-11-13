import logging
from os import environ

from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine



# database connection common to all threads
db_user = environ.get("DB_USER")
if db_user:
    url = f"postgresql://{db_user}@/{environ['DB_SCHEMA']}"
else:
    url = f"postgresql:///{environ['DB_SCHEMA']}"

common_engine = create_engine(url)


def get_database_session(new_connection=False):
    logging.debug("Creating new database connection: %s", url)
    if new_connection:
        # create a new connection
        # for multiprocessing
        engine = create_engine(url)
    else:
        engine = common_engine

    session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)
    return session()
