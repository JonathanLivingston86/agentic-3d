"""Collegamento di Agentic 3D agli agenti installati: Skill nelle loro cartelle e server MCP nelle loro configurazioni.

    agentic3d collega [--prova]     trova gli agenti e li collega (`--prova`: mostra cosa cambierebbe, senza scrivere)
    agentic3d scollega              toglie Skill e server di Agentic 3D, lasciando tutto il resto com'era

Regole: si tocca solo ciò che è di Agentic 3D (la voce `agentic3d` del server, le cartelle delle Skill con il file
`.agentic3d`); prima di cambiare un file di configurazione se ne fa una copia in
`<cartella di configurazione>/Copie di sicurezza/<data>`; un file che non si riesce a leggere non si tocca; rilanciare
il collegamento aggiorna senza duplicare.

Dove (documentazione ufficiale, verifica del 23 ottobre 2026, `docs/ricerca/2026-10-23-distribuzione-e-harness.md`):

| Agente          | Server MCP                                                  | Skill                    |
|-----------------|-------------------------------------------------------------|--------------------------|
| Claude Code     | `claude mcp add --scope user` (o `~/.claude.json`)          | `~/.claude/skills`       |
| Claude desktop  | `claude_desktop_config.json`, chiave `mcpServers`           | ZIP da caricare a mano   |
| Codex           | `~/.codex/config.toml`, tabella `[mcp_servers.agentic3d]`   | `~/.agents/skills`       |
| Gemini CLI      | `~/.gemini/settings.json`, chiave `mcpServers`              | `~/.gemini/skills`       |
| Cursor          | `~/.cursor/mcp.json`, chiave `mcpServers`                   | `~/.claude/skills`       |
| Copilot         | `~/.copilot/mcp-config.json`, chiave `mcpServers` (VS Code e CLI) | `~/.copilot/skills` |
| OpenCode        | `~/.config/opencode/opencode.json`, chiave `mcp`            | `~/.agents/skills`       |
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import configurazione as conf

NOME_SERVER = "agentic3d"
SEGNO = ".agentic3d"                      # file che marca le cartelle delle Skill installate da Agentic 3D
INIZIO_TOML = "# >>> Agentic 3D (gestito da `agentic3d collega`)"
FINE_TOML = "# <<< Agentic 3D"


def cartella_skill_pacchetto() -> Path:
    """Le Skill: dentro il pacchetto installato, oppure `skills/` del repository di sviluppo."""
    interna = Path(__file__).resolve().parent / "skill"
    if interna.is_dir():
        return interna
    sviluppo = conf.radice_sviluppo()
    if sviluppo and (sviluppo / "skills").is_dir():
        return sviluppo / "skills"
    raise FileNotFoundError("Skill di Agentic 3D non trovate nel pacchetto")


def comando_server() -> list[str]:
    """Comando assoluto che avvia il server MCP: le app con finestra (Claude desktop su macOS) non vedono il PATH."""
    cartella = Path(sys.executable).parent
    for nome in ("agentic3d.exe", "agentic3d"):
        if (cartella / nome).is_file():
            return [str(cartella / nome), "mcp"]
    trovato = shutil.which("agentic3d")
    return [trovato, "mcp"] if trovato else [sys.executable, "-m", "agentic3d", "mcp"]


@dataclass
class Contesto:
    casa: Path = field(default_factory=Path.home)
    prova: bool = False
    esegui: Callable = subprocess.run
    trova: Callable = shutil.which
    piattaforma: str = sys.platform
    copie: Path | None = None
    righe: list[str] = field(default_factory=list)

    def copia_di_sicurezza(self, f: Path) -> None:
        if self.prova or not f.is_file():
            return
        if self.copie is None:
            self.copie = conf.cartella_configurazione() / "Copie di sicurezza" / f"{datetime.now():%Y-%m-%d %H%M%S}"
        self.copie.mkdir(parents=True, exist_ok=True)
        nome = "-".join(f.relative_to(self.casa).parts) if f.is_relative_to(self.casa) else f.name
        shutil.copy2(f, self.copie / nome)


# ------------------------------------------------------------------ file JSON e TOML
def senza_commenti(testo: str) -> str:
    """JSON con commenti (JSONC, usato da OpenCode e VS Code): toglie // e /* */ fuori dalle stringhe e le virgole
    prima di } o ]."""
    out, i, n, in_stringa = [], 0, len(testo), False
    while i < n:
        c = testo[i]
        if in_stringa:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(testo[i + 1])
                i += 1
            elif c == '"':
                in_stringa = False
        elif c == '"':
            in_stringa = True
            out.append(c)
        elif testo.startswith("//", i):
            while i < n and testo[i] != "\n":
                i += 1
            continue
        elif testo.startswith("/*", i):
            fine = testo.find("*/", i + 2)
            i = n if fine < 0 else fine + 2
            continue
        else:
            out.append(c)
        i += 1
    pulito = "".join(out)
    import re
    return re.sub(r",(\s*[}\]])", r"\1", pulito)


def _leggi_json(f: Path) -> tuple[dict | None, bool]:
    """(dati, aveva commenti). Dati None se il file è rovinato: allora non si tocca."""
    if not f.is_file() or not f.read_text(encoding="utf-8").strip():
        return {}, False
    testo = f.read_text(encoding="utf-8-sig")
    try:
        dati, commenti = json.loads(testo), False
    except ValueError:
        try:
            dati, commenti = json.loads(senza_commenti(testo)), True
        except ValueError:
            return None, False
    return (dati, commenti) if isinstance(dati, dict) else (None, False)


def _scrivi_json(ctx: Contesto, f: Path, dati: dict) -> None:
    ctx.copia_di_sicurezza(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    provvisorio = f.with_name(f.name + ".agentic3d.tmp")
    provvisorio.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    provvisorio.replace(f)


def _json_server(ctx: Contesto, etichetta: str, f: Path, chiave: str, voce: dict | None) -> None:
    """Mette (o toglie, con `voce` None) il server nella chiave `chiave` di un file JSON."""
    dati, commenti = _leggi_json(f)
    if dati is None:
        ctx.righe.append(f"ATTENZIONE  {etichetta}: {f} non è un JSON leggibile: non toccato. "
                         f"Aggiungi a mano in `{chiave}` la voce `{NOME_SERVER}`: {json.dumps(voce)}")
        return
    sezione = dati.get(chiave) if isinstance(dati.get(chiave), dict) else {}
    if voce is None:
        if NOME_SERVER not in sezione:
            return
        del sezione[NOME_SERVER]
        azione = "server tolto"
    else:
        if sezione.get(NOME_SERVER) == voce:
            ctx.righe.append(f"OK  {etichetta}: server già collegato ({f})")
            return
        azione = "server aggiornato" if NOME_SERVER in sezione else "server aggiunto"
        sezione[NOME_SERVER] = voce
    dati[chiave] = sezione
    if not ctx.prova:
        _scrivi_json(ctx, f, dati)
    nota = " (il file aveva commenti: riscritto senza; l'originale è tra le copie di sicurezza)" if commenti else ""
    ctx.righe.append(f"{'PROVA' if ctx.prova else 'OK'}  {etichetta}: {azione} in {f}{nota}")


def _toml_codex(ctx: Contesto, f: Path, comando: list[str] | None) -> None:
    testo = f.read_text(encoding="utf-8") if f.is_file() else ""
    if INIZIO_TOML in testo and FINE_TOML in testo:
        a, b = testo.index(INIZIO_TOML), testo.index(FINE_TOML) + len(FINE_TOML)
        testo_senza = (testo[:a].rstrip("\n") + "\n" + testo[b:].lstrip("\n")).strip("\n")
        testo_senza = testo_senza + "\n" if testo_senza else ""
    else:
        testo_senza = testo
        if f"[mcp_servers.{NOME_SERVER}]" in testo:
            ctx.righe.append(f"ATTENZIONE  Codex: in {f} c'è già una tabella [mcp_servers.{NOME_SERVER}] scritta a mano: "
                             "non toccata")
            return
    if comando is None:
        nuovo, azione = testo_senza, "server tolto"
        if nuovo == testo:
            return
    else:
        # Codex chiede conferma per ogni strumento e lo ferma dopo 60 s: gli strumenti di Agentic 3D lavorano solo
        # nella cartella dei lavori (approvati), una costruzione con i render dura minuti, il primo avvio su macOS
        # (controlli di sicurezza) supera i 10 s
        blocco = "\n".join([INIZIO_TOML, f"[mcp_servers.{NOME_SERVER}]", f"command = {json.dumps(comando[0])}",
                            f"args = {json.dumps(comando[1:])}", "startup_timeout_sec = 60", "tool_timeout_sec = 1800",
                            'default_tools_approval_mode = "approve"', FINE_TOML])
        nuovo = (testo_senza.rstrip("\n") + "\n\n" if testo_senza.strip() else "") + blocco + "\n"
        if nuovo == testo:
            ctx.righe.append(f"OK  Codex: server già collegato ({f})")
            return
        azione = "server aggiornato" if INIZIO_TOML in testo else "server aggiunto"
    if not ctx.prova:
        ctx.copia_di_sicurezza(f)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(nuovo, encoding="utf-8")
    ctx.righe.append(f"{'PROVA' if ctx.prova else 'OK'}  Codex: {azione} in {f}")


# ------------------------------------------------------------------ agenti
def _claude_code(ctx: Contesto, comando: list[str] | None) -> None:
    cli = ctx.trova("claude")
    if cli:
        if ctx.prova:
            ctx.righe.append(f"PROVA  Claude Code: `claude mcp add --scope user {NOME_SERVER}`" if comando else
                             f"PROVA  Claude Code: `claude mcp remove {NOME_SERVER} --scope user`")
            return
        ctx.esegui([cli, "mcp", "remove", NOME_SERVER, "--scope", "user"], capture_output=True, text=True)
        if comando is None:
            ctx.righe.append("OK  Claude Code: server tolto")
            return
        esito = ctx.esegui([cli, "mcp", "add", "--scope", "user", NOME_SERVER, "--", *comando],
                           capture_output=True, text=True)
        ctx.righe.append("OK  Claude Code: server collegato (ambito utente)" if esito.returncode == 0 else
                         f"ERRORE  Claude Code: {(esito.stderr or esito.stdout or '').strip()[:300]}")
        return
    voce = None if comando is None else {"type": "stdio", "command": comando[0], "args": comando[1:]}
    _json_server(ctx, "Claude Code", ctx.casa / ".claude.json", "mcpServers", voce)


def _config_claude_desktop(ctx: Contesto) -> list[Path]:
    if ctx.piattaforma == "darwin":
        return [ctx.casa / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
    if ctx.piattaforma == "win32":
        roaming = Path(os.environ.get("APPDATA", ctx.casa / "AppData" / "Roaming"))
        locale = Path(os.environ.get("LOCALAPPDATA", ctx.casa / "AppData" / "Local"))
        file = [roaming / "Claude" / "claude_desktop_config.json"]
        # versione dal Microsoft Store: la cartella è virtualizzata dentro il pacchetto
        file += [p / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
                 for p in locale.glob("Packages/Claude_*") if (p / "LocalCache" / "Roaming" / "Claude").is_dir()]
        return file
    return [ctx.casa / ".config" / "Claude" / "claude_desktop_config.json"]


def _opencode_desktop(ctx: Contesto) -> list[Path]:
    """Dove si installa l'app desktop di OpenCode (usa la stessa configurazione di ~/.config/opencode)."""
    if ctx.piattaforma == "win32":
        locale = Path(os.environ.get("LOCALAPPDATA", ctx.casa / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", ctx.casa / "AppData" / "Roaming"))
        return [locale / "Programs" / "@opencodedesktop", roaming / "ai.opencode.desktop"]
    if ctx.piattaforma == "darwin":
        return [Path("/Applications/OpenCode.app"), ctx.casa / "Applications" / "OpenCode.app",
                ctx.casa / "Library" / "Application Support" / "ai.opencode.desktop"]
    return [ctx.casa / ".local" / "share" / "ai.opencode.desktop"]


@dataclass
class Agente:
    nome: str
    presente: Callable[[Contesto], bool]
    server: Callable[[Contesto, list[str] | None], None]
    skill: Callable[[Contesto], Path | None]


def _voce_mcp(comando):
    return None if comando is None else {"command": comando[0], "args": comando[1:]}


AGENTI = [
    Agente("Claude Code", lambda c: bool(c.trova("claude")) or (c.casa / ".claude").is_dir(), _claude_code,
           lambda c: c.casa / ".claude" / "skills"),
    Agente("Claude desktop", lambda c: any(f.parent.is_dir() for f in _config_claude_desktop(c)),
           lambda c, cmd: [_json_server(c, "Claude desktop", f, "mcpServers", _voce_mcp(cmd))
                           for f in _config_claude_desktop(c) if f.parent.is_dir()],
           lambda c: None),
    Agente("Codex", lambda c: bool(c.trova("codex")) or (c.casa / ".codex").is_dir(),
           lambda c, cmd: _toml_codex(c, c.casa / ".codex" / "config.toml", cmd),
           lambda c: c.casa / ".agents" / "skills"),
    Agente("Gemini CLI", lambda c: bool(c.trova("gemini")) or (c.casa / ".gemini").is_dir(),
           lambda c, cmd: _json_server(c, "Gemini CLI", c.casa / ".gemini" / "settings.json", "mcpServers", _voce_mcp(cmd)),
           lambda c: c.casa / ".gemini" / "skills"),
    Agente("Cursor", lambda c: (c.casa / ".cursor").is_dir(),
           lambda c, cmd: _json_server(c, "Cursor", c.casa / ".cursor" / "mcp.json", "mcpServers", _voce_mcp(cmd)),
           lambda c: c.casa / ".claude" / "skills"),
    Agente("GitHub Copilot", lambda c: (c.casa / ".copilot").is_dir() or bool(c.trova("copilot")),
           lambda c, cmd: _json_server(c, "GitHub Copilot", c.casa / ".copilot" / "mcp-config.json", "mcpServers",
                                       None if cmd is None else {"type": "stdio", **_voce_mcp(cmd)}),
           lambda c: c.casa / ".copilot" / "skills"),
    Agente("OpenCode", lambda c: bool(c.trova("opencode")) or (c.casa / ".config" / "opencode").is_dir()
           or any(p.exists() for p in _opencode_desktop(c)),
           lambda c, cmd: _json_server(c, "OpenCode", c.casa / ".config" / "opencode" / "opencode.json", "mcp",
                                       None if cmd is None else {"type": "local", "command": cmd, "enabled": True}),
           lambda c: c.casa / ".agents" / "skills"),
]


# ------------------------------------------------------------------ Skill
def _skill_del_pacchetto() -> list[Path]:
    return sorted(p for p in cartella_skill_pacchetto().iterdir() if (p / "SKILL.md").is_file())


def _installa_skill(ctx: Contesto, cartella: Path) -> None:
    nostre = _skill_del_pacchetto()
    if ctx.prova:
        ctx.righe.append(f"PROVA  Skill: {len(nostre)} in {cartella}")
        return
    cartella.mkdir(parents=True, exist_ok=True)
    saltate = []
    for s in nostre:
        dest = cartella / s.name
        if dest.exists() and not (dest / SEGNO).exists():
            saltate.append(s.name)             # una Skill con lo stesso nome ma non nostra: non si tocca
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(s, dest)
        (dest / SEGNO).write_text("Installata da Agentic 3D: `agentic3d scollega` la toglie.\n", encoding="utf-8")
    ctx.righe.append(f"OK  Skill: {len(nostre) - len(saltate)} in {cartella}" +
                     (f" (saltate perché già presenti e non di Agentic 3D: {', '.join(saltate)})" if saltate else ""))


def _togli_skill(ctx: Contesto, cartella: Path) -> None:
    tolte = [p for p in cartella.glob(f"*/{SEGNO}")] if cartella.is_dir() else []
    for segno in tolte:
        if not ctx.prova:
            shutil.rmtree(segno.parent)
    if tolte:
        ctx.righe.append(f"{'PROVA' if ctx.prova else 'OK'}  Skill tolte da {cartella}: {len(tolte)}")


# ------------------------------------------------------------------ comando /agentic3d
# Claude Code lo ricava dalla Skill `agentic3d`; OpenCode e Gemini CLI vogliono un file di comando a parte.
SEGNO_COMANDO = "installato da Agentic 3D"
TESTO_COMANDO = ("Usa Agentic 3D seguendo la Skill `agentic3d` (poi `lavoro-3d-ciclo-di-vita`). "
                 "Richiesta dell'utente: {argomenti}")
COMANDI = {
    "OpenCode": (lambda c: c.casa / ".config" / "opencode" / "commands" / "agentic3d.md",
                 lambda: ("---\ndescription: Agentic 3D, modelli 3D di interni con norme e SketchUp\n---\n"
                          f"<!-- {SEGNO_COMANDO} -->\n" + TESTO_COMANDO.format(argomenti="$ARGUMENTS") + "\n")),
    "Gemini CLI": (lambda c: c.casa / ".gemini" / "commands" / "agentic3d.toml",
                   lambda: (f"# {SEGNO_COMANDO}\n"
                            'description = "Agentic 3D, modelli 3D di interni con norme e SketchUp"\n'
                            f'prompt = """{TESTO_COMANDO.format(argomenti="{{args}}")}"""\n')),
}


def _comando(ctx: Contesto, agente: str, metti: bool) -> None:
    if agente not in COMANDI:
        return
    percorso, contenuto = COMANDI[agente]
    f = percorso(ctx)
    nostro = f.is_file() and SEGNO_COMANDO in f.read_text(encoding="utf-8", errors="replace")
    if f.is_file() and not nostro:
        if metti:
            ctx.righe.append(f"ATTENZIONE  {agente}: esiste già un comando /agentic3d non di Agentic 3D ({f}): "
                             "non toccato")
        return
    if ctx.prova:
        ctx.righe.append(f"PROVA  {agente}: comando /agentic3d {'in' if metti else 'tolto da'} {f}")
        return
    if metti:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenuto(), encoding="utf-8")
        ctx.righe.append(f"OK  {agente}: comando /agentic3d")
    elif nostro:
        f.unlink()
        ctx.righe.append(f"OK  {agente}: comando /agentic3d tolto")


def zip_skill_claude_desktop(destinazione: Path) -> list[Path]:
    """Un file ZIP per Skill, nel formato che Claude desktop accetta (cartella della Skill al primo livello)."""
    destinazione.mkdir(parents=True, exist_ok=True)
    fatti = []
    for s in _skill_del_pacchetto():
        z = destinazione / f"{s.name}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as archivio:
            for f in sorted(s.rglob("*")):
                if f.is_file():
                    archivio.write(f, f"{s.name}/{f.relative_to(s).as_posix()}")
        fatti.append(z)
    return fatti


# ------------------------------------------------------------------ comandi
def collega(ctx: Contesto | None = None, comando: list[str] | None = None) -> list[str]:
    ctx = ctx or Contesto()
    comando = comando or comando_server()
    trovati = [a for a in AGENTI if a.presente(ctx)]
    if not ctx.prova:
        conf.prepara_cartella_lavori()
    if not trovati:
        return ["ATTENZIONE  nessun agente trovato (Claude, Codex, Gemini CLI, Cursor, Copilot, OpenCode): "
                "installane uno, aprilo una volta e rilancia l'installazione di Agentic 3D."]
    ctx.righe.append(f"Agenti trovati: {', '.join(a.nome for a in trovati)}")
    ctx.righe.append(f"Server MCP: {' '.join(comando)}")
    for a in trovati:
        a.server(ctx, comando)
        _comando(ctx, a.nome, True)
    for cartella in dict.fromkeys(a.skill(ctx) for a in trovati if a.skill(ctx)):
        _installa_skill(ctx, cartella)
    if any(a.nome == "Claude desktop" for a in trovati):
        zip_dir = conf.cartella_configurazione() / "Skill per Claude desktop"
        if not ctx.prova:
            zip_skill_claude_desktop(zip_dir)
        ctx.righe.append(f"{'PROVA' if ctx.prova else 'DA FARE'}  Claude desktop: carica una volta le Skill da {zip_dir} "
                         "(Personalizza > Skill > + > Carica una skill), poi riavvia Claude.")
    if ctx.copie:
        ctx.righe.append(f"Copie di sicurezza dei file cambiati: {ctx.copie}")
    ctx.righe.append("Riavvia gli agenti aperti perché vedano il server e le Skill.")
    mancanti = [a.nome for a in AGENTI if a not in trovati]
    ctx.righe.append(f"COLLEGATO A: {', '.join(a.nome for a in trovati)}")
    if mancanti:
        ctx.righe.append(f"NON TROVATI: {', '.join(mancanti)}. Se usi uno di questi, aprilo una volta e rilancia "
                         "l'installazione di Agentic 3D.")
    return ctx.righe


# file in cui ogni agente tiene i server MCP (per controllare il collegamento senza modificarlo)
FILE_SERVER = {
    "Claude Code": lambda c: [c.casa / ".claude.json"],
    "Claude desktop": _config_claude_desktop,
    "Codex": lambda c: [c.casa / ".codex" / "config.toml"],
    "Gemini CLI": lambda c: [c.casa / ".gemini" / "settings.json"],
    "Cursor": lambda c: [c.casa / ".cursor" / "mcp.json"],
    "GitHub Copilot": lambda c: [c.casa / ".copilot" / "mcp-config.json"],
    "OpenCode": lambda c: [c.casa / ".config" / "opencode" / "opencode.json"],
}


def stato_collegamenti(ctx: Contesto | None = None) -> list[str]:
    """Per ogni agente installato: server MCP e Skill di Agentic 3D presenti? Solo lettura."""
    ctx = ctx or Contesto()
    righe = []
    for a in AGENTI:
        if not a.presente(ctx):
            continue
        server = False
        for f in FILE_SERVER[a.nome](ctx):
            try:
                testo = f.read_text(encoding="utf-8")
            except OSError:
                continue
            server = server or f'"{NOME_SERVER}"' in senza_commenti(testo) or INIZIO_TOML in testo
        cartella = a.skill(ctx)
        skill = cartella is None or (cartella / "lavoro-3d-ciclo-di-vita" / SEGNO).is_file() or \
            (cartella / "lavoro-3d-ciclo-di-vita" / "SKILL.md").is_file()
        if server and skill:
            righe.append(f"OK  {a.nome}: server MCP e Skill di Agentic 3D collegati")
        else:
            manca = " e ".join(x for x, ok in (("server MCP", server), ("Skill", skill)) if not ok)
            righe.append(f"ATTENZIONE  {a.nome}: non trovati {manca} di Agentic 3D. Rimedio: `agentic3d collega`, "
                         "poi riavvia l'agente")
    return righe or ["ATTENZIONE  nessun agente AI trovato (Claude, Codex, Gemini CLI, Cursor, Copilot, OpenCode). "
                     "Rimedio: installane uno, poi `agentic3d collega`"]


def scollega(ctx: Contesto | None = None) -> list[str]:
    ctx = ctx or Contesto()
    for a in AGENTI:
        if a.presente(ctx):
            a.server(ctx, None)
        _comando(ctx, a.nome, False)
    for cartella in dict.fromkeys(a.skill(ctx) for a in AGENTI if a.skill(ctx)):
        _togli_skill(ctx, cartella)
    if ctx.copie:
        ctx.righe.append(f"Copie di sicurezza dei file cambiati: {ctx.copie}")
    return ctx.righe or ["Niente da togliere."]
