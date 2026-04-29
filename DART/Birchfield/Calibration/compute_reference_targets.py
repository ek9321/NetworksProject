"""Compute extended metrics for Texas-7k reference networks.

Prints values suitable for pasting into parameter_sweep.py TARGETS dict.
"""

from .network_io import load_texas7k_network
from .network_stats import (
    compute_network_stats,
    compute_degree_distribution,
)


def main() -> None:
    for label, voltage_filter in [("345 kV", [345.0]), ("138 kV", [138.0])]:
        print(f"\n{'='*60}")
        print(f"Texas-7k {label}")
        print(f"{'='*60}")

        net = load_texas7k_network(voltage_filter=voltage_filter)
        stats = compute_network_stats(net)

        print(f"  nodes: {stats.num_nodes}")
        print(f"  edges: {stats.num_edges}")
        print(f"  mn_ratio: {stats.mn_ratio:.4f}")
        print(f"  mean_degree: {stats.degree_stats.mean_degree:.2f}")
        print(f"  max_degree: {stats.degree_stats.max_degree}")
        print(f"  mean_length_km: {stats.length_stats.mean_km:.2f}")
        print(f"  median_length_km: {stats.length_stats.median_km:.2f}")
        print(f"  intersection_rate: {stats.intersection_rate:.4f}")
        print(f"  meshedness: {stats.meshedness:.4f}")
        print(f"  deg1_frac: {stats.deg1_frac:.4f}")
        print(f"  deg2_frac: {stats.deg2_frac:.4f}")
        print(f"  deg3plus_frac: {stats.deg3plus_frac:.4f}")
        print(f"  degree_entropy: {stats.degree_entropy:.4f}")

        print(f"\n  Degree distribution:")
        dist = compute_degree_distribution(net)
        for d, frac in sorted(dist.items()):
            print(f"    degree {d}: {frac:.4f} ({int(frac * stats.num_nodes)} nodes)")


if __name__ == "__main__":
    main()
