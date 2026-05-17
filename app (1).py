import requests
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# --- Sheet 1: KAM Issue Tracker ---
SHEET_ID  = "1bsVE0CtTfTz7tojWxwBdb2PEa3x_kr1Q1ZST88WlB1E"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

# --- Sheet 2: Mail Feedback Tracker ---
FEEDBACK_SHEET_ID  = "1qWXu2WRA_D6qRwAK7mbGVJ-xHH2MHwqDHZiP5sO3Ofo"
FEEDBACK_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{FEEDBACK_SHEET_ID}/export?format=csv&gid=0"

TEAM = [
    {"key": "asif",  "name": "Ahmed Asif Rashid",  "initials": "AA", "email": "ahmed.asif"},
    {"key": "nahid", "name": "Nuruzzaman Nahid",    "initials": "NN", "email": "nuruzzaman.nahid"},
    {"key": "m3",    "name": "Vacant",              "initials": "?",  "vacant": True},
    {"key": "m4",    "name": "Vacant",              "initials": "?",  "vacant": True},
    {"key": "m5",    "name": "Vacant",              "initials": "?",  "vacant": True},
]

ACTIVE_MEMBERS = [m for m in TEAM if not m.get("vacant")]

def member_key(name):
    if not name:
        return None
    n = name.lower()
    if "asif" in n:
        return "asif"
    if "nuruzzaman" in n or "nahid" in n:
        return "nahid"
    return None

def member_key_by_email(email):
    if not email:
        return None
    e = email.lower()
    if "asif" in e:
        return "asif"
    if "nuruzzaman" in e or "nahid" in e:
        return "nahid"
    return None

def is_ir(comment):
    if not comment:
        return False
    c = comment.lower()
    return any(x in c for x in ["mail sub", "mail:", "subject", "rider not reachable",
                                  "regarding parcel", "parcel lost"]) or \
           any(p in comment for p in ["–", "DA-"])

def is_solved(status):
    return status and "solve" in status.lower()

def fetch_data():
    try:
        r = requests.get(SHEET_URL, timeout=10)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        rows = [dict(row) for row in reader]
        return rows, None
    except Exception as e:
        return [], str(e)

def fetch_feedback():
    try:
        r = requests.get(FEEDBACK_SHEET_URL, timeout=10)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        rows = [dict(row) for row in reader]
        return rows, None
    except Exception as e:
        return [], str(e)

def process_feedback(raw_rows):
    results = []
    for row in raw_rows:
        date       = row.get("Date", "").strip()
        subject    = row.get("Mail Subject Line", "").strip()
        kam_email  = row.get("KAM Mail", "").strip()
        pending    = row.get("Panding", "").strip().upper() == "TRUE"
        solved     = row.get("Slove", "").strip().upper() == "TRUE"
        solve_date = row.get("Slove date", "").strip()
        if not subject:
            continue
        key = member_key_by_email(kam_email)
        results.append({
            "date":       date,
            "subject":    subject,
            "kam_email":  kam_email,
            "key":        key or "unknown",
            "pending":    pending,
            "solved":     solved,
            "solve_date": solve_date,
        })
    return results

def process_rows(rows):
    col_map = {
        "kam":     ["KAM Name", "KAM name"],
        "comment": ["Comments 1    (Ops End)", "Comments 1 (Ops End)", "Comments 1", "Comments1"],
        "date":    ["Date", "Timestamp"],
        "cat":     ["Issue Category"],
        "subcat":  ["Issue Sub Category"],
        "cons":    ["Consignment ID/Merchant Name (Which one is Applicable)", "Consignment ID"],
        "pri":     ["Priority Scale", "Priority"],
        "status":  ["Ops Status", "Issue Status"],
    }

    def gv(row, field):
        for k in col_map[field]:
            if row.get(k, "").strip():
                return row[k].strip()
        return ""

    processed = []
    for row in rows:
        kam    = gv(row, "kam")
        key    = member_key(kam)
        if not key:
            continue
        comment = gv(row, "comment")
        status  = gv(row, "status")
        date    = gv(row, "date").split(" ")[0]
        processed.append({
            "key":     key,
            "kam":     kam,
            "date":    date,
            "cat":     gv(row, "cat"),
            "subcat":  gv(row, "subcat"),
            "cons":    gv(row, "cons"),
            "pri":     gv(row, "pri"),
            "status":  status,
            "comment": comment,
            "is_ir":   is_ir(comment),
            "solved":  is_solved(status),
        })
    return processed

@app.route("/")
def index():
    return render_template("dashboard.html", team=TEAM)

@app.route("/api/data")
def api_data():
    raw, err = fetch_data()
    rows = process_rows(raw)

    members = []
    for m in TEAM:
        if m.get("vacant"):
            members.append({**m, "vacant": True})
            continue
        mr = [r for r in rows if r["key"] == m["key"]]
        solved   = sum(1 for r in mr if r["solved"])
        ir_count = sum(1 for r in mr if r["is_ir"])
        urgent   = sum(1 for r in mr if r["pri"].lower() == "urgent")
        cats = {}
        for r in mr:
            cats[r["cat"] or "Other"] = cats.get(r["cat"] or "Other", 0) + 1
        top_cats = sorted(cats.items(), key=lambda x: -x[1])[:3]
        ratio = round(solved / len(mr) * 100) if mr else 0
        members.append({
            **m,
            "total":    len(mr),
            "solved":   solved,
            "pending":  len(mr) - solved,
            "ir_count": ir_count,
            "urgent":   urgent,
            "ratio":    ratio,
            "top_cats": top_cats,
        })

    all_solved = sum(1 for r in rows if r["solved"])
    all_ir     = sum(1 for r in rows if r["is_ir"])
    all_urgent = sum(1 for r in rows if r["pri"].lower() == "urgent")
    team_ratio = round(all_solved / len(rows) * 100) if rows else 0

    cat_counts = {}
    for r in rows:
        cat_counts[r["cat"] or "Other"] = cat_counts.get(r["cat"] or "Other", 0) + 1
    cat_chart = sorted(cat_counts.items(), key=lambda x: -x[1])[:8]

    today  = datetime.today().date()
    last30 = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    daily_trend = []
    for d in last30:
        day_rows   = [r for r in rows if r["date"] == d]
        per_member = {m["key"]: sum(1 for r in day_rows if r["key"] == m["key"])
                      for m in ACTIVE_MEMBERS}
        daily_trend.append({"date": d, "total": len(day_rows), "per_member": per_member})

    month_map = {}
    for r in rows:
        if r["date"] and len(r["date"]) >= 7:
            month = r["date"][:7]
            if month not in month_map:
                month_map[month] = {"total": 0, **{m["key"]: 0 for m in ACTIVE_MEMBERS}}
            month_map[month]["total"] += 1
            if r["key"] in month_map[month]:
                month_map[month][r["key"]] += 1
    monthly_trend = [{"month": k, **v} for k, v in sorted(month_map.items())]

    # --- Feedback tracker ---
    fb_raw, fb_err = fetch_feedback()
    fb_rows = process_feedback(fb_raw)

    fb_total   = len(fb_rows)
    fb_pending = sum(1 for r in fb_rows if r["pending"])
    fb_solved  = sum(1 for r in fb_rows if r["solved"])
    fb_ratio   = round(fb_solved / fb_total * 100) if fb_total else 0

    fb_per_member = {}
    for m in ACTIVE_MEMBERS:
        mr = [r for r in fb_rows if r["key"] == m["key"]]
        fb_per_member[m["key"]] = {
            "total":   len(mr),
            "pending": sum(1 for r in mr if r["pending"]),
            "solved":  sum(1 for r in mr if r["solved"]),
        }

    return jsonify({
        "ok":            not err,
        "error":         err,
        "rows":          rows,
        "members":       members,
        "summary": {
            "total":  len(rows),
            "solved": all_solved,
            "ratio":  team_ratio,
            "ir":     all_ir,
            "urgent": all_urgent,
        },
        "cat_chart":     cat_chart,
        "daily_trend":   daily_trend,
        "monthly_trend": monthly_trend,
        "dates":  sorted(set(r["date"] for r in rows if r["date"])),
        "cats":   sorted(set(r["cat"]  for r in rows if r["cat"])),
        "feedback": {
            "ok":         not fb_err,
            "total":      fb_total,
            "pending":    fb_pending,
            "solved":     fb_solved,
            "ratio":      fb_ratio,
            "per_member": fb_per_member,
            "rows":       fb_rows,
        },
    })

port = int(__import__('os').environ.get("PORT", 5000))
app.run(debug=False, host="0.0.0.0", port=port)
