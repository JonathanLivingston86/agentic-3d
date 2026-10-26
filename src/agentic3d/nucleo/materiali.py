"""Tavolozza dei materiali del progetto: stessi nomi e valori usati da Blender e dal GLB.

nome: (rosso, verde, blu, ruvidezza, metallo, trasparenza), con trasparenza 1 = opaco.
I nomi sono quelli che l'utente vede in SketchUp: leggibili e unici.
"""

MATERIALI = {
    "Intonaco pareti": (0.93, 0.91, 0.86, 0.9, 0.0, 1.0),
    "Fascia pareti verde salvia": (0.62, 0.74, 0.66, 0.85, 0.0, 1.0),
    "Soffitto bianco": (0.96, 0.96, 0.95, 0.9, 0.0, 1.0),
    "Pavimento rovere": (0.66, 0.47, 0.29, 0.55, 0.0, 1.0),
    "Telaio bianco": (0.95, 0.95, 0.94, 0.4, 0.0, 1.0),
    "Vetro": (0.75, 0.88, 0.95, 0.05, 0.0, 0.18),
    "Legno chiaro": (0.80, 0.64, 0.44, 0.55, 0.0, 1.0),
    "Laccato bianco": (0.95, 0.95, 0.93, 0.35, 0.0, 1.0),
    "Cestone verde acqua": (0.30, 0.62, 0.64, 0.7, 0.0, 1.0),
    "Cestone corallo": (0.88, 0.47, 0.40, 0.7, 0.0, 1.0),
    "Cestone senape": (0.90, 0.70, 0.25, 0.7, 0.0, 1.0),
    "Tessuto azzurro": (0.38, 0.58, 0.82, 0.95, 0.0, 1.0),
    "Tessuto giallo": (0.95, 0.77, 0.28, 0.95, 0.0, 1.0),
    "Cuscino bianco": (0.96, 0.95, 0.92, 0.95, 0.0, 1.0),
    "Tenda crema": (0.94, 0.90, 0.80, 0.95, 0.0, 1.0),
    "Metallo bastone": (0.55, 0.50, 0.42, 0.35, 0.9, 1.0),
    "Cornice nera": (0.07, 0.07, 0.08, 0.5, 0.0, 1.0),
    "Tela rosa": (0.93, 0.74, 0.72, 0.9, 0.0, 1.0),
    "Tela celeste": (0.70, 0.84, 0.90, 0.9, 0.0, 1.0),
    "Tela senape": (0.92, 0.80, 0.50, 0.9, 0.0, 1.0),
    "Tela verde": (0.66, 0.80, 0.64, 0.9, 0.0, 1.0),
    "Televisore nero": (0.03, 0.03, 0.035, 0.3, 0.0, 1.0),
    "Schermo spento": (0.02, 0.025, 0.03, 0.1, 0.0, 1.0),
    "Termosifone bianco": (0.96, 0.96, 0.95, 0.4, 0.0, 1.0),
    "Arco terracotta": (0.82, 0.48, 0.38, 0.8, 0.0, 1.0),
    "Anta armadio": (0.93, 0.92, 0.89, 0.5, 0.0, 1.0),
    "Maniglia": (0.60, 0.58, 0.55, 0.3, 0.9, 1.0),
    "Sgabello senape": (0.90, 0.68, 0.22, 0.6, 0.0, 1.0),
    "Libro 1": (0.80, 0.30, 0.28, 0.8, 0.0, 1.0),
    "Libro 2": (0.25, 0.45, 0.70, 0.8, 0.0, 1.0),
    "Libro 3": (0.90, 0.75, 0.25, 0.8, 0.0, 1.0),
    "Libro 4": (0.35, 0.62, 0.45, 0.8, 0.0, 1.0),
    "Libro 5": (0.92, 0.88, 0.80, 0.8, 0.0, 1.0),
    "Porta laccata": (0.94, 0.94, 0.92, 0.45, 0.0, 1.0),
    # soggiorno di prova: velluti caldi, noce, metallo nero, ottone (anni Settanta, in assonanza con la
    # poltrona Nolvik senape)
    "Velluto senape": (0.74, 0.50, 0.11, 0.85, 0.0, 1.0),
    "Velluto ruggine": (0.50, 0.21, 0.12, 0.85, 0.0, 1.0),
    "Velluto crema": (0.86, 0.80, 0.68, 0.85, 0.0, 1.0),
    "Metallo nero": (0.035, 0.035, 0.04, 0.45, 0.8, 1.0),
    "Legno noce": (0.33, 0.20, 0.12, 0.5, 0.0, 1.0),
    "Ottone": (0.78, 0.62, 0.32, 0.3, 1.0, 1.0),
    "Vetro opale": (0.96, 0.95, 0.91, 0.35, 0.0, 1.0),
    "Lana crema": (0.88, 0.83, 0.72, 0.95, 0.0, 1.0),
    "Terracotta": (0.70, 0.38, 0.25, 0.85, 0.0, 1.0),
    "Foglie": (0.18, 0.36, 0.17, 0.7, 0.0, 1.0),
    "Tela ocra": (0.80, 0.56, 0.24, 0.9, 0.0, 1.0),
    "Pietra grigia": (0.60, 0.59, 0.56, 0.4, 0.0, 1.0),
    "Acciaio": (0.75, 0.75, 0.74, 0.45, 1.0, 1.0),   # satinato: la vasca si legge in profondità
    "Vetro nero": (0.02, 0.02, 0.025, 0.05, 0.0, 1.0),
    "Ceramica bianca": (0.95, 0.95, 0.94, 0.12, 0.0, 1.0),     # sanitari
    "Cromo": (0.90, 0.90, 0.90, 0.08, 1.0, 1.0),               # rubinetti
}
LIBRI = ["Libro 1", "Libro 2", "Libro 3", "Libro 4", "Libro 5"]
CESTONI = ["Cestone verde acqua", "Cestone corallo", "Cestone senape"]
TESSUTI = {"azzurro": "Tessuto azzurro", "giallo": "Tessuto giallo"}
TELE = ["Tela rosa", "Tela celeste", "Tela senape", "Tela verde"]


def preambolo_blender() -> str:
    """Codice da incollare in testa agli script per Blender: la stessa tavolozza usata dal GLB e da SketchUp."""
    return (f"MATERIALI = {MATERIALI!r}\nLIBRI = {LIBRI!r}\nCESTONI = {CESTONI!r}\n"
            f"TESSUTI = {TESSUTI!r}\nTELE = {TELE!r}\n")
