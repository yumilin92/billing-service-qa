"""
Database setup (SQLAlchemy 2.0 style).

We use SQLite — a whole database in a single local file (billing.db),
zero configuration. Perfect for a demo. In Phase 2 the tests will point
this same code at a *fresh throwaway database* so they never read or
corrupt your dev data. That isolation ("each test starts clean") is a
core testing skill we want to show off.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# sqlite:///./billing.db  ->  a file called billing.db in the project folder.
SQLALCHEMY_DATABASE_URL = "sqlite:///./billing.db"

# `check_same_thread=False`: SQLite by default refuses to be used from more
# than one thread; FastAPI serves requests on several threads, so we allow it.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# A "session" is one conversation with the database. SessionLocal() makes one.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Every ORM table model (in models.py) inherits from this."""
    pass


def get_db():
    """FastAPI *dependency*: give each request its own DB session, and always
    close it afterwards — even if the request errors.

    `yield` (not `return`) makes this a generator: FastAPI runs the code up to
    yield before the request, hands the session to the route, then runs the
    `finally` block after. Tests will override this function to inject a test
    database instead of billing.db.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
