import requests
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

DASHBOARD_TITLE = "Grid KAM Issues Escalation Dashboard"

# ── Apps Script Web App URL ───────────────────────────────────────────────────
# After deploying Code.gs, paste your Web App URL here:
APPS_SCRIPT_URL = ""

# Fallback: direct CSV export (used if Apps Script URL not set)
SHEET_ID = "14OpqyqI9QiF0dtuxaRMX3DnHdMEOoe9D-BTccYgGqwU"
TABS_FALLBACK = {
    "ISD 2026":     "0",
    "OSD 2026":     "1669718373",
    "Central 2026": "226077825",
}
FEEDBACK_SHEET_ID  = "1qWXu2WRA_D6qRwAK7mbGVJ-xHH2MHwqDHZiP5sO3Ofo"
FEEDBACK_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{FEEDBACK_SHEET_ID}/export?format=csv&gid=0"

# ── Team config ───────────────────────────────────────────────────────────────
TEAM = [
    {"key": "asif",  "name": "Ahmed Asif Rashid",  "initials": "AA"},
    {"key": "nahid", "name": "Nuruzzaman Nahid",    "initials": "NN"},
    {"key": "m3",    "name": "Vacant",              "initials": "?", "vacant": True},
    {"key": "m4",    "name": "Vacant",              "initials": "?", "vacant": True},
    {"key": "m5",    "name": "Vacant",              "initials": "?", "vacant": True},
]
ACTIVE_MEMBERS = [m for m in TEAM if not m.get("vacant")]

# ── Helpers ───────────────────────────────────────────────────────────────────
def member_key(name):
    if not name: return None
    n = name.lower()
    if "asif" in n: return "asif"
    if "nuruzzaman" in n or "nahid" in n: return "nahid"
    return None

def member_key_by_email(email):
    if not email: return None
    e = email.lower()
    if "asif" in e: return "asif"
    if "nuruzzaman" in e or "nahid" in e: return "nahid"
    return None

def is_ir(details):
    if not details: return False
    c = details.lower()
    return any(x in c for x in [
        "mail sub", "mail:", "subject", "rider not reachable",
        "regarding parcel", "parcel lost"
    ]) or any(p in details for p in ["–", "DA-"])

def is_solved(status):
    return bool(status and ("solve" in status.lower() or "closed" in status.lower()))

def is_pending(status):
    return bool(status and "pending" in status.lower())

def fuzzy_get(row, *keywords):
    for key in row:
        kl = key.lower().strip()
        for kw in keywords:
            if kw.lower() in kl:
                val = row[key]
                return val.strip() if val else ""
    return ""

def normalise_date(ts):
    """Convert various date formats to YYYY-MM-DD."""
    if not ts: return ""
    ts = ts.strip().split(" ")[0]   # take date part only
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(ts, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ts  # return as-is if nothing matched

# ── Data fetching ─────────────────────────────────────────────────────────────
def using_apps_script():
    return "YOUR_DEPLOYMENT_ID" not in APPS_SCRIPT_URL and APPS_SCRIPT_URL.startswith("https://")

def fetch_from_apps_script():
    """Fetch all data from Apps Script Web App (single HTTP call)."""
    try:
        r = requests.get(APPS_SCRIPT_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            return None, None, data.get("error", "Apps Script returned error")

        main_rows = data.get("main", {}).get("rows", [])
        fb_rows   = data.get("feedback", {}).get("rows", [])
        return main_rows, fb_rows, None
    except Exception as e:
        return None, None, str(e)

def fetch_csv_fallback():
    """Fallback: fetch raw CSV from Google Sheets public export."""
    import csv
    all_rows, errors = [], []
    for tab_name, gid in TABS_FALLBACK.items():
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                row["_tab"] = tab_name
                all_rows.append(dict(row))
        except Exception as e:
            errors.append(f"{tab_name}: {e}")

    # Feedback
    fb_rows = []
    try:
        r = requests.get(FEEDBACK_SHEET_URL, timeout=10)
        r.raise_for_status()
        import csv as _csv
        reader = _csv.DictReader(io.StringIO(r.text))
        fb_rows = [dict(row) for row in reader]
    except Exception as e:
        errors.append(f"feedback: {e}")

    return all_rows, fb_rows, ("; ".join(errors) if errors else None)

def fetch_all_data():
    if using_apps_script():
        return fetch_from_apps_script()
    return fetch_csv_fallback()

# ── Row processing ────────────────────────────────────────────────────────────
def process_rows(raw_rows, kam_filter=None):
    processed = []
    for row in raw_rows:
        kam = fuzzy_get(row, "kam name", "kam")
        if not kam:
            email = fuzzy_get(row, "email address", "email")
            key   = member_key_by_email(email)
            kam   = email
        else:
            key = member_key(kam)

        if not key: continue
        if kam_filter and key != kam_filter: continue

        date         = normalise_date(fuzzy_get(row, "timestamp", "date"))
        status       = fuzzy_get(row, "ops status", "issue status", "status")
        cat          = fuzzy_get(row, "issue category", "category")
        subcat       = fuzzy_get(row, "issue sub category", "sub category", "subcat")
        cons         = fuzzy_get(row, "consignment id", "merchant name", "consignment")
        pri          = fuzzy_get(row, "priority scale", "priority")
        details      = fuzzy_get(row, "issue details")
        channel      = fuzzy_get(row, "channel")
        zone         = fuzzy_get(row, "zone")
        hub          = fuzzy_get(row, "concern hub", "hub")
        tab          = row.get("_tab", "")
        comment1     = fuzzy_get(row, "comments 1")
        comment2     = fuzzy_get(row, "comments 2")
        resolved_date= normalise_date(fuzzy_get(row, "resolved date", "resolve date"))
        issue_age    = fuzzy_get(row, "issue pick age", "pick age")
        responsible  = fuzzy_get(row, "responsible end", "responsible")
        regional_lead= fuzzy_get(row, "regional lead")
        kam_feedback = fuzzy_get(row, "kam feedback status", "feedback status")
        validation   = fuzzy_get(row, "validation")

        # Determine solved: check ops status + resolved date
        _solved  = is_solved(status) or bool(resolved_date)
        _pending = is_pending(status) and not _solved

        processed.append({
            "key": key, "kam": kam, "date": date,
            "cat": cat, "subcat": subcat, "cons": cons,
            "pri": pri, "status": status,
            "details": details, "channel": channel,
            "zone": zone, "hub": hub, "tab": tab,
            "comment1": comment1, "comment2": comment2,
            "resolved_date": resolved_date, "issue_age": issue_age,
            "responsible": responsible, "regional_lead": regional_lead,
            "kam_feedback": kam_feedback, "validation": validation,
            "is_ir":   is_ir(details or comment1),
            "solved":  _solved,
            "pending": _pending,
        })
    return processed

def process_feedback(raw_rows):
    results = []
    for row in raw_rows:
        date       = fuzzy_get(row, "date")
        subject    = fuzzy_get(row, "mail subject", "subject")
        kam_email  = fuzzy_get(row, "kam mail", "email")
        pending_v  = fuzzy_get(row, "panding", "pending")
        solved_v   = fuzzy_get(row, "slove", "solve")
        solve_date = fuzzy_get(row, "slove date", "solve date", "solved date")
        if not subject: continue
        pending = pending_v.upper() in ("TRUE", "YES", "1")
        solved  = solved_v.upper()  in ("TRUE", "YES", "1")
        key     = member_key_by_email(kam_email)
        results.append({
            "date": date, "subject": subject, "kam_email": kam_email,
            "key": key or "unknown", "pending": pending,
            "solved": solved, "solve_date": solve_date,
        })
    return results

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("dashboard.html", team=TEAM, title=DASHBOARD_TITLE)

@app.route("/api/debug")
def debug():
    raw, fb_raw, err = fetch_all_data()
    headers   = list(raw[0].keys())    if raw    else []
    fb_headers= list(fb_raw[0].keys()) if fb_raw else []
    return jsonify({
        "source":       "apps_script" if using_apps_script() else "csv_fallback",
        "apps_script_url": APPS_SCRIPT_URL,
        "error":        err,
        "total_rows":   len(raw),
        "fb_rows":      len(fb_raw),
        "headers":      headers,
        "fb_headers":   fb_headers,
        "sample":       raw[:3],
    })

@app.route("/api/data")
def api_data():
    kam_filter = request.args.get("kam", None)

    raw_main, raw_fb, err = fetch_all_data()
    rows = process_rows(raw_main or [], kam_filter=kam_filter)

    # ── Per-member stats ──────────────────────────────────────────────────────
    members = []
    for m in TEAM:
        if m.get("vacant"):
            members.append({**m, "vacant": True}); continue
        mr     = [r for r in rows if r["key"] == m["key"]]
        solved = sum(1 for r in mr if r["solved"])
        ir_cnt = sum(1 for r in mr if r["is_ir"])
        urgent = sum(1 for r in mr if r["pri"].lower() == "urgent")
        cats   = {}
        for r in mr: cats[r["cat"] or "Other"] = cats.get(r["cat"] or "Other", 0) + 1
        top_cats   = sorted(cats.items(), key=lambda x: -x[1])[:3]
        ratio      = round(solved / len(mr) * 100) if mr else 0
        tab_counts = {}
        for r in mr:
            t = r["tab"]; tab_counts[t] = tab_counts.get(t, 0) + 1
        members.append({
            **m, "total": len(mr), "solved": solved,
            "pending": len(mr) - solved,
            "ir_count": ir_cnt, "urgent": urgent,
            "ratio": ratio, "top_cats": top_cats,
            "tab_counts": tab_counts,
        })

    # ── Team summary ──────────────────────────────────────────────────────────
    all_solved = sum(1 for r in rows if r["solved"])
    all_ir     = sum(1 for r in rows if r["is_ir"])
    all_urgent = sum(1 for r in rows if r["pri"].lower() == "urgent")
    team_ratio = round(all_solved / len(rows) * 100) if rows else 0

    all_tabs   = sorted(set(r["tab"] for r in rows if r["tab"]))
    tab_totals = {t: sum(1 for r in rows if r["tab"] == t) for t in all_tabs}

    # ── Charts ────────────────────────────────────────────────────────────────
    cat_counts = {}
    for r in rows: cat_counts[r["cat"] or "Other"] = cat_counts.get(r["cat"] or "Other", 0) + 1
    cat_chart = sorted(cat_counts.items(), key=lambda x: -x[1])[:8]

    today  = datetime.today().date()
    last30 = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    daily_trend = []
    for d in last30:
        dr = [r for r in rows if r["date"] == d]
        pm = {m["key"]: sum(1 for r in dr if r["key"] == m["key"]) for m in ACTIVE_MEMBERS}
        daily_trend.append({"date": d, "total": len(dr), "per_member": pm})

    month_map = {}
    for r in rows:
        if r["date"] and len(r["date"]) >= 7:
            month = r["date"][:7]
            if month not in month_map:
                month_map[month] = {"total": 0, **{m["key"]: 0 for m in ACTIVE_MEMBERS}}
            month_map[month]["total"] += 1
            if r["key"] in month_map[month]: month_map[month][r["key"]] += 1
    monthly_trend = [{"month": k, **v} for k, v in sorted(month_map.items())]

    # ── Feedback ──────────────────────────────────────────────────────────────
    fb_rows    = process_feedback(raw_fb or [])
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
        "ok": not err, "error": err,
        "source": "apps_script" if using_apps_script() else "csv_fallback",
        "rows": rows, "members": members,
        "summary": {
            "total": len(rows), "solved": all_solved,
            "ratio": team_ratio, "ir": all_ir, "urgent": all_urgent,
            "tab_totals": tab_totals,
        },
        "cat_chart":     cat_chart,
        "daily_trend":   daily_trend,
        "monthly_trend": monthly_trend,
        "dates": sorted(set(r["date"] for r in rows if r["date"])),
        "cats":  sorted(set(r["cat"]  for r in rows if r["cat"])),
        "tabs":  all_tabs,
        "feedback": {
            "ok": True, "total": fb_total,
            "pending": fb_pending, "solved": fb_solved,
            "ratio": fb_ratio, "per_member": fb_per_member,
            "rows": fb_rows,
        },
    })

port = int(__import__('os').environ.get("PORT", 5000))
app.run(debug=False, host="0.0.0.0", port=port)
