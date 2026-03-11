
# -*- coding: utf-8 -*-
import subprocess
import random
import re

# --- Konfiguration ---
FASTCHESS_CMD = "./fastchess"   # Pfad zur fastchess-Ausführungsdatei
ENGINE_CMD = "./myengine"       # Pfad zu deiner C++ Engine
ROUNDS = 50                     # 50 Runden mit -repeat = 100 Spiele pro Iteration
CONCURRENCY = 5                 # Anzahl der CPU-Kerne für die Matches

# --- SPSA Hyperparameter ---
# Diese Werte bestimmen, wie aggressiv SPSA lernt.
A = 2.0  # Lernrate (Wie stark werden Parameter nach einem Sieg angepasst?)
C = 5.0  # Störung (Wie weit liegen Engine Plus und Minus beim Testen auseinander?)

# Deine zu optimierenden Parameter mit Startwerten
params = {
    "RevFut": 125.0,
}

def play_match(params_plus, params_minus):
    """Startet fastchess, lässt die Varianten spielen und gibt die Win-Rate zurück."""
    
    # 1. Befehlsliste für den fastchess-Aufruf zusammenbauen
    cmd = [FASTCHESS_CMD]
    
    # Engine Plus konfigurieren
    cmd.extend(["-engine", "name=Plus", f"cmd={ENGINE_CMD}"])
    for key, value in params_plus.items():
        cmd.append(f"option.{key}={int(value)}") # Parameter als UCI-Optionen
        
    # Engine Minus konfigurieren
    cmd.extend(["-engine", "name=Minus", f"cmd={ENGINE_CMD}"])
    for key, value in params_minus.items():
        cmd.append(f"option.{key}={int(value)}")
        
    # Allgemeine Match-Einstellungen
    cmd.extend([
        "-each", "proto=uci", "tc=8+0.1", # Time Control: 8s + 0.1s Inkrement
        "-rounds", str(ROUNDS),
        "-repeat",                         # Beide Engines spielen jede Eröffnung mit Weiß und Schwarz
        "-concurrency", str(CONCURRENCY),
        "-recover"                         # Verhindert Abstürze bei Engine-Fehlern
    ])
    
    # 2. fastchess ausführen
    print(f"Starte Match mit {ROUNDS * 2} Spielen...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 3. Output parsen
    # Wir suchen im Text nach der Zeile: "Score of Plus vs Minus: 55 - 40 - 5"
    match = re.search(r"Score of Plus vs Minus: (\d+) - (\d+) - (\d+)", result.stdout)
    
    if not match:
        print("Fehler: Konnte fastchess-Output nicht lesen!")
        print(result.stdout[-500:]) # Letzte Zeichen zur Fehlersuche ausgeben
        return 0.5 # Bei Fehler nehmen wir ein 50/50 Remis an
        
    wins = int(match.group(1))
    losses = int(match.group(2))
    draws = int(match.group(3))
    
    total_games = wins + losses + draws
    win_rate = (wins + (draws / 2.0)) / total_games
    
    return win_rate

# --- Der eigentliche SPSA-Loop ---
print("Starte SPSA Tuning...")

for iteration in range(1, 101): # Wir machen als Beispiel 100 Iterationen
    print(f"\n--- Iteration {iteration} ---")
    
    # 1. Zufälliges Delta erzeugen (Entweder +1 oder -1 für jeden Parameter)
    deltas = {k: random.choice([-1, 1]) for k in params.keys()}
    
    # 2. Plus- und Minus-Varianten berechnen
    params_plus = {k: v + C * deltas[k] for k, v in params.items()}
    params_minus = {k: v - C * deltas[k] for k, v in params.items()}
    
    # 3. Match spielen lassen
    score = play_match(params_plus, params_minus)
    print(f"Score für Plus: {score:.3f}")
    
    # 4. Gradient schätzen und Parameter updaten
    # Wenn Score > 0.5 (Plus hat gewonnen), ist der Gradient positiv.
    gradient_step = (score - 0.5) * 2 
    
    for key in params.keys():
        # Parameter in die Richtung anpassen, die erfolgreicher war
        params[key] += A * gradient_step * deltas[key]
        
    # Aktuellen Stand formatiert ausgeben
    print("Neue Parameter:", {k: round(v, 2) for k, v in params.items()})