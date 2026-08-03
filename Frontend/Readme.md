# Setup Guide

Follow the steps below to set up and run the **PACE Discovery Bot Frontend** locally.

---

## 1.  Clone Repository

```bash
git clone <your-repo-url>
cd Frontend
```

---

## 2.  Create and Activate Virtual Environment

```bash
python -m venv .venv
```

```bash
Open 2 Terminals. Terminal 1 & 2

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

---

## 3.  Install Dependencies

```bash
pip install "Django>=5.2,<6"
```

---

## 4.  Run the Server

```bash
Terminal 1

# Use a port that does not clash with your backend
python manage.py runserver 8001
```

The frontend will be available at: http://127.0.0.1:8001/

---

## 5.  Configure Backend API URL

The frontend talks to the Backend API via a small JavaScript config file.

Edit:

ai_listening_tool/static/ai_listening_tool/js/config.js

Set `API_BASE` to your Backend base URL (keep `/api` and do not add a trailing slash after it):

```js
(function () {
  window.RM_TOOL_CONFIG = {
    API_BASE: "http://127.0.0.1:8000/api", // change to your backend API base
    timeoutMs: 120000                      // request timeout in milliseconds
  };
})();
```

If your Backend runs on a different host/port, update the URL accordingly.

---

## Notes

- Ensure the Backend server is running and reachable at `API_BASE` before using the frontend; otherwise, searches will fail.
- Static files (CSS/JS/images) are served by Django while `DEBUG = True` (development mode).
- Stop the Django development server with `Ctrl + C` in Terminal 1.

---

## Quick testing

You can use a second terminal (Terminal 2) to quickly check that the frontend is responding.

### `/tool/` – main search page

```bash
Terminal 2

# Windows (PowerShell)
Invoke-WebRequest -Uri "http://127.0.0.1:8001/tool/"

# macOS / Linux
curl -s "http://127.0.0.1:8001/tool/"
```

### `/tool/results/` – latest results page

```bash
Terminal 2

# Windows (PowerShell)
Invoke-WebRequest -Uri "http://127.0.0.1:8001/tool/results/"

# macOS / Linux
curl -s "http://127.0.0.1:8001/tool/results/"
```

### `/tool/history/` – history page

```bash
Terminal 2

# Windows (PowerShell)
Invoke-WebRequest -Uri "http://127.0.0.1:8001/tool/history/"

# macOS / Linux
curl -s "http://127.0.0.1:8001/tool/history/"
```

### `/tool/simple/` – simple text-only results

```bash
Terminal 2

# Windows (PowerShell)
Invoke-WebRequest -Uri "http://127.0.0.1:8001/tool/simple/"

# macOS / Linux
curl -s "http://127.0.0.1:8001/tool/simple/"
```

### `/tool/debug/` – debug view

```bash
Terminal 2

# Windows (PowerShell)
Invoke-WebRequest -Uri "http://127.0.0.1:8001/tool/debug/"

# macOS / Linux
curl -s "http://127.0.0.1:8001/tool/debug/"
```
