import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import psycopg2

# =========================
# CONFIG
# =========================

MODEL_NAME = "Qwen/Qwen2.5-3B-Instruct"
MAX_CHARS = 4000
OUTPUT_JSON = "document_roles.json"

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "postgres",
    "password": "psql@123",
    "host": "localhost",
    "port": 5432,
}

ALLOWED_ROLES = {
    "syllabus",
    "marks_distribution",
    "study_material",
    "practice_sets",
    "unknown"
}

PROMPT_TEMPLATE = """
You are classifying an academic document uploaded by a professor.

You are given the following information:

FILENAME:
{filename}

FILE TYPE:
{file_type}

DOCUMENT TEXT (BEGINNING ONLY):
{content}

Your task:
Choose EXACTLY ONE role from the list below that best represents the PURPOSE of this document.

ROLES:
- syllabus
- marks_distribution
- study_material
- practice_sets
- unknown

RULES:
- If the filename contains the word "syllabus", choose "syllabus" even if content is mixed
- If the document describes marks, grading, evaluation, weightage, internal/external exams → choose "marks_distribution"
- If the document contains unit-wise explanations, lecture slides, notes, concepts → choose "study_material"
- If the document contains exercises, questions, problem sets → choose "practice_sets"
- If none apply or you are unsure → choose "unknown"

IMPORTANT:
- Do NOT explain your choice
- Do NOT output anything except the role name
- Output must be exactly one of the role strings above

ROLE:
"""


# =========================
# LOAD MODEL
# =========================

device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    device_map="auto"
)

# =========================
# DB FETCH
# =========================

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("""
    SELECT id, course_id, title, raw_text, file_type
    FROM documents
    WHERE parsed = TRUE
""")

rows = cur.fetchall()
cur.close()
conn.close()

print(f"Loaded {len(rows)} documents")

# =========================
# INFERENCE FUNCTION
# =========================

def infer_role(title, raw_text, file_type: str) -> str:
    title_l = (title or "").lower()

    if "syllabus" in title_l:
        return "syllabus"

    if any(k in title_l for k in ["marks", "evaluation", "weightage", "grading"]):
        return "marks_distribution"

    if any(k in title_l for k in ["question", "practice", "exercise", "problem"]):
        return "practice_sets"
    
    text = (raw_text or "")[:MAX_CHARS]

    prompt = PROMPT_TEMPLATE.format(
        filename=title, 
        file_type=file_type,
        content=text
    )

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=1024
    ).to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=5
        )

    prediction = tokenizer.decode(outputs[0], skip_special_tokens=True)
    prediction = prediction.strip().lower()

    return prediction if prediction in ALLOWED_ROLES else "unknown"

# =========================
# RUN INFERENCE
# =========================

results = []

for doc_id, course_id, title, raw_text, file_type in rows:
    role = infer_role(title, raw_text, file_type)
    
    results.append({
        "document_id": doc_id,
        "course_id": course_id,
        "title": title,
        "role": role
    })

    print(f"[{role.upper():18}] {title}")

# =========================
# SAVE OUTPUT
# =========================

with open(OUTPUT_JSON, "w") as f:
    json.dump(results, f, indent=2)

print(f"\nSaved results to {OUTPUT_JSON}")

with open("document_roles.json") as f:
    roles = json.load(f)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

for r in roles:
    cur.execute(
        """
        UPDATE documents
        SET role = %s
        WHERE id = %s
        """,
        (r["role"], r["document_id"])
    )

conn.commit()
cur.close()
conn.close()

print("Document roles updated successfully.")
