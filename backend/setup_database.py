#!/usr/bin/env python3
"""
Database setup script - creates the database if it doesn't exist
"""
import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv(".env.local")

def get_db_config():
    """Get database configuration from environment or defaults"""
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/dialogue_db"
    )
    
    # Parse the database URL
    # Format: postgresql://user:password@host:port/database
    if "://" in db_url:
        parts = db_url.replace("postgresql://", "").split("/")
        if len(parts) >= 2:
            db_name = parts[-1]
            auth_host = parts[0]
            
            if "@" in auth_host:
                auth, host_port = auth_host.split("@")
                if ":" in auth:
                    user, password = auth.split(":")
                else:
                    user = auth
                    password = ""
                
                if ":" in host_port:
                    host, port = host_port.split(":")
                else:
                    host = host_port
                    port = "5432"
            else:
                user = "postgres"
                password = ""
                if ":" in auth_host:
                    host, port = auth_host.split(":")
                else:
                    host = auth_host
                    port = "5432"
        else:
            raise ValueError("Invalid DATABASE_URL format")
    else:
        raise ValueError("Invalid DATABASE_URL format")
    
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": db_name
    }

def create_database():
    """Create the database if it doesn't exist"""
    try:
        config = get_db_config()
        db_name = config["database"]
        
        # Connect to PostgreSQL server (not to a specific database)
        conn_config = config.copy()
        conn_config["database"] = "postgres"  # Connect to default postgres database
        
        print(f"Connecting to PostgreSQL server at {config['host']}:{config['port']}...")
        conn = psycopg2.connect(**conn_config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        exists = cursor.fetchone()
        
        if exists:
            print(f"✅ Database '{db_name}' already exists.")
        else:
            print(f"Creating database '{db_name}'...")
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"✅ Database '{db_name}' created successfully!")
        
        cursor.close()
        conn.close()
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Error connecting to PostgreSQL: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running:")
        print("   - macOS: brew services start postgresql")
        print("   - Linux: sudo systemctl start postgresql")
        print("   - Windows: Check Services panel")
        print("\n2. Check your DATABASE_URL in .env.local:")
        print(f"   Current: {os.getenv('DATABASE_URL', 'Not set (using default)')}")
        print("\n3. Try connecting manually:")
        print(f"   psql -U {config.get('user', 'postgres')} -h {config.get('host', 'localhost')}")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Database Setup Script")
    print("=" * 60)
    print()
    
    success = create_database()
    
    if success:
        print()
        print("=" * 60)
        print("Next steps:")
        print("1. Run the API server: python start_server.py")
        print("2. The tables will be created automatically on startup")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("=" * 60)
        print("Database setup failed. Please fix the errors above.")
        print("=" * 60)
        sys.exit(1)

