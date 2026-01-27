import uuid
import psycopg2
from datetime import datetime
import tiktoken
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# =========================
# CONFIG
# =========================

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "postgres",
    "password": "psql@123",
    "host": "localhost",
    "port": 5432,
}

TARGET_TOKENS = 350
MAX_TOKENS = 500

TOPIC_TOP_1_THRESHOLD = 0.78
TOPIC_TOP_2_THRESHOLD = 0.72
DELTA_THRESHOLD = 0.05
MAX_TOPICS_PER_CHUNK = 2

# =========================
# TOKENIZER
# =========================

encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(encoder.encode(text))


embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# =========================
# DB CONNECTION
# =========================

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# =========================
# LOAD TOPICS (CACHE PER COURSE)
# =========================

cur.execute("""
    SELECT t.id, t.course_id, u.name, t.name
    FROM topics t
    JOIN units u ON t.unit_id = u.id
""")

topics_by_course = {}

for topic_id, course_id, unit_name, topic_name in cur.fetchall():
    rep = f"{unit_name} → {topic_name}"
    topics_by_course.setdefault(course_id, []).append({
        "topic_id": topic_id,
        "text": rep
    })

# Precompute topic embeddings
topic_embeddings = {}
for course_id, topics in topics_by_course.items():
    texts = [t["text"] for t in topics]
    embeds = embedder.encode(texts, normalize_embeddings=True)
    topic_embeddings[course_id] = embeds

print("✔ Topics loaded and embedded")

# =========================
# FETCH DOCUMENTS
# =========================

cur.execute("""
    SELECT id, course_id, role, raw_text
    FROM documents
    WHERE parsed = TRUE
      AND raw_text IS NOT NULL
""")

documents = cur.fetchall()
print(f"Found {len(documents)} documents to chunk")

# =========================
# CHUNK + MAP
# =========================

for document_id, course_id, role, raw_text in documents:
    print(f"\nProcessing document {document_id} ({role})")

    # Skip if chunks already exist
    cur.execute(
        "SELECT 1 FROM chunks WHERE document_id = %s LIMIT 1",
        (document_id,)
    )
    if cur.fetchone():
        print("→ Chunks already exist, skipping")
        continue

    paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]

    current_chunk = []
    current_tokens = 0
    chunk_index = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        if para_tokens > MAX_TOKENS:
            continue  # drop pathological paragraphs

        if current_tokens + para_tokens <= TARGET_TOKENS:
            current_chunk.append(para)
            current_tokens += para_tokens
        else:
            chunk_text = "\n".join(current_chunk)
            chunk_id = str(uuid.uuid4())

            # INSERT CHUNK
            cur.execute("""
                INSERT INTO chunks (
                    id, document_id, course_id,
                    chunk_index, text, token_count, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                chunk_id, document_id, course_id,
                chunk_index, chunk_text,
                current_tokens, datetime.utcnow()
            ))

            # MAP TO TOPICS (ONLY STUDY MATERIAL)
            if ((role == "study_material") or (role == "unknown")) and course_id in topics_by_course:
                print("DEBUG: INIDE TOPIC CHUNK MAPPING")
                chunk_embed = embedder.encode(
                    [chunk_text], normalize_embeddings=True
                )
                sims = cosine_similarity(
                    chunk_embed, topic_embeddings[course_id]
                )[0]

                ranked = sorted(
                    enumerate(sims),
                    key=lambda x: x[1],
                    reverse=True
                )

                selected = []

                if ranked and ranked[0][1] >= TOPIC_TOP_1_THRESHOLD:
                    selected.append(ranked[0])

                if (
                    len(ranked) > 1
                    and ranked[1][1] >= TOPIC_TOP_2_THRESHOLD
                    and abs(ranked[0][1] - ranked[1][1]) <= DELTA_THRESHOLD
                ):
                    selected.append(ranked[1])

                for rank, (idx, score) in enumerate(selected[:MAX_TOPICS_PER_CHUNK], start=1):
                    topic_id = topics_by_course[course_id][idx]["topic_id"]
                    cur.execute("""
                        INSERT INTO chunk_topic_map (
                            id, chunk_id, topic_id,
                            similarity_score, rank, inferred, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, TRUE, %s)
                    """, (
                        str(uuid.uuid4()),
                        chunk_id,
                        topic_id,
                        float(score),
                        rank,
                        datetime.utcnow()
                    ))

            chunk_index += 1
            current_chunk = [para]
            current_tokens = para_tokens

    conn.commit()
    print("✔ Done")

# =========================
# CLEANUP
# =========================

cur.close()
conn.close()
print("\nChunking + mapping completed successfully")

