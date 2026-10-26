"""Copia le Skill del progetto da `skills/` (fonte canonica) nelle cartelle lette dagli agenti.

Claude Code legge `.claude/skills`, Codex legge `.agents/skills`. Le copie sono generate e ignorate da Git.
Uso: python -I scripts/sincronizza_skill.py
"""
import shutil
from pathlib import Path

radice = Path(__file__).resolve().parents[1]
sorgente = radice / "skills"
for destinazione in (radice / ".claude" / "skills", radice / ".agents" / "skills"):
    if destinazione.exists():
        shutil.rmtree(destinazione)
    shutil.copytree(sorgente, destinazione)
    print(f"Skill copiate in {destinazione.relative_to(radice)}")
