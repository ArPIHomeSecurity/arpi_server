from flask_sqlalchemy import SQLAlchemy

from utils.models import metadata

db = SQLAlchemy(metadata=metadata)
