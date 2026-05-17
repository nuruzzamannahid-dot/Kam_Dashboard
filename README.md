# KAM Team — Issue Tracker Dashboard

Live dashboard for Ahmed Asif Rashid and Nuruzzaman Nahid (+ 3 vacant seats).
Pulls data directly from the shared Google Sheet and auto-refreshes every 90 seconds.

---

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the app
```bash
python app.py
```

### 3. Open in browser
```
http://localhost:5000
```

---

## Features
- Live issue count per member
- Solve ratio with colour-coded progress bar
- IR mail detection from Comments column
- Urgent issue alerts per member
- Category breakdown bar chart
- Filterable issues log (by member, date, category, keyword)
- Auto-refresh every 90 seconds
- 3 vacant seat placeholders ready for new hires

---

## Adding new team members
Open `app.py` and find the `TEAM` list. Replace a `Vacant` entry:

```python
{"key": "m3", "name": "New Member Name", "initials": "NM"},
```

Then update the `member_key()` function to match their name:

```python
def member_key(name):
    ...
    if "new member" in n:
        return "m3"
```

---

## Sharing with your team
Run on any machine visible to your team and share the URL, e.g.:
```
http://YOUR-PC-IP:5000
```
Or deploy to a free host like Railway, Render, or PythonAnywhere.

---

## Google Sheet requirement
The sheet must be set to **"Anyone with the link can view"**.
Sheet ID: `1bsVE0CtTfTz7tojWxwBdb2PEa3x_kr1Q1ZST88WlB1E`
