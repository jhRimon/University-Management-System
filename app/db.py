import mysql.connector
from flask import current_app


def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=current_app.config["DB_HOST"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"]
        )

        return connection

    except mysql.connector.Error as err:
        print("Database connection error:", err)
        return None