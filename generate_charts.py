"""
Generiert alle Diagramme fuer den Bericht.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from tomasulo import Config, TomasuloSimulator, InOrderPipeline, parse_trace

TRACE_DIR = os.path.join(os.path.dirname(__file__), "traces")
CHART_DIR = os.path.join(os.path.dirname(__file__), "charts")
os.makedirs(CHART_DIR, exist_ok=True)

plt.rcParams.update({
    'font.size': 11,
    'figure.figsize': (8, 4.5),
    'figure.dpi': 150,
    'axes.grid': True,
    'grid.alpha': 0.3,
})

def load_trace(filename):
    with open(os.path.join(TRACE_DIR, filename)) as f:
        return f.readlines()

def run_tom(lines, cfg):
    return TomasuloSimulator(cfg).run(lines, silent=True)

def run_io(lines, cfg):
    return InOrderPipeline(cfg).run(lines)


# =========================================================================
# Experiment A: Tomasulo vs. In-Order
# =========================================================================
def chart_experiment_a():
    traces = {
        "Mixed": "experiment_mixed.trace",
        "Parallel": "experiment_parallel.trace",
        "RAW-Kette": "val2_raw_chain.trace",
        "Referenz": "referenz.trace",
    }
    cfg = Config()
    tom_cycles, io_cycles, tom_ipc, io_ipc = [], [], [], []
    labels = []

    for name, tf in traces.items():
        lines = load_trace(tf)
        t = run_tom(lines, cfg)
        i = run_io(lines, cfg)
        labels.append(name)
        tom_cycles.append(t['total_cycles'])
        io_cycles.append(i['total_cycles'])
        tom_ipc.append(t['ipc'])
        io_ipc.append(i['ipc'])

    x = np.arange(len(labels))
    w = 0.35

    # Chart A1: Zyklenvergleich
    fig, ax = plt.subplots()
    bars1 = ax.bar(x - w/2, io_cycles, w, label='In-Order', color='#c0392b', alpha=0.85)
    bars2 = ax.bar(x + w/2, tom_cycles, w, label='Tomasulo', color='#2980b9', alpha=0.85)
    ax.set_ylabel('Gesamtzyklen')
    ax.set_title('Experiment A: Zyklenvergleich Tomasulo vs. In-Order')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.bar_label(bars1, padding=2, fontsize=9)
    ax.bar_label(bars2, padding=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'exp_a_zyklen.png'))
    plt.close()

    # Chart A2: IPC-Vergleich
    fig, ax = plt.subplots()
    bars1 = ax.bar(x - w/2, io_ipc, w, label='In-Order', color='#c0392b', alpha=0.85)
    bars2 = ax.bar(x + w/2, tom_ipc, w, label='Tomasulo', color='#2980b9', alpha=0.85)
    ax.set_ylabel('IPC (Instructions Per Cycle)')
    ax.set_title('Experiment A: IPC-Vergleich Tomasulo vs. In-Order')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.bar_label(bars1, padding=2, fontsize=9, fmt='%.3f')
    ax.bar_label(bars2, padding=2, fontsize=9, fmt='%.3f')
    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'exp_a_ipc.png'))
    plt.close()

    # Speedup-Daten fuer den Bericht
    speedups = [io/tom if tom > 0 else 0 for io, tom in zip(io_cycles, tom_cycles)]
    return list(zip(labels, tom_cycles, io_cycles, tom_ipc, io_ipc, speedups))


# =========================================================================
# Experiment B: RS-Variation
# =========================================================================
def chart_experiment_b():
    rs_counts = [1, 2, 3, 4, 6, 8]
    traces = {"Mixed": "experiment_mixed.trace", "Parallel": "experiment_parallel.trace"}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    results = {}

    for idx, (name, tf) in enumerate(traces.items()):
        lines = load_trace(tf)
        cycles_list, ipc_list, stalls_list = [], [], []

        for rs in rs_counts:
            cfg = Config(alu_rs_count=rs, ls_rs_count=rs)
            t = run_tom(lines, cfg)
            cycles_list.append(t['total_cycles'])
            ipc_list.append(t['ipc'])
            stalls_list.append(t['stall_cycles'])

        results[name] = list(zip(rs_counts, cycles_list, ipc_list, stalls_list))

        ax = axes[idx]
        ax2 = ax.twinx()
        line1 = ax.plot(rs_counts, ipc_list, 'o-', color='#2980b9', label='IPC', linewidth=2)
        line2 = ax2.plot(rs_counts, stalls_list, 's--', color='#e74c3c', label='Stall-Zyklen', linewidth=2)
        ax.set_xlabel('Reservierungsstationen pro FU')
        ax.set_ylabel('IPC', color='#2980b9')
        ax2.set_ylabel('Stall-Zyklen', color='#e74c3c')
        ax.set_title(f'Experiment B: RS-Variation ({name})')
        ax.set_xticks(rs_counts)
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax.legend(lines, labels, loc='center right')

    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'exp_b_rs_variation.png'))
    plt.close()
    return results


# =========================================================================
# Experiment C: Latenz-Variation
# =========================================================================
def chart_experiment_c():
    configs = [
        (1, 1, "ADD/SUB=1, MUL=1, DIV=1"),
        (3, 5, "Standard (MUL=3, DIV=5)"),
        (6, 10, "MUL=6, DIV=10"),
        (10, 20, "MUL=10, DIV=20"),
    ]
    traces = {"Mixed": "experiment_mixed.trace", "Parallel": "experiment_parallel.trace"}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    results = {}

    for idx, (name, tf) in enumerate(traces.items()):
        lines = load_trace(tf)
        labels, cycles_list, ipc_list, stalls_list = [], [], [], []

        for mul_lat, div_lat, label in configs:
            cfg = Config(latency_mul=mul_lat, latency_div=div_lat)
            t = run_tom(lines, cfg)
            labels.append(f"M{mul_lat}/D{div_lat}")
            cycles_list.append(t['total_cycles'])
            ipc_list.append(t['ipc'])
            stalls_list.append(t['stall_cycles'])

        results[name] = list(zip(labels, cycles_list, ipc_list, stalls_list))

        ax = axes[idx]
        x = np.arange(len(labels))
        w = 0.35
        bars1 = ax.bar(x - w/2, cycles_list, w, label='Zyklen', color='#2980b9', alpha=0.85)
        bars2 = ax.bar(x + w/2, stalls_list, w, label='Stalls', color='#e74c3c', alpha=0.85)
        ax.set_xlabel('Latenz-Konfiguration')
        ax.set_ylabel('Zyklen')
        ax.set_title(f'Experiment C: Latenzen ({name})')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=15)
        ax.legend()
        ax.bar_label(bars1, padding=2, fontsize=8)
        ax.bar_label(bars2, padding=2, fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'exp_c_latenzen.png'))
    plt.close()
    return results


# =========================================================================
# Experiment D: RAW-Analyse
# =========================================================================
def chart_experiment_d():
    traces = {
        "Mixed": "experiment_mixed.trace",
        "Parallel": "experiment_parallel.trace",
        "RAW-Kette": "val2_raw_chain.trace",
        "WAR/WAW": "val4_war_waw.trace",
        "LOAD/STORE": "val5_load_store.trace",
    }
    cfg = Config()
    labels, raw_resolved, stalls, io_stalls_list = [], [], [], []
    results = []

    for name, tf in traces.items():
        lines = load_trace(tf)
        t = run_tom(lines, cfg)
        i = run_io(lines, cfg)
        labels.append(name)
        raw_resolved.append(t['raw_resolved'])
        stalls.append(t['stall_cycles'])
        io_s = i.get('raw_stalls', 0)
        io_stalls_list.append(io_s)
        ratio = t['raw_resolved'] / (t['raw_resolved'] + t['stall_cycles']) if (t['raw_resolved'] + t['stall_cycles']) > 0 else 0
        results.append((name, t['instructions'], t['raw_resolved'], t['stall_cycles'], io_s, ratio))

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(labels))
    w = 0.25
    bars1 = ax.bar(x - w, raw_resolved, w, label='RAW aufgelöst (Tomasulo)', color='#27ae60', alpha=0.85)
    bars2 = ax.bar(x, stalls, w, label='Struct. Stalls (Tomasulo)', color='#e74c3c', alpha=0.85)
    bars3 = ax.bar(x + w, io_stalls_list, w, label='RAW-Stalls (In-Order)', color='#f39c12', alpha=0.85)
    ax.set_xlabel('Trace')
    ax.set_ylabel('Anzahl')
    ax.set_title('Experiment D: Aufgelöste RAW-Abhängigkeiten vs. Stalls')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15)
    ax.legend()
    ax.bar_label(bars1, padding=2, fontsize=9)
    ax.bar_label(bars2, padding=2, fontsize=9)
    ax.bar_label(bars3, padding=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'exp_d_raw_analyse.png'))
    plt.close()
    return results


# =========================================================================
# Validierungs-Timeline-Diagramm
# =========================================================================
def chart_validation_timeline():
    """Gantt-aehnliches Diagramm fuer den Beispiel-Trace."""
    lines = load_trace("referenz.trace")
    cfg = Config()
    sim = TomasuloSimulator(cfg)
    stats = sim.run(lines, silent=True)
    log = sorted(stats['instruction_log'], key=lambda e: e['index'])

    fig, ax = plt.subplots(figsize=(12, 4))
    colors = {'Issue': '#3498db', 'Execute': '#e67e22', 'Write': '#2ecc71', 'Wait': '#bdc3c7'}

    for i, entry in enumerate(log):
        y = len(log) - 1 - i
        iss = entry['issue_cycle']
        ex_start = entry['exec_start']
        wr = entry['write_cycle']

        # Issue (1 Zyklus)
        ax.barh(y, 1, left=iss-0.5, height=0.6, color=colors['Issue'], edgecolor='white')
        # Wait (zwischen Issue und Exec)
        if ex_start > iss + 1:
            ax.barh(y, ex_start - iss - 1, left=iss+0.5, height=0.6, color=colors['Wait'], edgecolor='white')
        # Execute
        if wr > ex_start:
            ax.barh(y, wr - ex_start, left=ex_start-0.5, height=0.6, color=colors['Execute'], edgecolor='white')
        # Write (1 Zyklus)
        ax.barh(y, 1, left=wr-0.5, height=0.6, color=colors['Write'], edgecolor='white')

    ax.set_yticks(range(len(log)))
    ax.set_yticklabels([e['instr'][:25] for e in reversed(log)], fontsize=9)
    ax.set_xlabel('Zyklus')
    ax.set_title('Validierung: Instruktions-Timeline (Referenz-Trace)')
    ax.set_xticks(range(0, stats['total_cycles'] + 2))

    # Legende
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=l) for l, c in colors.items()]
    ax.legend(handles=legend_elements, loc='lower right')

    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'val_timeline.png'))
    plt.close()


# =========================================================================
# Architektur-Diagramm
# =========================================================================
def chart_architecture():
    """Vereinfachtes Architekturdiagramm des Simulators."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis('off')
    ax.set_title('Architektur des Tomasulo-Simulators', fontsize=14, fontweight='bold', pad=15)

    box_style = dict(boxstyle='round,pad=0.4', facecolor='#ebf5fb', edgecolor='#2980b9', linewidth=2)
    box_style2 = dict(boxstyle='round,pad=0.4', facecolor='#fef9e7', edgecolor='#f39c12', linewidth=2)
    box_style3 = dict(boxstyle='round,pad=0.4', facecolor='#eafaf1', edgecolor='#27ae60', linewidth=2)
    cdb_style = dict(boxstyle='round,pad=0.3', facecolor='#fdedec', edgecolor='#e74c3c', linewidth=2.5)

    # Instruction Queue
    ax.text(1.5, 6.2, 'Instruktions-Queue\n(In-Order Issue)', ha='center', va='center',
            fontsize=10, bbox=box_style)

    # ALU RS
    ax.text(3, 4.5, 'ALU-RS\n(4 Stationen)', ha='center', va='center',
            fontsize=10, bbox=box_style2)
    # LS RS
    ax.text(7, 4.5, 'Load/Store-RS\n(3 Stationen)', ha='center', va='center',
            fontsize=10, bbox=box_style2)

    # FUs
    ax.text(3, 2.8, 'ALU\n(ADD/SUB/MUL/DIV)', ha='center', va='center',
            fontsize=9, bbox=box_style3)
    ax.text(7, 2.8, 'Load/Store Unit', ha='center', va='center',
            fontsize=9, bbox=box_style3)

    # Register File
    ax.text(1.2, 3.5, 'Register-\nfile\n(R0-R7)', ha='center', va='center',
            fontsize=9, bbox=box_style)

    # Memory
    ax.text(8.8, 2.8, 'Speicher\n(1024 W)', ha='center', va='center',
            fontsize=9, bbox=box_style)

    # CDB
    ax.text(5, 1.2, 'Common Data Bus (CDB)', ha='center', va='center',
            fontsize=11, fontweight='bold', bbox=cdb_style)

    # Arrows
    arrow_kw = dict(arrowstyle='->', color='#555', lw=1.5)
    ax.annotate('', xy=(3, 5.1), xytext=(1.5, 5.7), arrowprops=arrow_kw)
    ax.annotate('', xy=(7, 5.1), xytext=(1.5, 5.7), arrowprops=arrow_kw)
    ax.annotate('', xy=(3, 3.3), xytext=(3, 3.9), arrowprops=arrow_kw)
    ax.annotate('', xy=(7, 3.3), xytext=(7, 3.9), arrowprops=arrow_kw)
    ax.annotate('', xy=(8.0, 2.8), xytext=(7.7, 2.8), arrowprops=arrow_kw)
    ax.annotate('', xy=(5, 1.7), xytext=(3, 2.3), arrowprops=arrow_kw)
    ax.annotate('', xy=(5, 1.7), xytext=(7, 2.3), arrowprops=arrow_kw)
    # CDB back to RS and RegFile
    ax.annotate('', xy=(3, 3.9), xytext=(4.2, 1.5), arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5, ls='--'))
    ax.annotate('', xy=(7, 3.9), xytext=(5.8, 1.5), arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5, ls='--'))
    ax.annotate('', xy=(1.2, 3.0), xytext=(4.0, 1.2), arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5, ls='--'))
    # Issue arrow to regfile
    ax.annotate('', xy=(1.2, 4.0), xytext=(1.5, 5.7), arrowprops=dict(arrowstyle='->', color='#555', lw=1, ls=':'))

    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, 'architektur.png'))
    plt.close()


# =========================================================================
# Alle Validierungs-Timelines als Tabelle
# =========================================================================
def generate_validation_data():
    """Generiert Validierungsdaten fuer den Bericht."""
    val_traces = [
        ("val1_no_deps.trace", "Keine Abhängigkeiten"),
        ("val2_raw_chain.trace", "RAW-Kette"),
        ("val3_structural_stall.trace", "Struktureller Stall"),
        ("val4_war_waw.trace", "WAR/WAW-Auflösung"),
        ("val5_load_store.trace", "LOAD/STORE + CDB"),
    ]
    cfg = Config()
    results = []
    for tf, desc in val_traces:
        lines = load_trace(tf)
        sim = TomasuloSimulator(cfg)
        stats = sim.run(lines, silent=True)
        io = InOrderPipeline(cfg).run(lines)
        log = sorted(stats['instruction_log'], key=lambda e: e['index'])
        results.append({
            "file": tf,
            "desc": desc,
            "stats": stats,
            "io_stats": io,
            "log": log,
        })
    return results


# =========================================================================
# Main
# =========================================================================
if __name__ == "__main__":
    print("Generiere Diagramme...")

    print("  Architektur...")
    chart_architecture()

    print("  Validierungs-Timeline...")
    chart_validation_timeline()

    print("  Experiment A...")
    res_a = chart_experiment_a()
    for r in res_a:
        print(f"    {r[0]:15s}: Tom={r[1]:3d} IO={r[2]:3d} Speedup={r[5]:.2f}x")

    print("  Experiment B...")
    res_b = chart_experiment_b()

    print("  Experiment C...")
    res_c = chart_experiment_c()

    print("  Experiment D...")
    res_d = chart_experiment_d()

    print(f"\nAlle Diagramme gespeichert in: {CHART_DIR}/")
    print("Dateien:", os.listdir(CHART_DIR))
