import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection parameters
db_params = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT', '5432')
}

# SQL to create tables
tables = [
    """
    CREATE TABLE IF NOT EXISTS sources (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        api_base_url VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guides (
        id SERIAL PRIMARY KEY,
        source_id INTEGER REFERENCES sources(id),
        external_id VARCHAR(255),
        title VARCHAR(255) NOT NULL,
        subject VARCHAR(255),
        type VARCHAR(50),
        difficulty VARCHAR(50),
        category VARCHAR(255),
        locale VARCHAR(10),
        raw_data JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_id, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS steps (
        id SERIAL PRIMARY KEY,
        guide_id INTEGER REFERENCES guides(id),
        external_id VARCHAR(255),
        orderby INTEGER,
        title VARCHAR(255),
        raw_data JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(guide_id, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS media (
        id SERIAL PRIMARY KEY,
        guide_id INTEGER REFERENCES guides(id),
        step_id INTEGER REFERENCES steps(id) NULL,
        media_type VARCHAR(50),
        external_id VARCHAR(255),
        original_url TEXT,
        s3_path TEXT,
        width INTEGER,
        height INTEGER,
        metadata JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(guide_id, step_id, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tags (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guide_tags (
        guide_id INTEGER REFERENCES guides(id),
        tag_id INTEGER REFERENCES tags(id),
        PRIMARY KEY (guide_id, tag_id)
    )
    """
]

# Insert initial source
initial_data = [
    """
    INSERT INTO sources (name, description, api_base_url)
    VALUES ('iFixit', 'iFixit repair guides and media', 'https://www.ifixit.com/api/2.0')
    ON CONFLICT DO NOTHING
    """
]

# Connect to database and create tables
try:
    conn = psycopg2.connect(**db_params)
    cursor = conn.cursor()
    
    # Create tables
    for table in tables:
        cursor.execute(table)
    
    # Insert initial data
    for data in initial_data:
        cursor.execute(data)
        
    conn.commit()
    print("Database setup completed successfully")
except Exception as e:
    print(f"Error setting up database: {e}")
finally:
    if 'cursor' in locals() and cursor:
        cursor.close()
    if 'conn' in locals() and conn:
        conn.close()
