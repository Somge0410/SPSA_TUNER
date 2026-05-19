# -*- coding: utf-8 -*-
from bdb import effective
from configparser import MAX_INTERPOLATION_DEPTH
from math import floor
import subprocess
import random
import re
import json
import signal
import sys
import os
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend

# --- Konfiguration ---
FASTCHESS_CMD = "./fastchess"   # Pfad zur fastchess-Ausführungsdatei
ENGINE_CMD = "./tryFutPrun"       # Pfad zu deiner C++ Engine
ROUNDS = 2                     # 100 Runden mit -repeat = 100 Spiele pro Iteration
CONCURRENCY = 5                 # Anzahl der CPU-Kerne für die Matches
MAX_ITERATION=10000              # Anzahl der SPSA-Iterationen

# Die zu optimierenden Parameter mit Startwerten
params = {
    #"RevFut": {"value":165.0, "rate":60000, "change":50.0, "min": 0, "max": 500},
    #"RevFutDepth": {"value":2.0, "rate":2.0, "change":1.0, "min": 1, "max": 20},
    "FutilityMarginD1": {"value":200, "rate":35000, "change":150.0, "min": 0, "max": 10000},
    "FutilityMarginD2": {"value":400.0, "rate":60000, "change":225.0, "min": 0, "max": 10000},
    "FutilityMarginD3": {"value":600.0, "rate":75000, "change":350.0, "min": 0, "max": 10000},
    #"DeltaMargin": {"value":400.0, "rate":75000, "change":150.0, "min": 0, "max": 1000},
    #"MaxQuietPly": {"value":9.0, "rate":50.0, "change":1.0, "min": 1, "max": 20},
    #"LmrMinDepth": {"value":5.0, "rate":50.0, "change":1.0, "min": 1, "max": 10},
    #"LmrMinMoves": {"value":2.0, "rate":50.0, "change":1.0, "min": 1, "max": 10},
    #"LmrRedAm": {"value":1.0, "rate":50.0, "change":1.0, "min": 1, "max": 10}, # Prevents the 0 crash!
    #"NmpReduction": {"value":3.0, "rate":2.0, "change":1.0, "min": 1, "max": 10},
    #"AspirationWindowInitial": {"value":62.0, "rate":6000, "change":20.0, "min": 1, "max": 500},
    #"AspirationWindowMultiplier": {"value":1.75, "rate":15, "change":0.25, "min": 1, "max": 10.0},
    #"TimeAllocationDivisor": {"value":37.0, "rate":3000, "change":10.0, "min": 1, "max": 100},
    #"MaxTimeFraction": {"value":1.5, "rate":10.0, "change":0.5, "min": 1.0, "max": 10.0},
}

# --- Checkpoint handling ---
CHECKPOINT_FILE = "spsa_checkpoint.json"
GRAPH_FILE = "parameter_progress.png"
HISTORY_FILE = "parameter_history.json"

# Store original parameter values for percentage calculation
original_params = {k: v["value"] for k, v in params.items()}

# Dictionary to track parameter history across iterations
param_history = {k: [] for k in params.keys()}
iterations_list = []  # Track iteration numbers

def save_checkpoint(iteration, params):
    """Save current tuning state to file for resuming later."""
    checkpoint = {
        "iteration": iteration,
        "params": {k: {"value": v["value"], "rate": v["rate"], "change": v["change"], "min": v["min"], "max": v["max"]} 
                   for k, v in params.items()}
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, indent=2)
    print(f"[Checkpoint] Saved state at iteration {iteration}")

def load_checkpoint():
    """Load previous tuning state if it exists."""
    if not os.path.exists(CHECKPOINT_FILE):
        return None, 1
    
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
        iteration = checkpoint["iteration"]
        loaded_params = checkpoint["params"]
        
        # Restore params from checkpoint
        for key in params.keys():
            if key in loaded_params:
                params[key]["value"] = loaded_params[key]["value"]
        
        print(f"[Checkpoint] Loaded previous state from iteration {iteration}")
        print(f"[Checkpoint] Resuming from iteration {iteration + 1}")
        return params, iteration + 1
    except Exception as e:
        print(f"[Checkpoint] Error loading checkpoint: {e}")
        return None, 1

def load_history():
    """Load parameter history if it exists."""
    global param_history, iterations_list, original_params
    
    if not os.path.exists(HISTORY_FILE):
        return
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
        param_history = data.get("history", {k: [] for k in params.keys()})
        iterations_list = data.get("iterations", [])
        original_params = data.get("original_params", original_params)
        print(f"[History] Loaded parameter history with {len(iterations_list)} iterations")
    except Exception as e:
        print(f"[History] Error loading history: {e}")

def save_history():
    """Save parameter history to file."""
    try:
        history_data = {
            "history": param_history,
            "iterations": iterations_list,
            "original_params": original_params
        }
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history_data, f, indent=2)
    except Exception as e:
        print(f"[History] Error saving history: {e}")

def update_graph():
    """Update and save the parameter progress graph."""
    if not iterations_list:
        return
    
    try:
        plt.close('all')
        fig, ax = plt.subplots(figsize=(14, 8))
        
        # Plot each parameter as percentage change from original
        for param_name in params.keys():
            if param_name in param_history and len(param_history[param_name]) > 0:
                percentages = [
                    ((value - original_params[param_name]) / original_params[param_name] * 100)
                    for value in param_history[param_name]
                ]
                ax.plot(iterations_list, percentages, marker='o', label=param_name, linewidth=2)
        
        ax.set_xlabel('Iteration', fontsize=12, fontweight='bold')
        ax.set_ylabel('% Change from Original Value', fontsize=12, fontweight='bold')
        ax.set_title('SPSA Parameter Optimization Progress', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)
        
        plt.tight_layout()
        plt.savefig(GRAPH_FILE, dpi=100, bbox_inches='tight')
        print(f"[Graph] Updated graph saved to {GRAPH_FILE}")
        
    except Exception as e:
        print(f"[Graph] Error updating graph: {e}")

def display_graph():
    """Display the saved parameter progress graph."""
    try:
        if os.path.exists(GRAPH_FILE):
            import platform
            if platform.system() == 'Windows':
                os.startfile(GRAPH_FILE)
            elif platform.system() == 'Darwin':  # macOS
                os.system(f'open {GRAPH_FILE}')
            else:  # Linux
                os.system(f'xdg-open {GRAPH_FILE}')
            print(f"[Graph] Opening {GRAPH_FILE}") 
        else:
            print(f"[Graph] Graph file not found: {GRAPH_FILE}")
    except Exception as e:
        print(f"[Graph] Error displaying graph: {e}")

def signal_handler(signum, frame):
    """Handle Ctrl+C to gracefully save and exit."""
    print("\n[SIGNAL] Received interrupt signal. Saving state and exiting...")
    global iteration
    if 'iteration' in globals():
        save_checkpoint(iteration, params)
        save_history()
    display_graph()
    sys.exit(0)

def play_match(params_plus, params_minus):
    """Startet fastchess, lässt die Varianten spielen und gibt die Win-Rate zurück."""
    
    print("Starte Match")
    print("Plus Parameters", {k: v for k,v in params_plus.items()})
    print("Minus Parameters", {k: v for k,v in params_minus.items()})
    # 1. Befehlsliste für den fastchess-Aufruf zusammenbauen
    cmd = [FASTCHESS_CMD]
    
    # Engine Base konfigurieren
    cmd.extend(["-engine", "name=Plus", f"cmd={ENGINE_CMD}",
        "option.Threads=1", "option.Hash=128"])
    for key, value in params_plus.items():
        cmd.append(f"option.{key}={int(value)}") # Parameter als UCI-Optionen
    # Engine Minus konfigurieren
    cmd.extend(["-engine", "name=Minus", f"cmd={ENGINE_CMD}",
        "option.Threads=1", "option.Hash=128"])
    for key, value in params_minus.items():
        cmd.append(f"option.{key}={int(value)}")
    # Allgemeine Match-Einstellungen
    cmd.extend([
        "-each", "proto=uci", "tc=8+0.08", # Time Control: 8s + 0.08s Inkrement
        "-rounds", str(ROUNDS),
        "-repeat",                         # Beide Engines spielen jede Eröffnung mit Weiß und Schwarz
        "-concurrency", str(CONCURRENCY),
        #"-recover",                         # Verhindert Abstürze bei Engine-Fehlern
        # --- Opening Book Settings ---
        "-openings", 
        "file=8moves_v3.pgn", 
        "format=pgn", 
        "order=random", 
        "plies=16",
        # --- Logging ---
        "-log", "file=debug.log", "level=trace", "engine=true",
    ])
    
    # 2. fastchess ausführen und Output live in die Konsole schreiben
    print(f"Starte Match mit {ROUNDS * 2} Spielen...")
    output_lines = []
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in process.stdout:
            print(line, end="")  # Live-Ausgabe in die Konsole
            output_lines.append(line)
        process.wait(timeout=3600)  # Maximal 1 Stunde warten
    except subprocess.TimeoutExpired:
        print("Timeout: fastchess wird beendet...")
        process.kill()
        process.wait()
        return (0.5, 0)
    finally:
        # Sicherstellen, dass der Prozess wirklich beendet ist
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    
    full_output = "".join(output_lines)
    
    # 3. Output parsen
    # Wir suchen im Text nach der Zeile: "Wins: X, Losses: Y, Draws: Z"
    # findall statt search, da fastchess alle 20 Spiele Zwischenergebnisse ausgibt
    matches = re.findall(r"Wins: (\d+), Losses: (\d+), Draws: (\d+)", full_output)
    hypothesis=re.findall(r"H1", full_output)
    H1H=1 if len(hypothesis)>0 else 0
    if not matches:
        print("Fehler: Konnte fastchess-Output nicht lesen!")
        print(full_output[-500:]) # Letzte Zeichen zur Fehlersuche ausgeben
        return (0.5, 0) # Bei Fehler nehmen wir ein 50/50 Remis an
        
    # Letztes Ergebnis nehmen – das ist das Endergebnis nach allen Runden
    wins = int(matches[-1][0])
    losses = int(matches[-1][1])
    draws = int(matches[-1][2])
    
    total_games = wins + losses + draws
    win_rate = (wins + (draws / 2.0)) / total_games
    
    return (win_rate, H1H)

# --- Main execution ---
if __name__ == "__main__":
    # Set up signal handler for graceful cancellation
    signal.signal(signal.SIGINT, signal_handler)
    
    # Load checkpoint if it exists
    loaded_params, start_iteration = load_checkpoint()
    
    # Load parameter history if it exists
    load_history()
    
    try:
        for iteration in range(start_iteration, MAX_ITERATION): # Wir machen als Beispiel 100 Iterationen
            print(f"\n--- Iteration {iteration} ---")
            
            # 1. Zufälliges Delta erzeugen (Entweder +1 oder -1 für jeden Parameter)
            deltas = {k: random.choice([-1, 1]) for k in params.keys()}
            params_plus = {}
            params_minus={}
            effective_change={}
            for key, v in params.items():
                c_current=v["change"]/(iteration**0.101)
                plus_float=v["value"]+(c_current*deltas[key])
                minus_float=v["value"]-(c_current*deltas[key])

                plus_int=round(plus_float)
                minus_int=round(minus_float)

                plus_int=max(v["min"], min(v["max"], plus_int))
                minus_int=max(v["min"], min(v["max"], minus_int))
                if(plus_int==minus_int):
                    if deltas[key]==1:
                        if plus_int<v["max"]:
                            plus_int+=1
                        if minus_int>v["min"]:
                            minus_int-=1
                    else:
                        if plus_int>v["min"]:
                            plus_int-=1
                        if minus_int<v["max"]:
                            minus_int+=1
                params_plus[key]=plus_int
                params_minus[key]=minus_int

                effective_change[key]=abs(plus_int-minus_int)/2.0
            
            # 3. Match spielen lassen
            score, hypothesis = play_match(params_plus, params_minus)
            print(f"Score für Plus: {score:.3f}")
            
            # 4. Gradient schätzen und Parameter updaten
            # Wenn Score > 0.5 (Plus hat gewonnen), ist der Gradient positiv.
            gradient_step = score-0.5
            current_learning_rate={key: params[key]["rate"]/((MAX_ITERATION/10+iteration)**0.602) for key in params.keys()}

            for key in params.keys():
                # Parameter in die Richtung anpassen, die erfolgreicher war
                params[key]["value"] += (current_learning_rate[key]* gradient_step* deltas[key])/(effective_change[key])
            
            # Aktuellen Stand formatiert ausgeben
            print("Neue Parameter:", {k: round(v["value"], 2) for k, v in params.items()})
            
            # Track parameter history
            iterations_list.append(iteration)
            for param_name in params.keys():
                param_history[param_name].append(params[param_name]["value"])
            
            # Update graph after each iteration
            update_graph()
            
            # Save checkpoint and history after each iteration
            save_checkpoint(iteration, params)
            save_history()
    
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Saving checkpoint and history before exit...")
        save_checkpoint(iteration, params)
        save_history()
        update_graph()
        print("[INTERRUPTED] State saved. You can resume by running the script again.")
        display_graph()
        sys.exit(0)
    
    finally:
        print("\n[COMPLETED] Tuning finished!")
        print("Final Parameters:", {k: round(v["value"], 2) for k, v in params.items()})
        display_graph()