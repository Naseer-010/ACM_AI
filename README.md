<p align="center">
  <h1 align="center">🧠 StudyBuddy — Adaptive Cognitive Memory AI</h1>
  <p align="center">
    A syllabus-aware AI that learns <em>what</em> you need to study and <em>how</em> you learn — powered by Google Classroom, LLM inference, and semantic understanding.
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-Qwen%202.5-blueviolet" />
  <img src="https://img.shields.io/badge/DB-PostgreSQL-336791?logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/status-work%20in%20progress-orange" />
</p>

---

## 🎯 Vision

Most AI study tools treat every subject the same. **StudyBuddy doesn't.**

It connects directly to your **Google Classroom**, pulls your actual courses, materials, and assignments, then uses **on-device LLM inference** to deeply understand your syllabus structure — mapping every document to units, topics, and their role in your academic life.

The end goal: an **Adaptive Cognitive Memory AI** that:

- 📚 **Knows your syllabus** — unit-by-unit, topic-by-topic
- 🧩 **Understands document roles** — is it a syllabus? study material? practice set?
- 🔗 **Links content to topics** — via semantic similarity, not keyword hacks
- 🧠 **Adapts to you** — learns what you've covered, what's weak, and what's next *(planned)*
- ⏰ **Tracks deadlines** — assessments and due dates from Classroom *(planned)*

---

## 🏗️ Architecture

```
Google Classroom API
        │
        ▼
┌──────────────────┐
│  Extract & Dump  │  classroom_api_extraction.py
│  (OAuth 2.0)     │  → classroom_dump.json
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Normalize to DB │  normalize_classroom.py
│  (PostgreSQL)    │  → courses, documents, assessments
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Parse Documents │  parse_documents.py
│  (PDF/DOCX/PPTX) │  → raw_text via unstructured
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Infer Doc Roles │  infer_document_roles.py
│  (Qwen 2.5-3B)  │  → syllabus | study_material | marks | practice
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Extract Units & │  infer_units_topics.py
│  Topics (Qwen 7B)│  → structured syllabus graph
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Semantic Chunk  │  chunk_documents.py
│  + Topic Mapping │  → chunks linked to topics via embeddings
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Export for LLM  │  export_chunks_for_colab.py
│  Fine-tuning     │  → exported_chunks.json
└──────────────────┘
```

---

## 📂 Project Structure

| File | Purpose |
|---|---|
| `classroom_api_extraction.py` | OAuth 2.0 auth + fetch courses, materials, assignments & announcements from Google Classroom |
| `google_auth.py` | Reusable Google OAuth credential helper |
| `normalize_classroom.py` | Normalizes raw Classroom JSON into a relational PostgreSQL schema (`courses`, `documents`, `assessments`) |
| `parse_documents.py` | Downloads Drive files and extracts structured text using `unstructured` (PDF, DOCX, PPTX) |
| `infer_document_roles.py` | Uses **Qwen 2.5-3B-Instruct** to classify each document's academic role (syllabus, study material, etc.) |
| `infer_units_topics.py` | Uses **Qwen 2.5-7B-Instruct** to extract a structured unit → topic hierarchy from syllabus documents |
| `chunk_documents.py` | Token-aware chunking (~350 tokens) with semantic topic mapping via `all-MiniLM-L6-v2` embeddings + cosine similarity |
| `export_chunks_for_colab.py` | Exports processed chunks to JSON for downstream LLM fine-tuning or RAG pipelines |
| `backend/` | Backend service scaffolding (Docker, Makefile) — *in progress* |

---

## 🗄️ Database Schema

PostgreSQL database `studybuddy` with the following tables:

```
courses ──┬── documents ──── chunks ──── chunk_topic_map
          │                                    │
          ├── assessments                      │
          │                                    │
          └── units ──── topics ───────────────┘
```

| Table | Description |
|---|---|
| `courses` | Synced from Google Classroom (name, section, open elective flag) |
| `documents` | Materials linked to courses with Drive file IDs, file types, parsed text, and inferred roles |
| `assessments` | Coursework items with due dates + exam assessments inferred from announcements |
| `units` | Syllabus units extracted by LLM |
| `topics` | Topics within units, preserving academic ordering |
| `chunks` | Token-bounded text segments from parsed documents |
| `chunk_topic_map` | Semantic links between chunks and topics (similarity score + rank) |

---

## ⚙️ Setup

### Prerequisites

- Python 3.10+
- PostgreSQL running locally
- Google Cloud project with **Classroom API** and **Drive API** enabled
- `credentials.json` from Google Cloud Console (OAuth 2.0 client)
- GPU recommended for LLM inference steps (Qwen models)

### Installation

```bash
# Clone the repo
git clone https://github.com/your-username/acm_ai.git
cd acm_ai

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Database Setup

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE studybuddy;"
```

### Google Classroom Auth

1. Place your `credentials.json` in the project root
2. Run the extraction script — it will open a browser for OAuth consent on the first run

---

## 🚀 Usage — Pipeline Steps

Run each step sequentially. Each builds on the output of the previous:

```bash
# Step 1: Extract data from Google Classroom
python classroom_api_extraction.py

# Step 2: Normalize into PostgreSQL
python normalize_classroom.py

# Step 3: Download & parse documents (PDF/DOCX/PPTX)
python parse_documents.py

# Step 4: Classify document roles via LLM
python infer_document_roles.py

# Step 5: Extract syllabus units & topics via LLM
python infer_units_topics.py

# Step 6: Chunk documents + map to topics semantically
python chunk_documents.py

# Step 7: Export chunks for fine-tuning / RAG
python export_chunks_for_colab.py
```

---

## 🤖 AI Models Used

| Model | Task | Why |
|---|---|---|
| **Qwen 2.5-3B-Instruct** | Document role classification | Fast, accurate single-label classification from filename + content |
| **Qwen 2.5-7B-Instruct** | Syllabus unit/topic extraction | Structured JSON generation from noisy academic text |
| **all-MiniLM-L6-v2** | Chunk ↔ Topic semantic mapping | Lightweight, high-quality sentence embeddings for cosine similarity |
| **tiktoken (cl100k_base)** | Token counting for chunking | OpenAI-compatible tokenizer for consistent chunk sizing |

---

## 🔮 Roadmap

- [ ] **Adaptive learning engine** — cognitive memory model that tracks what you know vs. what you don't
- [ ] **Spaced repetition** — schedule reviews based on forgetting curves
- [ ] **Conversational tutor** — RAG-powered chat that answers from your actual syllabus
- [ ] **Assessment preparation** — auto-generate practice questions from study material chunks
- [ ] **Progress dashboard** — visualize topic coverage and knowledge gaps
- [ ] **Backend API** — REST/GraphQL service for frontend consumption
- [ ] **Multi-user support** — each student gets their own cognitive profile
- [ ] **Real-time Classroom sync** — webhook-based updates when professors post new material

---

## 🛡️ Security Notes

- `credentials.json` and `token.json` are **gitignored** — never commit these
- Database credentials are currently hardcoded — move to environment variables before deployment

---

## 📄 License

This project is currently unlicensed. Add a license before public distribution.

---

<p align="center">
  <sub>Built with 🧠 for ACM AI — because studying should be smart, not just hard.</sub>
</p>
