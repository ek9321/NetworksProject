"""
Fetch real-time LMPs from the ERCOT Public API and write lmp_snapshot.json.

Usage:
    python Realist/ERCOT/pull_lmp_ercot.py

Credentials are read from environment variables (or Realist/.env for local dev):
    ERCOT_USERNAME
    ERCOT_PASSWORD
    ERCOT_CLIENT_ID
    ERCOT_SUBSCRIPTION_KEY

Output:
    Realist/grid_data/lmp_snapshot.json
"""

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import requests

# Load .env for local development (ignored gracefully if python-dotenv not installed)
try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(_env)
except ImportError:
    pass

# ── Auth ──────────────────────────────────────────────────────────────────────

AUTH_URL = (
    "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com"
    "/B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
)
API_BASE = "https://api.ercot.com/api/public-reports"

SP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "grid_data", "SP_List_EB_Mapping",
)
RN_TO_UNIT_CSV = os.path.join(SP_DIR, "Resource_Node_to_Unit_01292026_104938.csv")
SP_CSV         = os.path.join(SP_DIR, "Settlement_Points_01292026_104938.csv")


def get_token():
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
    body = resp.json()
    token = body.get("id_token") or body.get("access_token")
    if not token:
        print(f"Auth response keys: {list(body.keys())}", file=sys.stderr)
        raise ValueError("No token in auth response")
    return token


# ── Fetch ─────────────────────────────────────────────────────────────────────

def _rows_from_response(raw):
    """
    Parse one page of the ERCOT API response into a list of row-dicts.

    The API has two observed formats:
      A) {"fields": [{"name": col}, ...], "data": [[v0,v1,...], ...], "_links": {...}}
         — used by most endpoints (gridstatus-documented format)
      B) {"fields": [...], "report": {"col": [v0,v1,...], ...}, "_links": {...}}
         — columnar dict variant seen on some endpoints
    """
    fields_meta = raw.get("fields", [])
    col_names   = [f["name"] for f in fields_meta] if fields_meta else []

    # Format A: data is a list of row-arrays
    data = raw.get("data")
    if isinstance(data, list) and data:
        return [{col_names[i]: row[i] for i in range(len(col_names))} for row in data]

    # Format B: report is a dict of {col_name: [values]}
    report = raw.get("report", {})
    if isinstance(report, dict) and report:
        col_keys = list(report.keys())
        # If values are lists, it's columnar
        first_val = report[col_keys[0]]
        if isinstance(first_val, list):
            n = len(first_val)
            return [{k: report[k][i] for k in col_keys} for i in range(n)]
        # If values are scalars (integers = column indices into data?),
        # the data rows may be inline in a separate key or this is a metadata response.
        # Log and return empty — caller will handle.
        print(f"  report values are scalars ({type(first_val).__name__}); "
              f"keys={list(raw.keys())}", file=sys.stderr)

    print(f"  Could not parse response. Top-level keys: {list(raw.keys())}", file=sys.stderr)
    return []


def fetch_all_pages(token, endpoint):
    """
    Fetch all pages from a paginated ERCOT API endpoint.
    Returns a list of row-dicts.
    """
    headers = {
        "Authorization":             f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": os.environ["ERCOT_SUBSCRIPTION_KEY"],
    }
    # page and size params are required to get actual data rows
    url = f"{API_BASE}/{endpoint}?size=10000&page=1"
    all_rows = []
    page = 1

    while url:
        print(f"  Fetching page {page}...")
        resp = requests.get(url, headers=headers, timeout=90)
        resp.raise_for_status()
        raw = resp.json()

        rows = _rows_from_response(raw)
        all_rows.extend(rows)

        # Follow pagination (_links.next.href)
        links    = raw.get("_links", {})
        next_obj = links.get("next") or links.get("nextPage")
        next_url = (next_obj or {}).get("href") if isinstance(next_obj, dict) else None
        url      = next_url
        page    += 1

    return all_rows


def fetch_lmp(token):
    return fetch_all_pages(token, "np6-788-cd/lmp_node_zone_hub")


# ── Substation mapping ────────────────────────────────────────────────────────

def build_rn_to_substations():
    """
    Map each ERCOT resource-node name → set of ERCOT substation abbreviations.

    Both sources are consulted independently and their keys are unioned so that
    every HTML node matching either source can receive an LMP price:

      Settlement_Points   (RESOURCE_NODE → SUBSTATION)
      Resource_Node_to_Unit (RESOURCE_NODE → UNIT_SUBSTATION)

    Both name spaces overlap with n.ercot values in the HTML, so prices are
    accumulated for all keys produced by either source.

    Returns a dict {resource_node_name: set_of_substation_abbrevs}.
    """
    mapping = defaultdict(set)

    if os.path.exists(SP_CSV):
        with open(SP_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rn  = row.get("RESOURCE_NODE", "").strip()
                sub = row.get("SUBSTATION", "").strip()
                if rn and sub:
                    mapping[rn].add(sub)
    else:
        print(f"  Warning: {SP_CSV} not found", file=sys.stderr)

    if os.path.exists(RN_TO_UNIT_CSV):
        with open(RN_TO_UNIT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rn  = row["RESOURCE_NODE"].strip()
                sub = row["UNIT_SUBSTATION"].strip()
                if rn and sub:
                    mapping[rn].add(sub)
    else:
        print(f"  Warning: {RN_TO_UNIT_CSV} not found", file=sys.stderr)

    return dict(mapping)


# ── Parse ─────────────────────────────────────────────────────────────────────

def build_snapshot(records, rn_to_subs):
    if not records:
        raise ValueError("No records returned from API")

    # Find latest SCED timestamp
    timestamps = sorted({str(r.get("SCEDTimestamp") or "") for r in records} - {""})
    if not timestamps:
        raise ValueError(f"No SCEDTimestamp found. Sample record keys: {list(records[0].keys())}")
    latest = timestamps[-1]
    print(f"  Latest SCED timestamp: {latest}")

    latest_records = [r for r in records if str(r.get("SCEDTimestamp") or "") == latest]
    print(f"  Records at latest timestamp: {len(latest_records)}")

    lmp  = {}
    hub  = {}
    zone = {}

    for r in latest_records:
        name    = str(r.get("settlementPoint") or "").strip()
        price   = r.get("LMP")
        sp_type = str(r.get("settlementPointType") or "").strip()

        if not name or price is None:
            continue
        price = float(price)

        if "Hub" in sp_type or name.startswith("HB_"):
            hub[name] = price
        elif "Load Zone" in sp_type or name.startswith("LZ_"):
            zone[name] = price
        else:
            lmp[name] = price

    # Build substation-keyed lookup: map each resource node → its ERCOT substation
    # abbreviations (from both SP mapping CSVs), then average all resource-node
    # prices at each substation.  The HTML matches lmp_base[n.ercot] where n.ercot
    # is the ERCOT substation abbreviation stored in the v6 matching CSV.
    # Both Settlement_Points.SUBSTATION and Resource_Node_to_Unit.UNIT_SUBSTATION
    # overlap with the HTML node names, so prices are accumulated for all keys.
    sub_prices = defaultdict(list)
    for name, price in lmp.items():
        for sub in rn_to_subs.get(name, set()):
            sub_prices[sub].append(price)

    lmp_base = {sub: round(sum(prices) / len(prices), 2)
                for sub, prices in sub_prices.items()}

    print(f"  Resource nodes: {len(lmp)}, hubs: {len(hub)}, zones: {len(zone)}, "
          f"substations with LMP: {len(lmp_base)}")
    return {
        "timestamp":  latest,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "lmp":      lmp,
        "lmp_base": lmp_base,
        "hub":      hub,
        "zone":     zone,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Authenticating with ERCOT API...")
    token = get_token()
    print("  OK")

    print("Fetching LMPs (np6-788-cd)...")
    records = fetch_lmp(token)
    print(f"  Total records fetched: {len(records)}")

    print("Building resource-node → substation mapping...")
    rn_to_subs = build_rn_to_substations()
    print(f"  Mapped {len(rn_to_subs)} resource nodes to substations")

    print("Parsing response...")
    snapshot = build_snapshot(records, rn_to_subs)

    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "grid_data", "lmp_snapshot.json",
    )
    with open(out, "w") as f:
        json.dump(snapshot, f, separators=(",", ":"))

    kb = os.path.getsize(out) / 1024
    print(f"Saved: {out}  ({kb:.1f} KB)")


if __name__ == "__main__":
    main()
