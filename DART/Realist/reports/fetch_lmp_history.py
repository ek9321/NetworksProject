"""
Fetch 30 days of hourly ERCOT LMP snapshots and save to data/lmp_history.csv.

For each of the 720 hours in the past 30 days, queries one SCED interval
from the ERCOT public API (np6-788-cd/lmp_node_zone_hub).  Checkpoints
completed hours so interrupted runs can resume.

Usage (from project root):
    python3 Realist/reports/fetch_lmp_history.py

Output:
    Realist/reports/data/lmp_history.csv
    Columns: hour, settlement_point, lmp, sp_type
"""

import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
REALIST      = os.path.dirname(SCRIPT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REALIST, ".env"))
except ImportError:
    pass

OUT_CSV   = os.path.join(SCRIPT_DIR, "data", "lmp_history.csv")
CKPT_FILE = os.path.join(SCRIPT_DIR, "data", "lmp_history_checkpoint.txt")

os.makedirs(os.path.join(SCRIPT_DIR, "data"), exist_ok=True)

AUTH_URL = (
    "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com"
    "/B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
)
API_BASE = "https://api.ercot.com/api/public-reports"

# ERCOT operates in Central Prevailing Time.  The API returns naive timestamps
# that are CPT.  We construct query strings in the same naive format.
# In late Jan–Feb 2026 Texas is on CST (UTC-6); DST starts Mar 8 2026.
CPT_OFFSET = timedelta(hours=-6)   # CST; update to -5 after DST transition

DAYS_BACK  = 30
# Final hour: end of yesterday (last complete day)
# Start hour: DAYS_BACK days before that
_now_cpt   = datetime.now(timezone.utc).astimezone(
                 timezone(CPT_OFFSET)).replace(tzinfo=None)
END_HOUR   = _now_cpt.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
START_HOUR = END_HOUR - timedelta(days=DAYS_BACK) + timedelta(hours=1)

FIELD_NAMES = ["hour", "settlement_point", "lmp", "sp_type"]


# ── Auth ──────────────────────────────────────────────────────────────────────

_token_cache = {"token": None, "expires": datetime.min}


def get_token():
    now = datetime.utcnow()
    if _token_cache["token"] and now < _token_cache["expires"]:
        return _token_cache["token"]

    client_id = os.environ["ERCOT_CLIENT_ID"]
    resp = requests.post(AUTH_URL, data={
        "grant_type":    "password",
        "username":      os.environ["ERCOT_USERNAME"],
        "password":      os.environ["ERCOT_PASSWORD"],
        "client_id":     client_id,
        "scope":         f"openid {client_id} offline_access",
        "response_type": "id_token",
    }, timeout=30)
    resp.raise_for_status()
    body  = resp.json()
    token = body.get("id_token") or body.get("access_token")
    if not token:
        raise ValueError("No token in auth response")
    _token_cache["token"]   = token
    _token_cache["expires"] = now + timedelta(minutes=55)
    return token


# ── Fetch one hour ────────────────────────────────────────────────────────────

def classify_sp(name):
    if name.startswith("HB_"):
        return "hub"
    if name.startswith("LZ_"):
        return "load_zone"
    return "resource_node"


def fetch_hour(hour_dt):
    """
    Fetch SCED records within a 15-minute window starting at hour_dt.
    Returns list of {settlement_point, lmp, sp_type} using the FIRST
    SCED timestamp found (de-duplicated by settlement point).
    Returns None on unrecoverable error.
    """
    ts_from = hour_dt.strftime("%Y-%m-%dT%H:%M:%S")
    ts_to   = (hour_dt + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")

    url = (f"{API_BASE}/np6-788-cd/lmp_node_zone_hub"
           f"?size=10000&page=1"
           f"&SCEDTimestampFrom={ts_from}"
           f"&SCEDTimestampTo={ts_to}")

    for attempt in range(3):
        try:
            token = get_token()
            headers = {
                "Authorization":             f"Bearer {token}",
                "Ocp-Apim-Subscription-Key": os.environ["ERCOT_SUBSCRIPTION_KEY"],
            }
            resp = requests.get(url, headers=headers, timeout=60)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    rate-limited, waiting {wait}s…", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            break
        except requests.RequestException as e:
            if attempt == 2:
                print(f"    FAILED after 3 attempts: {e}", file=sys.stderr)
                return None
            time.sleep(10 * (attempt + 1))

    fields = [f["name"] for f in body.get("fields", [])]
    rows   = body.get("data", [])
    if not rows or not fields:
        return []

    # Build rows, take first LMP seen per settlement point
    sp_col  = fields.index("settlementPoint")
    lmp_col = fields.index("LMP")
    seen = {}
    for row in rows:
        sp  = row[sp_col]
        lmp = float(row[lmp_col])
        if sp not in seen:
            seen[sp] = lmp

    return [
        {"settlement_point": sp, "lmp": lmp, "sp_type": classify_sp(sp)}
        for sp, lmp in seen.items()
    ]


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint():
    if not os.path.exists(CKPT_FILE):
        return set()
    with open(CKPT_FILE) as f:
        return {line.strip() for line in f if line.strip()}


def save_checkpoint(hour_str):
    with open(CKPT_FILE, "a") as f:
        f.write(hour_str + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Fetching hourly LMP history: {START_HOUR} → {END_HOUR} (CPT)")
    print(f"Output: {OUT_CSV}\n")

    completed = load_checkpoint()
    print(f"Checkpoint: {len(completed)} hours already done\n")

    # Build list of all hours to fetch
    hours = []
    cur = START_HOUR
    while cur <= END_HOUR:
        hours.append(cur)
        cur += timedelta(hours=1)

    todo = [h for h in hours if h.strftime("%Y-%m-%dT%H") not in completed]
    print(f"Hours to fetch: {len(todo)} / {len(hours)}\n")

    # Open CSV (append mode if resuming)
    file_exists = os.path.exists(OUT_CSV)
    csv_fh = open(OUT_CSV, "a", newline="")
    writer = csv.DictWriter(csv_fh, fieldnames=FIELD_NAMES)
    if not file_exists:
        writer.writeheader()

    ok = 0
    empty = 0
    errors = 0

    for i, hour_dt in enumerate(todo):
        hour_str = hour_dt.strftime("%Y-%m-%dT%H")
        print(f"[{i+1:4d}/{len(todo)}] {hour_str} … ", end="", flush=True)

        records = fetch_hour(hour_dt)

        if records is None:
            print("ERROR")
            errors += 1
        elif len(records) == 0:
            print("empty (no SCED data in window)")
            empty += 1
        else:
            for rec in records:
                writer.writerow({
                    "hour":             hour_str,
                    "settlement_point": rec["settlement_point"],
                    "lmp":              rec["lmp"],
                    "sp_type":          rec["sp_type"],
                })
            csv_fh.flush()
            save_checkpoint(hour_str)
            print(f"{len(records)} records")
            ok += 1

        # Polite rate-limiting: ~1 req/sec
        time.sleep(1.0)

    csv_fh.close()

    print(f"\nDone.  OK={ok}  empty={empty}  errors={errors}")
    print(f"Output: {OUT_CSV}")
    size_mb = os.path.getsize(OUT_CSV) / 1024 / 1024
    print(f"File size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
