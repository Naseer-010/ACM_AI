import json
import psycopg2

OUTPUT_PATH ="exported_chunks.json"

# =========================
# DB Connection
# =========================

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "nquzet",
    "host": "/var/run/postgresql",
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# =========================
# FETCH CHUNKS
# =========================

cursor.execute("""
    SELECT
        id,
        course_id,
        document_id,
        chunk_index,
        text
    FROM chunks
    ORDER BY course_id, document_id, chunk_index
""")

rows = cursor.fetchall()
print(f"Exporting {len(rows)} chunks")

# =========================
# BUILD JSON
# =========================

chunks = []

for row in rows:
    chunk_id, course_id, document_id, chunk_index, text = row

    chunks.append({
        "chunk_id": chunk_id,
        "course_id": course_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "text": text
    })

# =========================
# WRITE FILE
# =========================

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(chunks, f, indent=2, ensure_ascii=False)

print(f"Saved to {OUTPUT_PATH}")


cursor.close()
conn.close()
