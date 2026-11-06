# Auspify IMS

Inventory Management System — Python Flask + React (Vite) + SQLite.

> Project status: **Step 1 (inventory modules)** - schema + seed data, product /
> category / supplier CRUD (API and UI). Features are added step by step; the
> README is completed at the end of the project.

## Project layout

```
auspify_ims/
├── backend/            # Flask API
│   ├── app.py          # entry point (create_app factory + /api/health)
│   └── requirements.txt
└── frontend/           # React app (Vite)
    ├── index.html
    ├── vite.config.js  # dev server + /api proxy to Flask
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── App.css
        └── index.css
```

## Prerequisites

- Python 3.10+
- Node.js 20.19+ (or 22.12+) and npm

## Setup (first time only)

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend (in a second terminal)
cd frontend
npm install
```

## Run (two terminals)

```bash
# Terminal 1 - backend on http://localhost:5000
cd backend
source .venv/bin/activate
python app.py

# Terminal 2 - frontend on http://localhost:5173
cd frontend
npm run dev
```

Open http://localhost:5173 — the page should show **Backend status: ok**.

## How the frontend talks to the backend

The Vite dev server proxies every request starting with `/api` to
`http://localhost:5000` (see `frontend/vite.config.js`). The React code
therefore uses relative URLs such as `fetch('/api/health')`. Flask-CORS is also
enabled on `/api/*` so the API can be called directly from another origin.
