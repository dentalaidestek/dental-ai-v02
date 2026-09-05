# DENTAL-AI V0.1.0
Project Key: DENTAL-AI-2026-CIHAN

This is the first runnable prototype: SQLite + SQLModel + FastAPI + Jinja2.

## Termux
pkg update
pkg install python
cd DENTAL_AI_V0_1_0
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

Open:
http://127.0.0.1:8000

Demo accounts:
Admin: admin / change-me-admin
Doctor: doctor / change-me-doctor

IMPORTANT: Demo credentials are for local development only. Change/remove them before any real clinical use.
