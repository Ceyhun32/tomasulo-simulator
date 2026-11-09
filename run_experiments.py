"""
Experiment-Runner fuer den Tomasulo-Pipeline-Simulator
======================================================
Fuehrt vier Experimente durch:
  a) Vergleich Tomasulo vs. In-Order
  b) Variation der RS-Anzahl
  c) Variation der Latenzen
  d) Analyse aufgeloester Abhaengigkeiten
"""

import os
import sys
from tomasulo import Config, TomasuloSimulator, InOrderPipeline

TRACE_DIR = os.path.join(os.path.dirname(__file__), "traces")


def load_trace(filename: str):
    path = os.path.join(TRACE_DIR, filename)
    with open(path) as f:
        return f.readlines()


def run_tomasulo(trace_lines, config: Config) -> dict:
    sim = TomasuloSimulator(config)
    return sim.run(trace_lines, silent=True)


def run_in_order(trace_lines, config: Config) -> dict:
    pipe = InOrderPipeline(config)
    return pipe.run(trace_lines)


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def experiment_a():
    """Vergleich Tomasulo vs. In-Order-Pipeline."""
    print_header("Experiment A: Tomasulo vs. In-Order-Pipeline")

    traces = ["experiment_mixed.trace", "experiment_parallel.trace"]
    config = Config()

    print(f"\n  {'Trace':<28s} | {'Tomasulo':>10s} | {'In-Order':>10s} | "
          f"{'Speedup':>8s} | {'IPC(T)':>7s} | {'IPC(IO)':>7s}")
    print("  " + "-" * 85)

    results = []
    for tf in traces:
        lines = load_trace(tf)
        tom = run_tomasulo(lines, config)
        io = run_in_order(lines, config)
        speedup = io["total_cycles"] / tom["total_cycles"] if tom["total_cycles"] > 0 else 0
        print(f"  {tf:<28s} | {tom['total_cycles']:>10d} | {io['total_cycles']:>10d} | "
              f"{speedup:>7.2f}x | {tom['ipc']:>7.4f} | {io['ipc']:>7.4f}")
        results.append({"trace": tf, "tomasulo": tom, "in_order": io, "speedup": speedup})

    return results


def experiment_b():
    """Variation der RS-Anzahl."""
    print_header("Experiment B: Variation der Reservierungsstationen")

    rs_counts = [2, 4, 8]
    traces = ["experiment_mixed.trace", "experiment_parallel.trace"]

    results = []
    for tf in traces:
        lines = load_trace(tf)
        print(f"\n  Trace: {tf}")
        print(f"  {'RS/FU':>6s} | {'Zyklen':>8s} | {'IPC':>7s} | "
              f"{'Stalls':>7s} | {'ALU%':>6s} | {'LS%':>6s}")
        print("  " + "-" * 55)

        for rs in rs_counts:
            config = Config(alu_rs_count=rs, ls_rs_count=rs)
            tom = run_tomasulo(lines, config)
            print(f"  {rs:>6d} | {tom['total_cycles']:>8d} | {tom['ipc']:>7.4f} | "
                  f"{tom['stall_cycles']:>7d} | {tom['alu_utilization_pct']:>5.1f}% | "
                  f"{tom['ls_utilization_pct']:>5.1f}%")
            results.append({"trace": tf, "rs_count": rs, **tom})

    return results


def experiment_c():
    """Variation der FU-Latenzen."""
    print_header("Experiment C: Variation der Latenzen")

    latency_configs = [
        {"name": "Standard",  "mul": 3,  "div": 5},
        {"name": "Hoch",      "mul": 6,  "div": 10},
        {"name": "Sehr hoch", "mul": 10, "div": 20},
    ]
    traces = ["experiment_mixed.trace", "experiment_parallel.trace"]

    results = []
    for tf in traces:
        lines = load_trace(tf)
        print(f"\n  Trace: {tf}")
        print(f"  {'Konfig':<12s} | {'MUL':>4s} | {'DIV':>4s} | "
              f"{'Zyklen':>8s} | {'IPC':>7s} | {'Stalls':>7s} | {'RAW':>5s}")
        print("  " + "-" * 65)

        for lc in latency_configs:
            config = Config(latency_mul=lc["mul"], latency_div=lc["div"])
            tom = run_tomasulo(lines, config)
            print(f"  {lc['name']:<12s} | {lc['mul']:>4d} | {lc['div']:>4d} | "
                  f"{tom['total_cycles']:>8d} | {tom['ipc']:>7.4f} | "
                  f"{tom['stall_cycles']:>7d} | {tom['raw_resolved']:>5d}")
            results.append({"trace": tf, **lc, **tom})

    return results


def experiment_d():
    """Analyse der aufgeloesten Abhaengigkeiten."""
    print_header("Experiment D: Aufgeloeste RAW-Abhaengigkeiten")

    traces = ["experiment_mixed.trace", "experiment_parallel.trace",
              "val2_raw_chain.trace", "val4_war_waw.trace"]
    config = Config()

    print(f"\n  {'Trace':<28s} | {'Instr':>6s} | {'RAW aufg.':>10s} | "
          f"{'Stalls':>7s} | {'IO-Stalls':>10s} | {'Anteil aufg.':>12s}")
    print("  " + "-" * 85)

    results = []
    for tf in traces:
        lines = load_trace(tf)
        tom = run_tomasulo(lines, config)
        io = run_in_order(lines, config)

        io_stalls = io.get("raw_stalls", 0)
        ratio = (tom["raw_resolved"] / (tom["raw_resolved"] + tom["stall_cycles"])
                 if (tom["raw_resolved"] + tom["stall_cycles"]) > 0 else 0)

        print(f"  {tf:<28s} | {tom['instructions']:>6d} | {tom['raw_resolved']:>10d} | "
              f"{tom['stall_cycles']:>7d} | {io_stalls:>10d} | {ratio:>11.1%}")
        results.append({"trace": tf, "tomasulo": tom, "in_order": io, "ratio": ratio})

    return results


def run_validation():
    """Fuehrt alle Validierungs-Traces aus."""
    print_header("VALIDIERUNG")

    val_traces = [
        ("val1_no_deps.trace", "Keine Abhaengigkeiten"),
        ("val2_raw_chain.trace", "RAW-Abhaengigkeitskette"),
        ("val3_structural_stall.trace", "Struktureller Stall"),
        ("val4_war_waw.trace", "WAR/WAW-Aufloesung"),
        ("val5_load_store.trace", "LOAD/STORE mit CDB"),
    ]

    for tf, desc in val_traces:
        print(f"\n--- {desc} ({tf}) ---")
        lines = load_trace(tf)
        sim = TomasuloSimulator(Config())
        sim.run(lines, silent=False)
        sim.print_final_stats()


def main():
    print("Tomasulo-Pipeline-Simulator: Experimente und Validierung")
    print("=" * 70)

    # Validierung
    run_validation()

    # Experimente
    experiment_a()
    experiment_b()
    experiment_c()
    experiment_d()

    print("\n\nAlle Experimente abgeschlossen.")


if __name__ == "__main__":
    main()
