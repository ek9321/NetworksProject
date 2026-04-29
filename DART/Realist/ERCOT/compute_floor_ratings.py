"""
Compute physics-based line ratings from a floor SCED run.

Reads line_detail.csv from a floor run (all ratings 999,999 MVA),
computes max absolute flow per line, and outputs a CSV of minimum
ratings: min(max_flow × margin, cap).

Usage:
    python compute_floor_ratings.py <line_detail.csv> <output.csv> [--margin 1.1] [--cap 800]
"""

import argparse
import csv
from collections import defaultdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("line_detail", help="Path to line_detail.csv from floor run")
    parser.add_argument("output", help="Output CSV path (UID, MinRating)")
    parser.add_argument("--margin", type=float, default=1.1,
                        help="Margin factor above max flow (default 1.1)")
    parser.add_argument("--cap", type=float, default=800,
                        help="Max rating cap in MVA (default 800)")
    parser.add_argument("--base", type=float, default=250,
                        help="Only output lines where flow exceeds this (default 250)")
    args = parser.parse_args()

    # Compute max absolute flow per line
    max_flow = defaultdict(float)
    with open(args.line_detail, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            uid = row['Line']
            flow = abs(float(row['Flow']))
            if flow > max_flow[uid]:
                max_flow[uid] = flow

    # Compute min ratings for overloaded lines
    results = []
    for uid, flow in sorted(max_flow.items()):
        if flow > args.base:
            rating = min(round(flow * args.margin, 1), args.cap)
            results.append((uid, rating, round(flow, 1)))

    # Write output
    with open(args.output, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['UID', 'MinRating', 'MaxFlow'])
        for uid, rating, flow in results:
            writer.writerow([uid, rating, flow])

    print(f"Lines where max flow > {args.base} MVA: {len(results)}")
    print(f"Ratings set to min(flow × {args.margin}, {args.cap})")
    if results:
        flows = [r[2] for r in results]
        print(f"Flow range: {min(flows):.0f} – {max(flows):.0f} MVA")
        ratings = [r[1] for r in results]
        print(f"Rating range: {min(ratings):.0f} – {max(ratings):.0f} MVA")


if __name__ == "__main__":
    main()
