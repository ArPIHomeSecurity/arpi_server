from os import environ

from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine

engine = create_engine("postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % {
    "user": environ.get("DB_USER", None),
    "pw": environ.get("DB_PASSWORD", None),
    "db": environ.get("DB_SCHEMA", None),
    "host": environ.get("DB_HOST", None),
    "port": environ.get("DB_PORT", None),
})

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
