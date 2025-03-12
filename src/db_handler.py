import os
import psycopg2

# Load PostgreSQL credentials from .env
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")

def save_financial_data(financial_data):
    """Saves extracted financial data into PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DB
        )
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financial_data (
                id SERIAL PRIMARY KEY,
                metric TEXT,
                value TEXT
            )
        """)

        # Insert extracted KPIs into the database
        for metric, value in financial_data.items():
            cursor.execute("INSERT INTO financial_data (metric, value) VALUES (%s, %s)", (metric, value))

        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Financial data saved to PostgreSQL!")

    except Exception as e:
        print("❌ Database error:", e)
