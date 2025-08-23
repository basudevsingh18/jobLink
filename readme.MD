# Micro-Jobs Task Board (Flask + HTML)

A lean MVP for a micro-jobs board that connects customers with skilled workers.  
Built with **Python (Flask)** and **barebones HTML templates** (no DB yet).

---

## Features (MVP)
- Post a job (title, description, budget, location, contact)
- Browse open jobs (search, filter by category/location)
- View job details and **Accept via WhatsApp** (prefilled message)
- Simple admin panel with seed demo jobs

---

## Project Structure
```
microjobs-taskboard/
│
├── app.py                 # Entry point (Flask app)
├── requirements.txt       # Python dependencies
├── README.md              # Setup + usage
│
├── /microjobs
│   └── routes.py          # All routes + in-memory job store
│
├── /templates             # HTML templates (Jinja2)
│   ├── base.html
│   ├── jobs.html
│   ├── job_detail.html
│   ├── post_job.html
│   └── admin.html
│
└── /static                # (empty for now; add CSS/JS later)
```

---

## Setup

1. Clone repo / copy files.  
2. (Optional) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Mac/Linux
   venv\Scripts\activate      # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run app:
   ```bash
   python app.py
   ```
5. Visit in your browser:
   - `http://127.0.0.1:5000/seed` → preload demo jobs  
   - `http://127.0.0.1:5000/jobs` → browse jobs

---

## Next Steps
- Add a real database (SQLite or Postgres) instead of in-memory list.
- Add login/auth (for workers & customers).
- Add ratings/reviews for workers.
- Add payments (MMG/credit card).

---

## License
MIT — free to use, modify, and build upon.