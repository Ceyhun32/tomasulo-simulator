"""
Tomasulo-Pipeline-Simulator
============================
Implementierung des Tomasulo-Algorithmus fuer eine
in-order-issuende, out-of-order-ausfuehrende und
out-of-order-abschliessende Pipeline.

Autor: Ceyhun Akca
Hochschule Kempten
"""

import re
import sys
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Konfigurierbare Parameter des Simulators."""
    alu_rs_count: int = 4          # Anzahl ALU-Reservierungsstationen
    ls_rs_count: int = 3           # Anzahl Load/Store-Reservierungsstationen
    latency_add: int = 1           # Latenz ADD/SUB
    latency_mul: int = 3           # Latenz MUL
    latency_div: int = 5           # Latenz DIV
    latency_ls: int = 2            # Latenz LOAD/STORE
    num_registers: int = 8         # Anzahl Register (R0-R7)
    memory_size: int = 1024        # Speichergroesse in Woertern

    def get_latency(self, op: str) -> int:
        """Gibt die Latenz fuer eine Operation zurueck."""
        op = op.upper()
        if op in ("ADD", "SUB"):
            return self.latency_add
        elif op == "MUL":
            return self.latency_mul
        elif op == "DIV":
            return self.latency_div
        elif op in ("LOAD", "STORE"):
            return self.latency_ls
        else:
            raise ValueError(f"Unbekannte Operation: {op}")

    @staticmethod
    def from_dict(d: dict) -> 'Config':
        """Erstellt Config aus einem Dictionary (z.B. aus JSON-Datei)."""
        c = Config()
        for k, v in d.items():
            if hasattr(c, k):
                setattr(c, k, v)
        return c

    @staticmethod
    def from_json(path: str) -> 'Config':
        with open(path) as f:
            return Config.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# Instruction representation
# ---------------------------------------------------------------------------

class OpType(Enum):
    ALU = "ALU"
    LOAD_STORE = "LS"

@dataclass
class Instruction:
    """Repraesentiert eine geparste Instruktion."""
    op: str               # ADD, SUB, MUL, DIV, LOAD, STORE
    rd: int               # Zielregister (fuer STORE: Basisregister der Adresse)
    rs1: int              # Erster Quelloperand / Basisregister bei LOAD
    rs2: int = -1         # Zweiter Quelloperand (nicht bei LOAD/STORE)
    offset: int = 0       # Offset fuer LOAD/STORE
    raw_text: str = ""    # Originaltext der Instruktion
    index: int = 0        # Laufende Nummer im Trace

    @property
    def op_type(self) -> OpType:
        if self.op in ("LOAD", "STORE"):
            return OpType.LOAD_STORE
        return OpType.ALU

    def __str__(self):
        return self.raw_text if self.raw_text else f"{self.op} R{self.rd}, R{self.rs1}, R{self.rs2}"


# ---------------------------------------------------------------------------
# Trace Parser
# ---------------------------------------------------------------------------

def parse_trace(lines: List[str]) -> List:
    """
    Parst eine Trace-Datei.
    Gibt eine Liste zurueck, die Instruction-Objekte und
    Kommando-Strings ('v', 's', 'h', 'i') enthaelt.
    """
    result = []
    instr_count = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # Ausgabebefehle: einzelne Buchstaben v, s, h, i
        if line.lower() in ("v", "s", "h", "i"):
            result.append(line.lower())
            continue

        # Instruktion parsen
        instr = _parse_instruction(line, instr_count)
        if instr:
            instr_count += 1
            result.append(instr)
        else:
            print(f"WARNUNG: Konnte Zeile nicht parsen: '{line}'")

    return result


def _parse_instruction(line: str, index: int) -> Optional[Instruction]:
    """Parst eine einzelne Instruktionszeile."""
    # Kommentare entfernen: # oder // bis Zeilenende
    line = re.sub(r'(//|#).*$', '', line).strip()
    # Klammer-Kommentare entfernen (aber nicht Register-Klammern wie 4(R2))
    line = re.sub(r'\((?![Rr]\d).*?\)', '', line).strip()
    
    # Normalisieren: Kommas und Leerzeichen
    parts = re.split(r'[\s,]+', line)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return None

    op = parts[0].upper()

    if op in ("ADD", "SUB", "MUL", "DIV"):
        # Format: OP Rd, Rs1, Rs2
        if len(parts) < 4:
            return None
        rd = _parse_register(parts[1])
        rs1 = _parse_register(parts[2])
        rs2 = _parse_register(parts[3])
        if rd is None or rs1 is None or rs2 is None:
            return None
        return Instruction(op=op, rd=rd, rs1=rs1, rs2=rs2,
                           raw_text=line, index=index)

    elif op == "LOAD":
        # Format: LOAD Rd, offset(Rs)
        if len(parts) < 3:
            return None
        rd = _parse_register(parts[1])
        offset, rs = _parse_offset_reg(parts[2])
        if rd is None or rs is None:
            return None
        return Instruction(op=op, rd=rd, rs1=rs, offset=offset,
                           raw_text=line, index=index)

    elif op == "STORE":
        # Format: STORE Rs, offset(Rd)
        # Rs = Wert der gespeichert wird, Rd = Basisregister fuer Adresse
        if len(parts) < 3:
            return None
        rs = _parse_register(parts[1])
        offset, rd = _parse_offset_reg(parts[2])
        if rs is None or rd is None:
            return None
        # Intern: rd = Basisregister (Adresse), rs1 = Quellregister (Wert)
        # STORE hat kein Zielregister im klassischen Sinne
        return Instruction(op=op, rd=rd, rs1=rs, offset=offset,
                           raw_text=line, index=index)

    return None


def _parse_register(s: str) -> Optional[int]:
    """Parst ein Register wie 'R3' und gibt die Nummer zurueck."""
    s = s.strip().rstrip(',')
    m = re.match(r'[Rr](\d+)', s)
    return int(m.group(1)) if m else None


def _parse_offset_reg(s: str) -> Tuple[int, Optional[int]]:
    """Parst 'offset(Rs)' und gibt (offset, register_nr) zurueck."""
    m = re.match(r'(-?\d+)\(([Rr]\d+)\)', s.strip())
    if m:
        offset = int(m.group(1))
        reg = _parse_register(m.group(2))
        return offset, reg
    return 0, None


# ---------------------------------------------------------------------------
# Reservation Station
# ---------------------------------------------------------------------------

@dataclass
class ReservationStation:
    """Eine Reservierungsstation."""
    name: str             # z.B. "ALU0", "LS1"
    rs_type: OpType       # ALU oder LOAD_STORE
    busy: bool = False
    op: str = ""          # Operation
    vj: int = 0           # Wert Operand 1
    vk: int = 0           # Wert Operand 2
    qj: str = ""          # Tag fuer Operand 1 (leer = Wert verfuegbar)
    qk: str = ""          # Tag fuer Operand 2 (leer = Wert verfuegbar)
    dest_reg: int = -1    # Zielregister (-1 fuer STORE)
    offset: int = 0       # Offset fuer LOAD/STORE
    result: int = 0       # Berechnetes Ergebnis
    remaining_cycles: int = 0   # Verbleibende Ausfuehrungszyklen
    executing: bool = False     # Wird gerade ausgefuehrt?
    ready_to_write: bool = False  # Bereit fuer CDB-Broadcast?
    instruction: Optional[Instruction] = None
    issued_cycle: int = 0       # Zyklus des Issue
    exec_start_cycle: int = 0   # Zyklus des Ausfuehrungsbeginns
    write_cycle: int = 0        # Zyklus des CDB-Writes

    def clear(self):
        """Setzt die RS auf den Ausgangszustand zurueck."""
        self.busy = False
        self.op = ""
        self.vj = 0
        self.vk = 0
        self.qj = ""
        self.qk = ""
        self.dest_reg = -1
        self.offset = 0
        self.result = 0
        self.remaining_cycles = 0
        self.executing = False
        self.ready_to_write = False
        self.instruction = None
        self.issued_cycle = 0
        self.exec_start_cycle = 0
        self.write_cycle = 0

    def operands_ready(self) -> bool:
        return self.qj == "" and self.qk == ""

    def status_str(self) -> str:
        if not self.busy:
            return f"  {self.name:6s} | frei"
        state = "WAIT"
        if self.ready_to_write:
            state = "WRITE"
        elif self.executing:
            state = f"EXEC({self.remaining_cycles})"
        elif not self.operands_ready():
            state = "WAIT"
        else:
            state = "READY"
        
        qj_str = f"Qj={self.qj}" if self.qj else f"Vj={self.vj}"
        qk_str = f"Qk={self.qk}" if self.qk else f"Vk={self.vk}"
        dest = f"R{self.dest_reg}" if self.dest_reg >= 0 else "-"
        return (f"  {self.name:6s} | {state:9s} | {self.op:5s} | "
                f"{qj_str:12s} | {qk_str:12s} | Dest={dest}")


# ---------------------------------------------------------------------------
# Tomasulo Simulator
# ---------------------------------------------------------------------------

class TomasuloSimulator:
    """
    Hauptklasse des Tomasulo-Simulators.
    
    Phasenreihenfolge pro Zyklus:
      1. Write Result (CDB-Broadcast)
      2. Execute (Ausfuehrung starten/fortsetzen)
      3. Issue (naechste Instruktion zuweisen)
    """

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self._init_hardware()
        self._init_stats()
        self.verbose = False
        self.output_lines: List[str] = []

    def _init_hardware(self):
        """Initialisiert alle Hardware-Komponenten."""
        cfg = self.config
        
        # Reservierungsstationen
        self.alu_stations: List[ReservationStation] = [
            ReservationStation(name=f"ALU{i}", rs_type=OpType.ALU)
            for i in range(cfg.alu_rs_count)
        ]
        self.ls_stations: List[ReservationStation] = [
            ReservationStation(name=f"LS{i}", rs_type=OpType.LOAD_STORE)
            for i in range(cfg.ls_rs_count)
        ]
        self.all_stations = self.alu_stations + self.ls_stations

        # Registerfile: Wert und Tag (welche RS den Wert produzieren wird)
        self.reg_values = [i for i in range(cfg.num_registers)]  # R_i = i
        self.reg_tags = [""] * cfg.num_registers  # leer = Wert aktuell

        # Hauptspeicher
        self.memory = [i * 10 for i in range(cfg.memory_size)]

        # Tracking: RS deren Operand in diesem Zyklus via CDB ankam
        # (duerfen erst im naechsten Zyklus mit Ausfuehrung beginnen)
        self._cdb_updated_rs: set = set()

    def _init_stats(self):
        """Setzt die Statistik-Zaehler zurueck."""
        self.cycle = 0
        self.stall_cycles = 0
        self.raw_resolved = 0  # Aufgeloeste RAW-Abhaengigkeiten
        self.instructions_issued = 0
        self.instructions_completed = 0
        # Busy-Zyklen pro RS-Typ fuer Auslastungsberechnung
        self.alu_busy_cycles = 0
        self.ls_busy_cycles = 0
        # Instruction log for timeline
        self.instruction_log: List[Dict] = []

    def _log(self, msg: str):
        """Gibt eine Nachricht aus (wenn verbose) und speichert sie."""
        self.output_lines.append(msg)
        print(msg)

    def _log_verbose(self, msg: str):
        """Gibt eine Nachricht nur im Verbose-Modus aus."""
        if self.verbose:
            self._log(msg)

    # ------------------------------------------------------------------
    # Phase 1: Write Result (CDB-Broadcast)
    # ------------------------------------------------------------------

    def _phase_write_result(self):
        """
        Waehlt eine fertig ausgefuehrte RS und broadcastet ihr Ergebnis
        auf dem Common Data Bus (CDB). Maximal ein CDB-Broadcast pro Zyklus.
        STOREs brauchen den CDB nicht und werden separat abgeschlossen.
        """
        # 1) Alle fertigen STOREs abschliessen (brauchen kein CDB)
        stores = [rs for rs in self.all_stations
                  if rs.busy and rs.ready_to_write and rs.op == "STORE"]
        for store_rs in stores:
            self._complete_store(store_rs)

        # 2) Ein CDB-Broadcast (nicht-STORE) — Liste NEU aufbauen nach STORE-Clearing
        cdb_candidates = [rs for rs in self.all_stations
                          if rs.busy and rs.ready_to_write and rs.op != "STORE"]
        if cdb_candidates:
            cdb_candidates.sort(key=lambda rs: rs.issued_cycle)
            self._cdb_broadcast(cdb_candidates[0])

    def _complete_store(self, rs: ReservationStation):
        """Schliesst eine STORE-Instruktion ab (ohne CDB)."""
        self._compute_result(rs)
        rs.write_cycle = self.cycle

        addr = rs.vk + rs.offset
        if 0 <= addr < self.config.memory_size:
            self.memory[addr] = rs.vj

        self._log_verbose(
            f"  [Zyklus {self.cycle}] STORE abgeschlossen: "
            f"Speicher[{addr}] = {rs.vj} (von {rs.name})")

        for entry in self.instruction_log:
            if entry.get("rs_name") == rs.name and entry.get("write_cycle") == 0:
                entry["write_cycle"] = self.cycle
                break

        self.instructions_completed += 1
        rs.clear()

    def _cdb_broadcast(self, rs: ReservationStation):
        """Broadcastet das Ergebnis einer RS auf dem CDB."""
        self._compute_result(rs)
        rs.write_cycle = self.cycle

        tag = rs.name
        value = rs.result

        self._log_verbose(
            f"  [Zyklus {self.cycle}] CDB-Broadcast: {tag} -> "
            f"R{rs.dest_reg} = {value}")

        # Alle RS aktualisieren, die auf dieses Tag warten
        for other in self.all_stations:
            if other.busy and other.qj == tag:
                other.vj = value
                other.qj = ""
                self.raw_resolved += 1
                self._cdb_updated_rs.add(other.name)
            if other.busy and other.qk == tag:
                other.vk = value
                other.qk = ""
                self.raw_resolved += 1
                self._cdb_updated_rs.add(other.name)

        # Registerfile aktualisieren
        if rs.dest_reg >= 0:
            if self.reg_tags[rs.dest_reg] == tag:
                self.reg_values[rs.dest_reg] = value
                self.reg_tags[rs.dest_reg] = ""

        for entry in self.instruction_log:
            if entry.get("rs_name") == rs.name and entry.get("write_cycle") == 0:
                entry["write_cycle"] = self.cycle
                break

        self.instructions_completed += 1
        rs.clear()

    def _compute_result(self, rs: ReservationStation):
        """Berechnet das Ergebnis einer Instruktion."""
        op = rs.op
        if op == "ADD":
            rs.result = rs.vj + rs.vk
        elif op == "SUB":
            rs.result = rs.vj - rs.vk
        elif op == "MUL":
            rs.result = rs.vj * rs.vk
        elif op == "DIV":
            rs.result = int(rs.vj / rs.vk) if rs.vk != 0 else 0  # Truncation (wie Hardware)
        elif op == "LOAD":
            addr = rs.vj + rs.offset
            if 0 <= addr < self.config.memory_size:
                rs.result = self.memory[addr]
            else:
                rs.result = 0
        elif op == "STORE":
            pass  # STORE hat kein Berechnungsergebnis

    # ------------------------------------------------------------------
    # Phase 2: Execute
    # ------------------------------------------------------------------

    def _phase_execute(self):
        """
        Fuehrt alle RS weiter aus:
        - Bereits ausfuehrende RS: remaining_cycles verringern
        - Bereite RS: Ausfuehrung starten
        """
        for rs in self.all_stations:
            if not rs.busy:
                continue

            # Bereits in Ausfuehrung
            if rs.executing:
                rs.remaining_cycles -= 1
                if rs.remaining_cycles == 0:
                    rs.executing = False
                    rs.ready_to_write = True
                continue

            # Noch nicht ausfuehrend, aber bereit zum Starten?
            # WICHTIG: RS die gerade in diesem Zyklus ihren Operanden via CDB
            # erhalten haben, duerfen erst im naechsten Zyklus starten
            # (Hennessy & Patterson: 1-Zyklus-Verzoegerung nach CDB-Capture)
            if (rs.operands_ready() and not rs.ready_to_write
                    and rs.name not in self._cdb_updated_rs):
                latency = self.config.get_latency(rs.op)
                rs.remaining_cycles = latency
                rs.executing = True
                rs.exec_start_cycle = self.cycle

                # Update log
                for entry in self.instruction_log:
                    if entry.get("rs_name") == rs.name and entry.get("exec_start") == 0:
                        entry["exec_start"] = self.cycle
                        break

                self._log_verbose(
                    f"  [Zyklus {self.cycle}] Ausfuehrung gestartet: "
                    f"{rs.name} ({rs.op}), Latenz={latency}")

                # Sofort dekrementieren (dieser Zyklus zaehlt als erster Ausfuehrungszyklus)
                rs.remaining_cycles -= 1
                if rs.remaining_cycles == 0:
                    rs.executing = False
                    rs.ready_to_write = True

    # ------------------------------------------------------------------
    # Phase 3: Issue
    # ------------------------------------------------------------------

    def _try_issue(self, instr: Instruction) -> bool:
        """
        Versucht eine Instruktion zu issuen.
        Gibt True zurueck wenn erfolgreich, False bei strukturellem Stall.
        """
        # Passende RS finden
        stations = (self.alu_stations if instr.op_type == OpType.ALU
                     else self.ls_stations)
        
        free_rs = None
        for rs in stations:
            if not rs.busy:
                free_rs = rs
                break

        if free_rs is None:
            # Struktureller Stall: keine freie RS
            self.stall_cycles += 1
            self._log_verbose(
                f"  [Zyklus {self.cycle}] STALL: Keine freie "
                f"{instr.op_type.value}-RS fuer {instr}")
            return False

        # RS belegen
        free_rs.busy = True
        free_rs.op = instr.op
        free_rs.instruction = instr
        free_rs.issued_cycle = self.cycle
        free_rs.offset = instr.offset

        if instr.op in ("ADD", "SUB", "MUL", "DIV"):
            # Zwei Quelloperanden: rs1 und rs2
            free_rs.dest_reg = instr.rd
            self._read_operand_j(free_rs, instr.rs1)
            self._read_operand_k(free_rs, instr.rs2)
            # Register-Renaming: Zielregister zeigt auf diese RS
            self.reg_tags[instr.rd] = free_rs.name

        elif instr.op == "LOAD":
            # Quelloperand: rs1 (Basisregister)
            free_rs.dest_reg = instr.rd
            self._read_operand_j(free_rs, instr.rs1)
            free_rs.qk = ""  # Kein zweiter Operand
            free_rs.vk = 0
            # Register-Renaming
            self.reg_tags[instr.rd] = free_rs.name

        elif instr.op == "STORE":
            # Quelloperand 1 (Vj): Wert der gespeichert wird (rs1)
            # Quelloperand 2 (Vk): Basisregister fuer Adresse (rd)
            free_rs.dest_reg = -1  # STORE hat kein Zielregister
            self._read_operand_j(free_rs, instr.rs1)  # Wert
            self._read_operand_k(free_rs, instr.rd)    # Adresse
        
        self.instructions_issued += 1

        # Instruction log
        self.instruction_log.append({
            "index": instr.index,
            "instr": str(instr),
            "rs_name": free_rs.name,
            "issue_cycle": self.cycle,
            "exec_start": 0,
            "write_cycle": 0,
        })

        self._log_verbose(
            f"  [Zyklus {self.cycle}] Issue: {instr} -> {free_rs.name}")

        return True

    def _read_operand_j(self, rs: ReservationStation, reg: int):
        """Liest Operand J aus dem Registerfile oder setzt Tag."""
        if self.reg_tags[reg] != "":
            rs.qj = self.reg_tags[reg]
            rs.vj = 0
        else:
            rs.qj = ""
            rs.vj = self.reg_values[reg]

    def _read_operand_k(self, rs: ReservationStation, reg: int):
        """Liest Operand K aus dem Registerfile oder setzt Tag."""
        if self.reg_tags[reg] != "":
            rs.qk = self.reg_tags[reg]
            rs.vk = 0
        else:
            rs.qk = ""
            rs.vk = self.reg_values[reg]

    # ------------------------------------------------------------------
    # Ausgabebefehle
    # ------------------------------------------------------------------

    def _handle_command(self, cmd: str):
        """Verarbeitet einen Ausgabebefehl."""
        if cmd == "v":
            self.verbose = not self.verbose
            mode = "EIN" if self.verbose else "AUS"
            self._log(f"--- Verbose-Modus: {mode} ---")
        elif cmd == "s":
            self._print_state()
        elif cmd == "h":
            self._print_ipc()
        elif cmd == "i":
            self._print_stalls()

    def _print_state(self):
        """Gibt den aktuellen Zustand aller RS und Register aus."""
        self._log(f"\n=== Zustand nach Zyklus {self.cycle} ===")
        self._log("Reservierungsstationen:")
        self._log(f"  {'Name':6s} | {'Status':9s} | {'Op':5s} | "
                  f"{'Operand J':12s} | {'Operand K':12s} | Dest")
        self._log("  " + "-" * 70)
        for rs in self.all_stations:
            self._log(rs.status_str())

        self._log("\nRegisterfile:")
        parts = []
        for i in range(self.config.num_registers):
            tag = self.reg_tags[i]
            val = self.reg_values[i]
            if tag:
                parts.append(f"R{i}=[{tag}]")
            else:
                parts.append(f"R{i}={val}")
        self._log("  " + "  ".join(parts))

        self._log("")

    def _print_ipc(self):
        """Gibt IPC und Gesamtzyklen aus."""
        ipc = self.instructions_completed / self.cycle if self.cycle > 0 else 0
        self._log(f"\n=== Leistung (Zyklus {self.cycle}) ===")
        self._log(f"  Gesamtzyklen:            {self.cycle}")
        self._log(f"  Abgeschl. Instruktionen: {self.instructions_completed}")
        self._log(f"  IPC:                     {ipc:.4f}")
        self._log("")

    def _print_stalls(self):
        """Gibt Stall-Zyklen und aufgeloeste Abhaengigkeiten aus."""
        self._log(f"\n=== Abhaengigkeiten (Zyklus {self.cycle}) ===")
        self._log(f"  Stall-Zyklen (strukturell): {self.stall_cycles}")
        self._log(f"  Aufgeloeste RAW-Abhaengigkeiten: {self.raw_resolved}")
        self._log("")

    # ------------------------------------------------------------------
    # FU-Auslastung zaehlen
    # ------------------------------------------------------------------

    def _count_utilization(self):
        """Zaehlt die belegten RS pro Typ in diesem Zyklus.
        Zaehlt RS die in diesem Zyklus aktiv waren (executing oder gerade fertig)."""
        for rs in self.alu_stations:
            if rs.busy and (rs.executing or rs.ready_to_write):
                self.alu_busy_cycles += 1
        for rs in self.ls_stations:
            if rs.busy and (rs.executing or rs.ready_to_write):
                self.ls_busy_cycles += 1

    # ------------------------------------------------------------------
    # Haupt-Simulationsschleife
    # ------------------------------------------------------------------

    def run(self, trace_lines: List[str], silent: bool = False) -> Dict:
        """
        Fuehrt die Simulation fuer einen gegebenen Trace aus.
        
        Args:
            trace_lines: Liste der Zeilen der Trace-Datei
            silent: Wenn True, keine Ausgabe auf stdout
            
        Returns:
            Dictionary mit Statistiken
        """
        self._init_hardware()
        self._init_stats()
        self.verbose = False
        self.output_lines = []

        # Trace parsen
        trace = parse_trace(trace_lines)
        if not trace:
            return self._get_stats()

        num_instructions = sum(1 for item in trace if isinstance(item, Instruction))
        pointer = 0

        # Hauptschleife
        while True:
            # Kommandos verarbeiten (verbrauchen keinen Zyklus)
            while pointer < len(trace) and isinstance(trace[pointer], str):
                if not silent:
                    self._handle_command(trace[pointer])
                else:
                    if trace[pointer] == "v":
                        pass  # Verbose im Silent-Modus ignorieren
                pointer += 1

            # Abbruchbedingung: alle Instruktionen issued UND keine RS mehr belegt
            all_issued = (pointer >= len(trace))
            any_busy = any(rs.busy for rs in self.all_stations)

            if all_issued and not any_busy:
                break

            # Neuer Zyklus
            self.cycle += 1
            self._cdb_updated_rs.clear()  # Reset CDB-Tracking

            # Phase 1: Write Result (CDB)
            self._phase_write_result()

            # Phase 2: Execute
            self._phase_execute()

            # Phase 3: Issue
            if pointer < len(trace) and isinstance(trace[pointer], Instruction):
                if self._try_issue(trace[pointer]):
                    pointer += 1

            # Auslastung zaehlen
            self._count_utilization()

            # Sicherheits-Check gegen Endlosschleifen
            if self.cycle > num_instructions * 100 + 1000:
                if not silent:
                    self._log("FEHLER: Maximale Zyklenanzahl ueberschritten!")
                break

        # Finale Kommandos am Ende des Traces
        while pointer < len(trace) and isinstance(trace[pointer], str):
            if not silent:
                self._handle_command(trace[pointer])
            pointer += 1

        return self._get_stats()

    def _get_stats(self) -> Dict:
        """Gibt die gesammelten Statistiken als Dictionary zurueck."""
        total = self.cycle
        ipc = self.instructions_completed / total if total > 0 else 0
        alu_cap = self.config.alu_rs_count * total if total > 0 else 1
        ls_cap = self.config.ls_rs_count * total if total > 0 else 1
        
        return {
            "total_cycles": total,
            "instructions": self.instructions_completed,
            "ipc": round(ipc, 4),
            "stall_cycles": self.stall_cycles,
            "raw_resolved": self.raw_resolved,
            "alu_utilization_pct": round(self.alu_busy_cycles / alu_cap * 100, 2) if alu_cap > 0 else 0,
            "ls_utilization_pct": round(self.ls_busy_cycles / ls_cap * 100, 2) if ls_cap > 0 else 0,
            "instruction_log": self.instruction_log,
        }

    def print_final_stats(self):
        """Gibt die abschliessenden Statistiken aus."""
        stats = self._get_stats()
        self._log("\n" + "=" * 60)
        self._log("ENDERGEBNIS")
        self._log("=" * 60)
        self._log(f"  Gesamtzyklen:                    {stats['total_cycles']}")
        self._log(f"  Instruktionen:                   {stats['instructions']}")
        self._log(f"  IPC:                             {stats['ipc']:.4f}")
        self._log(f"  Stall-Zyklen (strukturell):      {stats['stall_cycles']}")
        self._log(f"  Aufgeloeste RAW-Abhaengigkeiten: {stats['raw_resolved']}")
        self._log(f"  ALU-Auslastung:                  {stats['alu_utilization_pct']:.1f}%")
        self._log(f"  Load/Store-Auslastung:           {stats['ls_utilization_pct']:.1f}%")
        self._log("=" * 60)

        # Instruktions-Timeline
        if self.instruction_log:
            self._log("\nInstruktions-Timeline:")
            self._log(f"  {'Nr':>3s} | {'Instruktion':30s} | {'RS':6s} | "
                      f"{'Issue':>5s} | {'Exec':>5s} | {'Write':>5s}")
            self._log("  " + "-" * 70)
            for entry in sorted(self.instruction_log, key=lambda e: e["index"]):
                self._log(f"  {entry['index']:3d} | {entry['instr']:30s} | "
                          f"{entry['rs_name']:6s} | {entry['issue_cycle']:5d} | "
                          f"{entry['exec_start']:5d} | {entry['write_cycle']:5d}")
        self._log("")


# ---------------------------------------------------------------------------
# In-Order-Referenzpipeline (ohne dynamisches Scheduling)
# ---------------------------------------------------------------------------

class InOrderPipeline:
    """
    Einfache In-Order-Pipeline ohne dynamisches Scheduling.
    Dient als Vergleich zum Tomasulo-Algorithmus.
    
    Modell:
    - Eine Instruktion nach der anderen (kein Pipelining der FUs)
    - Bei RAW-Abhaengigkeit: Warten bis Produzent fertig
    - Jede Instruktion: 1 (Issue) + Latenz (Execute) + 1 (Writeback)
    - Naechste Instruktion kann erst issuen wenn vorherige abgeschlossen
      ODER wenn keine Abhaengigkeit (einfaches Pipelining)
    """

    def __init__(self, config: Config = None):
        self.config = config or Config()

    def run(self, trace_lines: List[str]) -> Dict:
        trace = parse_trace(trace_lines)
        instructions = [item for item in trace if isinstance(item, Instruction)]

        if not instructions:
            return {"total_cycles": 0, "instructions": 0, "ipc": 0}

        # Fuer jede Instruktion: wann ist ihr Ergebnis verfuegbar?
        # write_cycle[reg] = Zyklus in dem Register reg beschrieben wird
        reg_available = [0] * self.config.num_registers
        cycle = 0
        raw_stalls = 0

        log = []

        for instr in instructions:
            # Fruehester Issue-Zyklus: ein Zyklus nach dem letzten Issue
            earliest_issue = cycle + 1

            # RAW-Check: muessen Quelloperanden verfuegbar sein
            if instr.op in ("ADD", "SUB", "MUL", "DIV"):
                needed = max(reg_available[instr.rs1], reg_available[instr.rs2])
            elif instr.op == "LOAD":
                needed = reg_available[instr.rs1]
            elif instr.op == "STORE":
                needed = max(reg_available[instr.rs1], reg_available[instr.rd])
            else:
                needed = 0

            # Issue fruhestens wenn Operanden bereit
            issue_cycle = max(earliest_issue, needed + 1)

            # Stalls durch Abhaengigkeiten
            if issue_cycle > earliest_issue:
                raw_stalls += (issue_cycle - earliest_issue)

            latency = self.config.get_latency(instr.op)
            exec_start = issue_cycle + 1
            exec_end = exec_start + latency - 1
            write_cycle = exec_end + 1

            # Ergebnis verfuegbar nach Writeback
            if instr.op != "STORE" and instr.rd >= 0:
                reg_available[instr.rd] = write_cycle

            log.append({
                "index": instr.index,
                "instr": str(instr),
                "issue": issue_cycle,
                "exec_start": exec_start,
                "write": write_cycle,
            })

            cycle = issue_cycle  # Naechstes Issue fruehestens danach

        # Gesamtzyklen = letzter Writeback-Zyklus
        total_cycles = max(entry["write"] for entry in log) if log else 0
        ipc = len(instructions) / total_cycles if total_cycles > 0 else 0

        return {
            "total_cycles": total_cycles,
            "instructions": len(instructions),
            "ipc": round(ipc, 4),
            "raw_stalls": raw_stalls,
            "instruction_log": log,
        }


# ---------------------------------------------------------------------------
# Kommandozeilen-Interface
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Tomasulo-Pipeline-Simulator")
    parser.add_argument("trace_file", help="Pfad zur Trace-Datei")
    parser.add_argument("--config", "-c", help="JSON-Konfigurationsdatei")
    parser.add_argument("--alu-rs", type=int, help="Anzahl ALU-RS")
    parser.add_argument("--ls-rs", type=int, help="Anzahl Load/Store-RS")
    parser.add_argument("--lat-add", type=int, help="Latenz ADD/SUB")
    parser.add_argument("--lat-mul", type=int, help="Latenz MUL")
    parser.add_argument("--lat-div", type=int, help="Latenz DIV")
    parser.add_argument("--lat-ls", type=int, help="Latenz LOAD/STORE")
    parser.add_argument("--compare", action="store_true",
                        help="Vergleich mit In-Order-Pipeline")
    parser.add_argument("--silent", action="store_true",
                        help="Nur Endergebnis ausgeben")

    args = parser.parse_args()

    # Konfiguration
    if args.config:
        config = Config.from_json(args.config)
    else:
        config = Config()

    # Kommandozeilen-Overrides
    if args.alu_rs: config.alu_rs_count = args.alu_rs
    if args.ls_rs: config.ls_rs_count = args.ls_rs
    if args.lat_add: config.latency_add = args.lat_add
    if args.lat_mul: config.latency_mul = args.lat_mul
    if args.lat_div: config.latency_div = args.lat_div
    if args.lat_ls: config.latency_ls = args.lat_ls

    # Trace einlesen
    with open(args.trace_file) as f:
        trace_lines = f.readlines()

    # Tomasulo-Simulation
    print("=" * 60)
    print("TOMASULO-PIPELINE-SIMULATOR")
    print(f"Konfiguration: ALU-RS={config.alu_rs_count}, "
          f"LS-RS={config.ls_rs_count}")
    print(f"Latenzen: ADD/SUB={config.latency_add}, MUL={config.latency_mul}, "
          f"DIV={config.latency_div}, LOAD/STORE={config.latency_ls}")
    print("=" * 60)

    sim = TomasuloSimulator(config)
    sim.run(trace_lines, silent=args.silent)
    sim.print_final_stats()

    # Vergleich mit In-Order
    if args.compare:
        print("\n" + "=" * 60)
        print("VERGLEICH: IN-ORDER-PIPELINE (ohne dynamisches Scheduling)")
        print("=" * 60)
        
        io_pipe = InOrderPipeline(config)
        io_stats = io_pipe.run(trace_lines)

        print(f"  Gesamtzyklen:    {io_stats['total_cycles']}")
        print(f"  Instruktionen:   {io_stats['instructions']}")
        print(f"  IPC:             {io_stats['ipc']:.4f}")
        print(f"  RAW-Stalls:      {io_stats.get('raw_stalls', 0)}")

        tom_stats = sim._get_stats()
        if io_stats['total_cycles'] > 0:
            speedup = io_stats['total_cycles'] / tom_stats['total_cycles']
            print(f"\n  Speedup (Tomasulo vs. In-Order): {speedup:.2f}x")
        print("=" * 60)


if __name__ == "__main__":
    main()
