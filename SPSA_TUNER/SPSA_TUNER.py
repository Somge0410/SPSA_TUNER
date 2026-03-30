# -*- coding: utf-8 -*-
from bdb import effective
from configparser import MAX_INTERPOLATION_DEPTH
from math import floor
import subprocess
import random
import re

# --- Konfiguration ---
FASTCHESS_CMD = "./fastchess"   # Pfad zur fastchess-Ausführungsdatei
ENGINE_CMD = "./myengine"       # Pfad zu deiner C++ Engine
ROUNDS = 500                     # 100 Runden mit -repeat = 100 Spiele pro Iteration
CONCURRENCY = 6                 # Anzahl der CPU-Kerne für die Matches
MAX_ITERATION=100              # Anzahl der SPSA-Iterationen

# Die zu optimierenden Parameter mit Startwerten
params = {
    "RevFut": {"value":165.0, "rate":60000, "change":50.0, "min": 0, "max": 500},
    "RevFutDepth": {"value":2.0, "rate":2.0, "change":1.0, "min": 1, "max": 20},
    "FutilityMarginD1": {"value":678.0, "rate":1900000, "change":150.0, "min": 0, "max": 1000},
    "FutilityMarginD2": {"value":190.0, "rate":250000, "change":50.0, "min": 0, "max": 1000},
    "DeltaMargin": {"value":400.0, "rate":75000, "change":150.0, "min": 0, "max": 1000},
    "MaxQuietPly": {"value":9.0, "rate":50.0, "change":1.0, "min": 1, "max": 20},
    "LmrMinDepth": {"value":5.0, "rate":50.0, "change":1.0, "min": 1, "max": 10},
    "LmrMinMoves": {"value":2.0, "rate":50.0, "change":1.0, "min": 1, "max": 10},
    "LmrRedAm": {"value":1.0, "rate":50.0, "change":1.0, "min": 1, "max": 10}, # Prevents the 0 crash!
    #"NmpReduction": {"value":3.0, "rate":2.0, "change":1.0, "min": 1, "max": 10},
    "AspirationWindowInitial": {"value":62.0, "rate":6000, "change":20.0, "min": 1, "max": 500},
    "AspirationWindowMultiplier": {"value":1.75, "rate":15, "change":0.25, "min": 1, "max": 10.0},
    "TimeAllocationDivisor": {"value":37.0, "rate":3000, "change":10.0, "min": 1, "max": 100},
    "MaxTimeFraction": {"value":1.5, "rate":10.0, "change":0.5, "min": 1.0, "max": 10.0},
}

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

for iteration in range(1, MAX_ITERATION): # Wir machen als Beispiel 100 Iterationen
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