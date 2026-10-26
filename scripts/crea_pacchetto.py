"""Costruisce il pacchetto da distribuire e la copia pulita per il repository pubblico.

    python -I scripts/crea_pacchetto.py

In `dist/`:
- `Agentic 3D <versione>/` e lo ZIP omonimo: `Windows/` e `Mac/` con installatore e disinstallatore, `Guida.html`,
  `Licenza.md` e `componenti/` (motore .whl, script di Windows, istruzioni per l'agente);
- `Agentic 3D per SketchUp.rbz`: l'estensione da inviare al portale di firma di SketchUp;
- `repository pubblico/`: solo ciò che si pubblica (niente lavori, test, stato o percorsi di questo computer).

Prima di finire cerca nei file prodotti nomi e percorsi personali: se ne trova, si ferma con un errore.

Versioni: un numero già distribuito non si riusa mai (pacchetti diversi con lo stesso nome creano conflitti). Ogni
pacchetto costruito riceve l'etichetta Git `v<versione>`; se l'etichetta esiste già lo script si ferma e chiede di
aumentare `version` in `pyproject.toml` (1.1.0 -> 1.1.1 per correzioni, 1.2.0 per funzioni nuove). `--prova` costruisce
in `dist/prova/` senza etichetta e con "prova" nel nome, per i collaudi su questo computer.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
DIST = RADICE / "dist"
DISTRIBUZIONE = RADICE / "distribuzione"
# parole che non devono mai uscire dal computer di sviluppo: elenco in un file che non si pubblica
FILE_VIETATE = RADICE / "scripts" / "parole vietate.txt"
PUBBLICO = ["src", "skills", "distribuzione", "scripts/crea_pacchetto.py", "scripts/sincronizza_skill.py",
            "pyproject.toml", "uv.lock", "LICENZA.md", "INSTALLA.md", ".gitattributes"]
IGNORA = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def versione() -> str:
    return tomllib.loads((RADICE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def scrivi_testo(origine: Path, destinazione: Path, a_capo: str, bom: bool = False) -> None:
    """Copia un testo con gli a capo del sistema di destinazione (CRLF per .cmd e .ps1, LF per .command)."""
    testo = origine.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", a_capo)
    destinazione.write_bytes(("﻿" if bom else "").encode("utf-8") + testo.encode("utf-8"))


def costruisci_wheel() -> Path:
    for vecchio in DIST.glob("agentic3d-*.whl"):
        vecchio.unlink()
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(DIST)], cwd=RADICE, check=True)
    return next(DIST.glob(f"agentic3d-{versione()}-*.whl"))


def assembla_pacchetto(wheel: Path) -> Path:
    cartella = DIST / (f"Agentic 3D {versione()}" + (" prova" if DIST.name == "prova" else ""))
    if cartella.exists():
        shutil.rmtree(cartella)
    for sotto in ("Windows", "Mac", "componenti"):
        (cartella / sotto).mkdir(parents=True)
    for f in (DISTRIBUZIONE / "Windows").glob("*.cmd"):
        scrivi_testo(f, cartella / "Windows" / f.name, "\r\n")
    for f in (DISTRIBUZIONE / "Mac").glob("*.command"):
        scrivi_testo(f, cartella / "Mac" / f.name, "\n")
    for f in (DISTRIBUZIONE / "componenti").glob("*.ps1"):
        scrivi_testo(f, cartella / "componenti" / f.name, "\r\n", bom=True)   # PowerShell 5 vuole il BOM per gli accenti
    shutil.copy2(DISTRIBUZIONE / "Guida.html", cartella)
    shutil.copy2(RADICE / "LICENZA.md", cartella / "Licenza.md")
    shutil.copy2(RADICE / "INSTALLA.md", cartella / "componenti")
    shutil.copy2(wheel, cartella / "componenti")
    return cartella


def comprimi(cartella: Path) -> Path:
    """ZIP con i permessi Unix: i .command restano eseguibili quando il Mac lo estrae."""
    zip_ = cartella.parent / f"{cartella.name}.zip"
    zip_.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(cartella.rglob("*")):
            if f.is_dir():
                continue
            info = zipfile.ZipInfo.from_file(f, f"{cartella.name}/{f.relative_to(cartella).as_posix()}")
            info.external_attr = ((0o755 if f.suffix == ".command" else 0o644) | 0o100000) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())
    return zip_


def repository_pubblico() -> Path:
    cartella = DIST / "repository pubblico"
    if cartella.exists():
        shutil.rmtree(cartella)
    cartella.mkdir(parents=True)
    for voce in PUBBLICO:
        p = RADICE / voce
        dest = cartella / voce
        dest.parent.mkdir(parents=True, exist_ok=True)
        if p.is_dir():
            shutil.copytree(p, dest, ignore=IGNORA)
        else:
            shutil.copy2(p, dest)
    shutil.move(str(cartella / "distribuzione" / "README.md"), cartella / "README.md")
    (cartella / "docs").mkdir()
    shutil.copy2(RADICE / "docs" / "presentazione" / "Flusso di Agentic 3D.png", cartella / "docs")
    (cartella / ".gitignore").write_text("__pycache__/\n*.pyc\n.venv/\ndist/\n.DS_Store\nThumbs.db\n", encoding="utf-8")
    return cartella


def controlla_dati_personali(*cartelle: Path) -> list[str]:
    if not FILE_VIETATE.is_file():
        return [f"manca {FILE_VIETATE.name}: controllo dei dati personali non eseguito"]
    vietate = [r.strip() for r in FILE_VIETATE.read_text(encoding="utf-8").splitlines() if r.strip() and not r.startswith("#")]
    trovati = []
    for cartella in cartelle:
        for f in cartella.rglob("*"):
            if not f.is_file() or f.suffix.lower() in (".png", ".zip"):
                continue
            if f.suffix == ".whl":
                with zipfile.ZipFile(f) as z:
                    testi = [(f"{f.name}:{n}", z.read(n).decode("utf-8", "replace")) for n in z.namelist()]
            else:
                testi = [(str(f.relative_to(DIST)), f.read_text(encoding="utf-8", errors="replace"))]
            for nome, testo in testi:
                trovati += [f"{nome}: {v}" for v in vietate if v in testo]
    return trovati


def etichetta_esiste(nome: str) -> bool:
    esito = subprocess.run(["git", "tag", "--list", nome], cwd=RADICE, capture_output=True, text=True, check=True)
    return bool(esito.stdout.strip())


def main() -> int:
    global DIST
    prova = "--prova" in sys.argv
    etichetta = f"v{versione()}"
    if prova:
        DIST = DIST / "prova"
    elif etichetta_esiste(etichetta):
        print(f"ERRORE: la versione {versione()} è già stata distribuita (etichetta {etichetta}). "
              "Aumenta `version` in pyproject.toml prima di costruire un pacchetto nuovo.")
        return 1
    DIST.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-I", str(RADICE / "scripts" / "sincronizza_skill.py")], check=True)
    wheel = costruisci_wheel()
    sys.path.insert(0, str(RADICE / "src"))
    from agentic3d.estensione import crea_rbz
    rbz = crea_rbz(DIST)
    cartella = assembla_pacchetto(wheel)
    zip_ = comprimi(cartella)
    pubblico = repository_pubblico()
    problemi = controlla_dati_personali(cartella, pubblico)
    if problemi:
        print("ERRORE: dati personali nei file da distribuire:\n  " + "\n  ".join(problemi))
        return 1
    print(f"pacchetto:   {zip_} ({zip_.stat().st_size / 1e6:.1f} MB)")
    print(f"estensione:  {rbz}")
    print(f"pubblico:    {pubblico}")
    print("controllo dei dati personali: nessuna occorrenza")
    if not prova:
        subprocess.run(["git", "tag", "-a", etichetta, "-m", f"Pacchetto {versione()}"], cwd=RADICE, check=True)
        print(f"etichetta:   {etichetta} (questa versione non si può più ricostruire con lo stesso numero)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
