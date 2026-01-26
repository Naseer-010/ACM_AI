import json
import uuid
import psycopg2
from datetime import datetime

# =========================
# CONFIG
# =========================

JSON_PATH = "classroom_dump.json"

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "postgres",
    "host": "localhost",
    "password": "psql@123",
    "port": "5432"
}

# =========================
# DB CONNECTION
# =========================

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# =========================
# SCHEMA CREATION
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    gc_course_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    section TEXT,
    course_state TEXT,
    is_open_elective BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    gc_material_id TEXT,
    drive_file_id TEXT,
    title TEXT,
    file_type TEXT,
    source TEXT,
    parsed BOOLEAN,
    created_at TIMESTAMP
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS assessments (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    type TEXT,
    title TEXT,
    due_date DATE,
    max_points INTEGER,
    source TEXT,
    inferred BOOLEAN,
    created_at TIMESTAMP
);
""")

conn.commit()

# =========================
# HELPERS
# =========================

def gen_uuid():
    return str(uuid.uuid4())


def safe_lower(text):
    return text.lower() if isinstance(text, str) else ""


def infer_file_type(filename: str):
    if not filename:
        return None
    filename = filename.lower()
    if filename.endswith(".pdf"):
        return "pdf"
    if filename.endswith(".ppt") or filename.endswith(".pptx"):
        return "ppt"
    if filename.endswith(".doc") or filename.endswith(".docx"):
        return "docx"
    return "unknown"


def extract_due_date(coursework):
    due = coursework.get("dueDate")
    if not due:
        return None
    return f"{due.get('year')}-{due.get('month'):02d}-{due.get('day'):02d}"


def contains_exam_keywords(text):
    keywords = [
        "exam",
        "test",
        "class test",
        "mid",
        "quiz",
        "semester"
    ]
    text = safe_lower(text)
    return any(k in text for k in keywords)

with open(JSON_PATH, "r") as f:
    classroom_data = json.load(f)

print(f"Loaded {len(classroom_data)} courses")

# =========================
# NORMALIZATION
# =========================

course_id_map = {}  # gc_course_id -> db_course_id

for course_block in classroom_data:

    # -------------------------
    # COURSES
    # -------------------------
    course = course_block["course"]

    db_course_id = gen_uuid()
    gc_course_id = course["id"]

    course_name = course["name"]
    section = course.get("section", "")
    course_state = course["courseState"]

    is_open_elective = (
        "open elective" in safe_lower(course_name)
        or safe_lower(section) == "open elective"
        or course_name.lower().startswith("oe")
    )

    cursor.execute("""
        INSERT INTO courses (
            id, gc_course_id, name, section,
            course_state, is_open_elective,
            created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        db_course_id,
        gc_course_id,
        course_name,
        section,
        course_state,
        is_open_elective,
        datetime.utcnow(),
        datetime.utcnow()
    ))

    course_id_map[gc_course_id] = db_course_id

    # -------------------------
    # DOCUMENTS (MATERIALS)
    # -------------------------
    for material in course_block.get("materials", []):
        gc_material_id = material["id"]

        for item in material.get("materials", []):
            drive = item.get("driveFile", {}).get("driveFile")
            if not drive:
                continue

            doc_id = gen_uuid()
            title = drive.get("title", "")
            drive_file_id = drive["id"]
            file_type = infer_file_type(title)

            cursor.execute("""
                INSERT INTO documents (
                    id, course_id, gc_material_id,
                    drive_file_id, title,
                    file_type, source, parsed, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                doc_id,
                db_course_id,
                gc_material_id,
                drive_file_id,
                title,
                file_type,
                "classroom",
                False,
                datetime.utcnow()
            ))

    # -------------------------
    # ASSESSMENTS (COURSEWORK)
    # -------------------------
    for work in course_block.get("coursework", []):
        assessment_id = gen_uuid()

        due_date = extract_due_date(work)

        cursor.execute("""
            INSERT INTO assessments (
                id, course_id, type, title,
                due_date, max_points,
                source, inferred, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            assessment_id,
            db_course_id,
            work.get("workType", "unknown").lower(),
            work.get("title", ""),
            due_date,
            work.get("maxPoints"),
            "coursework",
            False,
            datetime.utcnow()
        ))

    # -------------------------
    # ASSESSMENTS (ANNOUNCEMENTS - INFERRED)
    # -------------------------
    for announcement in course_block.get("announcements", []):
        text = announcement.get("text", "")

        if not contains_exam_keywords(text):
            continue

        assessment_id = gen_uuid()

        cursor.execute("""
            INSERT INTO assessments (
                id, course_id, type, title,
                source, inferred, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            assessment_id,
            db_course_id,
            "class_test",
            "Inferred from announcement",
            "announcement",
            True,
            datetime.utcnow()
        ))

# =========================
# COMMIT & CLOSE
# =========================

conn.commit()
cursor.close()
conn.close()

print("Normalization completed successfully")
