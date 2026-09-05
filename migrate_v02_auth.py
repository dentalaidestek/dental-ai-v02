import sqlite3
from pathlib import Path

DB = Path("dental_ai.db")

con = sqlite3.connect(DB)
cur = con.cursor()

columns = {
    "password_hash": "TEXT",
    "email": "TEXT",
    "is_active": "BOOLEAN NOT NULL DEFAULT 1",
    "created_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
}

existing = {
    row[1]
    for row in cur.execute("PRAGMA table_info(user)").fetchall()
}

for name, definition in columns.items():
    if name not in existing:
        print(f"+ Ekleniyor: {name}")
        cur.execute(f"ALTER TABLE user ADD COLUMN {name} {definition}")
    else:
        print(f"= Zaten var: {name}")

con.commit()

print("\nUSER TABLOSU SON DURUM:")
for row in cur.execute("PRAGMA table_info(user)").fetchall():
    print(row)

con.close()

print("\nMigration tamamlandı.")
