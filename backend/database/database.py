import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

load_dotenv(".env.local")

# Get database URL from environment variable, with fallback
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dialogue_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    try:
        from database.models import User
        from sqlalchemy import text
        # Test connection first
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        # Create tables
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables initialized successfully")
    except Exception as e:
        error_msg = str(e)
        if "connection" in error_msg.lower() or "could not connect" in error_msg.lower():
            raise Exception(f"Database connection failed. Please check your DATABASE_URL in .env.local. Error: {error_msg}")
        elif "database" in error_msg.lower() and "does not exist" in error_msg.lower():
            raise Exception(f"Database does not exist. Please create the database first. Error: {error_msg}")
        else:
            raise Exception(f"Database initialization failed: {error_msg}")
