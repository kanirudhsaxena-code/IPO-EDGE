import os
import psycopg


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing")
    with psycopg.connect(url) as conn:
        value = conn.execute("SELECT 1").fetchone()[0]
        if value != 1:
            raise RuntimeError("Database check failed")
    print("DATABASE_OK")


if __name__ == "__main__":
    main()
