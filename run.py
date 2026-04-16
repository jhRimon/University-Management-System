from app import create_app
from app.db import get_db_connection

app = create_app()

@app.route("/testdb")
def test_db():
    conn = get_db_connection()

    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE();")
        db = cursor.fetchone()
        cursor.close()
        conn.close()

        return f"Connected to database: {db}"

    return "Database connection failed"


if __name__ == "__main__":
    app.run(debug=True)