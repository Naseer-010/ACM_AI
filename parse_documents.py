import io
import os
import tempfile
import psycopg2

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth import get_credentials

from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.pptx import partition_pptx

# =========================
# CONFIG
# =========================

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "postgres",
    "host": "localhost",
    "password": "psql@123",
    "port": "5432"
}

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# =========================
# DB CONNECTION
# =========================

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# =========================
# GOOGLE DRIVE CLIENT
# =========================

creds = get_credentials(SCOPES)
drive_service = build("drive", "v3", credentials=creds)

# =========================
# FILE DOWNLOAD
# =========================

def download_drive_file(file_id) -> bytes:
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    return fh.read()

# =========================
# UNSTRUCTURED PARSERS
# =========================

def elements_to_text(elements):
    """
    Convert unstructured elements into a clean, LLM-friendly text
    with semantic tags preserved.
    """
    lines = []

    for el in elements:
        text = el.text.strip() if el.text else ""
        if not text:
            continue

        category = el.category.upper()
        lines.append(f"[{category}] {text}")

    return "\n".join(lines)


def parse_pdf(file_path):
    elements = partition_pdf(
        filename=file_path,
        strategy="hi_res",                 # IMPORTANT for layout
        infer_table_structure=True,        # VERY IMPORTANT for syllabus tables
        extract_images_in_pdf=False,
    )
    return elements_to_text(elements)


def parse_docx(file_path):
    elements = partition_docx(filename=file_path)
    return elements_to_text(elements)


def parse_ppt(file_path):
    elements = partition_pptx(filename=file_path)
    return elements_to_text(elements)

# =========================
# MAIN PIPELINE
# =========================

cursor.execute("""
    SELECT id, drive_file_id, file_type
    FROM documents
    WHERE parsed = FALSE
""")

documents = cursor.fetchall()
print(f"Found {len(documents)} unparsed documents")

for doc_id, drive_file_id, file_type in documents:
    print(f"\nParsing document {doc_id} ({file_type})")

    tmp_path = None

    try:
        # Download file bytes
        file_bytes = download_drive_file(drive_file_id)

        # Create temp file (unstructured requires a file path)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # Parse based on file type
        if file_type == "pdf":
            extracted_text = parse_pdf(tmp_path)
        elif file_type == "docx":
            extracted_text = parse_docx(tmp_path)
        elif file_type == "ppt":
            extracted_text = parse_ppt(tmp_path)
        else:
            print(f" Unsupported file type: {file_type}")
            continue

        if not extracted_text.strip():
            print(" No text extracted, skipping")
            continue

        # Store in DB
        cursor.execute("""
            UPDATE documents
            SET raw_text = %s,
                parsed = TRUE
            WHERE id = %s
        """, (
            extracted_text,
            doc_id
        ))

        conn.commit()
        print("✔ Parsed and stored successfully")

    except Exception as e:
        conn.rollback()
        print(f" Failed to parse document {doc_id}: {e}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# =========================
# CLEANUP
# =========================

cursor.close()
conn.close()
print("\nDocument parsing completed")
