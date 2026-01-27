import json
import uuid
import torch
import psycopg2
from transformers import AutoTokenizer, AutoModelForCausalLM


# =========================
# CONFIG
# =========================

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
MAX_CHARS = 5000

DB_CONFIG = {
    "dbname": "studybuddy",
    "user": "postgres",
    "password": "psql@123",
    "host": "localhost",
    "port": 5432,
}

# =========================
# MODEL LOAD
# =========================

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

model.eval()

# =========================
# DB CONNECT
# =========================

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("""
    SELECT id, course_id, raw_text
    FROM documents
    WHERE role = 'syllabus'
""")

# cur.execute("""
#     SELECT raw_text FROM documents
#     where id ='6fa942e1-aef2-4155-82de-1cc341e996fa'
# """)

syllabus_docs = cur.fetchall()
print(f"Found {len(syllabus_docs)} syllabus documents")

PROMPT_TEMPLATE = """
Extract the syllabus structure from the text below.

Task:
- Identify all syllabus UNITS or MODULES.
- For each unit, list its TOPICS in order.

Rules:
- Do not invent content.
- Preserve academic wording.
- If no topics exist, use an empty list.
- Output VALID JSON only.
- No explanations, no markdown.

JSON format:
{{
  "units": [
    {{
      "unit_name": "...",
      "order": 1,
      "topics": [
        {{ "topic_name": "...", "order": 1 }}
      ]
    }}
  ]
}}

Syllabus Text:
{text}
"""


# =========================
# INFERENCE FUNCTION
# =========================

def safe_json_parse(text):
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")

    json_str = text[start:end + 1]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from model: {e}\n\n{json_str}")

    if "units" not in parsed or not isinstance(parsed["units"], list):
        raise ValueError("JSON missing 'units' array")

    return parsed


def infer_units_topics(text: str) -> dict:
    text = text[:MAX_CHARS]
    full_prompt = PROMPT_TEMPLATE.format(text=text)

    # Move inputs to GPU
    inputs = tokenizer(full_prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=1400,
            do_sample=False  
        )

    input_len = inputs.input_ids.shape[1]
    new_tokens = outputs[0][input_len:]
    decoded = tokenizer.decode(new_tokens, skip_special_tokens=True)
    
    print("=========Raw Model Output=========")
    print(decoded)
    print("==================================")

    return safe_json_parse(decoded)

# debug_result = infer_units_topics(syllabus_docs)
# print("=========Parsed JSON Output=========")
# print(debug_result)

# =========================
# INSERT HELPERS
# =========================

def get_or_create_unit(course_id, name, order):
    cur.execute(
        """
        SELECT id FROM units
        WHERE course_id = %s AND name = %s
        """,
        (course_id, name)
    )
    row = cur.fetchone()

    if row:
        return row[0]

    unit_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO units (id, course_id, name, order_index, inferred)
        VALUES (%s, %s, %s, %s, TRUE)
        """,
        (unit_id, course_id, name, order)
    )
    return unit_id


def get_or_create_topic(course_id, unit_id, name, order):
    cur.execute(
        """
        SELECT id FROM topics
        WHERE course_id = %s AND unit_id = %s AND name = %s
        """,
        (course_id, unit_id, name)
    )
    row = cur.fetchone()

    if row:
        return row[0]

    topic_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO topics (id, course_id, unit_id, name, order_index, inferred)
        VALUES (%s, %s, %s, %s, %s, TRUE)
        """,
        (topic_id, course_id, unit_id, name, order)
    )
    return topic_id


# =========================
# MAIN LOOP
# =========================

for doc_id, course_id, raw_text in syllabus_docs:
    print(doc_id)
    
    try:
        
        result = infer_units_topics(raw_text)

        for unit in result.get("units", []):
            unit_name = unit.get("unit_name")
            unit_order = unit.get("order")

            if not unit_name:
                continue

            unit_id = get_or_create_unit(course_id, unit_name, unit_order)

            for topic in unit.get("topics", []):
                topic_name = topic.get("topic_name")
                topic_order = topic.get("order")

                if topic_name:
                    get_or_create_topic(course_id, unit_id, topic_name, topic_order)
    except Exception as e:
        print(f"Error processing document {doc_id}: {e}")

    conn.commit()

# =========================
# CLEANUP
# =========================

cur.close()
conn.close()

print("Unit & topic extraction complete.")
