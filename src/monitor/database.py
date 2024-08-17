from os import environ

from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine

from dotenv import load_dotenv
load_dotenv()

# database connection common to all threads
common_engine = create_engine("postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % {
    "user": environ["DB_USER"],
    "pw": environ["DB_PASSWORD"],
    "db": environ["DB_SCHEMA"],
    "host": environ["DB_HOST"],
    "port": environ["DB_PORT"],
})


def get_database_session(new_connection=False):
    if new_connection:
        # create a new connection
        # for multiprocessing
        engine = create_engine("postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % {
            "user": environ["DB_USER"],
            "pw": environ["DB_PASSWORD"],
            "db": environ["DB_SCHEMA"],
            "host": environ["DB_HOST"],
            "port": environ["DB_PORT"],
        })
    else:
        engine = common_engine

    session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)
    return session()
