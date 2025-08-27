# JobLink — Micro-Jobs Task Board

A lean MVP to connect **customers** who post quick tasks with **workers** who accept them.  
Built with **Flask (Python)**, **Jinja2 templates**, and ready to scale with **Postgres + Docker + automated migrations**.

---

## Features
- Post a job (title, description, budget, location, contact)
- Browse open jobs (search, filter by category/location)
- View job details and **Accept via WhatsApp** (prefilled message)
- Simple admin panel with seed demo jobs
- **DB mode**: job acceptance with transparent audit events

---

## Project Structure
jobLink/  
├── app.py                 # Flask entry point  
├── requirements.txt       # Python dependencies  
├── README.md              # Project documentation  
│  
├── microjobs/             # Application package  
│   ├── __init__.py  
│   └── routes.py          # Routes + logic  
│  
├── templates/             # HTML (Jinja2) templates  
│   ├── base.html  
│   ├── jobs.html  
│   ├── job_detail.html  
│   ├── post_job.html  
│   └── admin.html  
│  
├── static/                # CSS, JS, images  
│  
├── docker-compose.yml     # Postgres + PostgREST + Flask (DB mode)  
├── .env.example           # Sample environment variables  
│  
├── db/  
│   └── init/              # SQL migrations (applied in lexical order)  
│       ├── 01_schema.sql  
│       ├── 02_seed_min.sql  
│       └── 03_job_events.sql  
│  
└── scripts/               # Helper scripts for DB migrations  
    ├── migrate.sh         # Run migrations (Mac/Linux)  
    ├── migrate.bat        # Run migrations (Windows CMD)  
    ├── migrate.ps1        # Run migrations (Windows PowerShell)  
    ├── psql.sh            # Quick psql shell into container  
    └── seed.sh            # Run only *seed*.sql files  

---

## Quickstart

### Simple Mode (No Database)
1. (Optional) Create a virtual environment  
   - Mac/Linux:  
     ```bash
     python -m venv venv
     source venv/bin/activate
     ```  
   - Windows:  
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```

2. Install dependencies  
   ```bash
   pip install -r requirements.txt

3. Run the Flask App
   ```bash
   python app.py

4. Open in Browser
   - http://127.0.0.1:5000/seed → preload demo jobs
   - http://127.0.0.1:5000/jobs → browse jobs

## Database Mode (Docker + Postgres + PostgREST)

1. Copy environment file 
     ```bash
     cp .env.example .env
     ```  

2. Start services 
   ```bash
   docker compose up -d

3. Run migrations
   - Mac/Linux:
     ```bash
     ./scripts/migrate.sh
     ```
   - Windows CMD:
     ```bash
     scripts\migrate.bat
   ```
   - Windows PowerShell:
     ```bash
     pwsh -File scripts\migrate.ps1 
   ```

4. (Optional) Run seed data only
   ```bash
   ./scripts/seed.sh
   ```

## License
MIT — free to use, modify, and build upon.