from os import environ

from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine

from dotenv import load_dotenv
load_dotenv()

engine = create_engine("postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % {
    "user": environ["DB_USER"],
    "pw": environ["DB_PASSWORD"],
    "db": environ["DB_SCHEMA"],
    "host": environ["DB_HOST"],
    "port": environ["DB_PORT"],
})

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
