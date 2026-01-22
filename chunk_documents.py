import uuid
import psycopg2
from datetime import datetime
import tiktoken

# =========================
# CONFIG
# =========================

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "nquzet",
    "host": "/var/run/postgresql",
}

TARGET_TOKENS = 500
MAX_TOKENS = 650

# =========================
# TOKENIZER
# =========================

encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(encoder.encode(text))

# =========================
# DB CONNECTION
# =========================

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# =========================
# FETCH DOCUMENTS
# =========================

cursor.execute("""
    SELECT id, course_id, raw_text
    FROM documents
    WHERE parsed = TRUE
      AND raw_text IS NOT NULL
""")

documents = cursor.fetchall()
print(f"Found {len(documents)} documents to chunk")

# =========================
# CHUNKING LOGIC
# =========================

for document_id, course_id, raw_text in documents:
    print(f"Chunking document {document_id}")

    # Idempotency: skip if chunks already exist
    cursor.execute(
        "SELECT 1 FROM chunks WHERE document_id = %s LIMIT 1",
        (document_id,)
    )
    if cursor.fetchone():
        print("→ Chunks already exist, skipping")
        continue

    paragraphs = [
        p.strip()
        for p in raw_text.split("\n")
        if p.strip()
    ]

    current_chunk = []
    current_tokens = 0
    chunk_index = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # If single paragraph is too large, force split
        if para_tokens > MAX_TOKENS:
            words = para.split()
            temp = []
            for word in words:
                temp.append(word)
                if count_tokens(" ".join(temp)) >= TARGET_TOKENS:
                    chunk_text = " ".join(temp)
                    cursor.execute("""
                        INSERT INTO chunks (
                            id, document_id, course_id,
                            chunk_index, text, token_count, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        str(uuid.uuid4()),
                        document_id,
                        course_id,
                        chunk_index,
                        chunk_text,
                        count_tokens(chunk_text),
                        datetime.utcnow()
                    ))
                    chunk_index += 1
                    temp = []
            continue

        if current_tokens + para_tokens <= TARGET_TOKENS:
            current_chunk.append(para)
            current_tokens += para_tokens
        else:
            chunk_text = "\n".join(current_chunk)
            cursor.execute("""
                INSERT INTO chunks (
                    id, document_id, course_id,
                    chunk_index, text, token_count, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                document_id,
                course_id,
                chunk_index,
                chunk_text,
                current_tokens,
                datetime.utcnow()
            ))
            chunk_index += 1
            current_chunk = [para]
            current_tokens = para_tokens

    # Final chunk
    if current_chunk:
        chunk_text = "\n".join(current_chunk)
        cursor.execute("""
            INSERT INTO chunks (
                id, document_id, course_id,
                chunk_index, text, token_count, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            document_id,
            course_id,
            chunk_index,
            chunk_text,
            current_tokens,
            datetime.utcnow()
        ))

    conn.commit()
    print("✔ Chunking complete")

# =========================
# CLEANUP
# =========================

cursor.close()
conn.close()
print("All documents chunked successfully ✅")
