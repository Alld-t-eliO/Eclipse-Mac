from __future__ import annotations

import shlex
from pathlib import Path

from . import style as ui
from .errors import EclipseError
from .inbox import local_files
from .local_system import LocalStatus, common_folders, local_status
from .memory import add_memory, filter_memories, load_memories, summarize
from .scripts import load_scripts, run_script

LOGO = r"""
    ______     __  _
   / ____/____/ /_(_)___  ________
  / __/ / ___/ / / / __ \/ ___/ _ \
 / /___/ /__/ / / / /_/ (__  )  __/
/_____/\___/_/_/_/ .___/____/\___/
                /_/
"""


def human_size(value: object) -> str:
    size = float(value or 0)
    for unit in ("o", "Kio", "Mio", "Gio", "Tio"):
        if size < 1024 or unit == "Tio":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} Tio"


def header(title: str = "CENTRE DE CONTRÔLE MAC") -> None:
    status = local_status()
    ui.clear()
    for index, line in enumerate(LOGO.strip("\n").splitlines()):
        print(ui.paint(line, ui.CYAN if index < 3 else ui.MAGENTA, bold=True))
    print(f"\n  {ui.neon(title, bold=True)}")
    print(f"  {ui.muted('MAC')} {ui.accent(status.hostname)} {ui.muted('· SHELL')} {ui.success(status.shell or 'local')}")
    print(f"  {ui.muted('─' * 54)}\n")


def pause() -> None:
    input(f"\n  {ui.muted('Entrée pour revenir au menu…')}")


def local_panel(status: LocalStatus) -> list[str]:
    return [
        ui.neon("╭─ MAC // LOCAL CORE ────────────╮", bold=True),
        f"{ui.neon('│')} {ui.muted('RAM')}  {ui.gauge(status.memory_percent, 13)} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('SSD')}  {ui.gauge(status.disk.percent, 13)} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('OS')}   {ui.accent(status.release or status.system):>24} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('ARCH')} {ui.paint(status.machine, ui.WHITE):>24} {ui.neon('│')}",
        ui.neon("╰────────────────────────────────╯", bold=True),
    ]


def local_status_menu() -> None:
    status = local_status()
    header("MAC // ÉTAT LOCAL")
    print(f"  {ui.muted('Hôte'):<18} {ui.accent(status.hostname)}")
    print(f"  {ui.muted('macOS'):<18} {status.release or status.system}")
    print(f"  {ui.muted('Architecture'):<18} {status.machine}")
    print(f"  {ui.muted('CPU'):<18} {status.processor or 'N/D'}")
    print(f"  {ui.muted('Dossier perso'):<18} {status.home}")
    print(f"  {ui.muted('Shell'):<18} {status.shell or 'N/D'}")
    print(f"\n  {ui.muted('Mémoire')} {ui.gauge(status.memory_percent, 24)} {human_size(status.memory_used)} / {human_size(status.memory_total)}")
    print(f"  {ui.muted('Disque /')} {ui.gauge(status.disk.percent, 24)} {human_size(status.disk.used)} / {human_size(status.disk.total)}")


def local_files_menu() -> None:
    while True:
        header("FICHIERS // MAC LOCAL")
        folders = common_folders()
        for index, folder in enumerate(folders, 1):
            print(ui.menu_line(f"[{index}]", str(folder)))
        print(ui.menu_line("[0]", "Retour"), "\n")
        choice = input(ui.prompt("Dossier")).strip()
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(folders):
            folder = folders[int(choice) - 1]
            header("FICHIERS // MAC LOCAL")
            print(f"  {ui.neon(str(folder), bold=True)}\n")
            rows = local_files(folder, limit=30)
            print("\n".join(f"  {row}" for row in rows) if rows else f"  {ui.muted('Aucun fichier visible.')}")
        else:
            print(ui.danger("Choix invalide."))
        pause()


def memory_menu() -> None:
    while True:
        header("MÉMOIRE // MAC LOCAL")
        data = summarize(load_memories())
        print(f"  {ui.muted('Entrées')} {ui.accent(data['count'])}")
        print(f"  {ui.muted('Tags')}    {data['tags'] or '{}'}")
        print(f"  {ui.muted('Projets')} {data['projects'] or '{}'}\n")
        print(ui.menu_line("[1]", "Lister les dernières mémoires"))
        print(ui.menu_line("[2]", "Chercher dans la mémoire"))
        print(ui.menu_line("[3]", "Ajouter une mémoire"))
        print(ui.menu_line("[0]", "Retour"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "1":
            entries = load_memories()[-20:]
        elif choice == "2":
            query = input(ui.prompt("Recherche")).strip()
            entries = filter_memories(load_memories(), query=query)
        elif choice == "3":
            text = input(ui.prompt("Texte")).strip()
            tags = input(ui.prompt("Tags")).strip()
            project = input(ui.prompt("Projet")).strip()
            entry = add_memory(text, tags=[tags] if tags else [], project=project or None, source="eclipse-ui")
            print(f"  {ui.success('●')} Mémoire ajoutée : {entry.id}")
            pause()
            continue
        else:
            print(ui.danger("Choix invalide."))
            pause()
            continue
        print()
        if not entries:
            print(f"  {ui.muted('Aucune mémoire.')}")
        for entry in reversed(entries):
            tags = f" #{' #'.join(entry.tags)}" if entry.tags else ""
            project = f" [{entry.project}]" if entry.project else ""
            print(f"  {ui.accent(entry.id)} {ui.muted(entry.created_at)}{project}{tags}")
            print(f"    {entry.text}")
        pause()


def local_scripts_menu() -> None:
    while True:
        header("SCRIPTS // MAC LOCAL")
        scripts = list(load_scripts().values())
        if scripts:
            for index, script in enumerate(scripts, 1):
                tags = f" #{' #'.join(script.tags)}" if script.tags else ""
                description = f" · {script.description}" if script.description else ""
                print(ui.menu_line(f"[{index}]", f"{script.name}{tags}{description}"))
        else:
            print(f"  {ui.muted('Aucun script local enregistré.')}")
        print(ui.menu_line("[0]", "Retour"), "\n")
        choice = input(ui.prompt("Script à exécuter")).strip()
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(scripts):
            script = scripts[int(choice) - 1]
            raw_arguments = input(ui.prompt("Arguments optionnels")).strip()
            try:
                arguments = shlex.split(raw_arguments) if raw_arguments else []
            except ValueError as error:
                raise EclipseError(f"Arguments invalides : {error}") from error
            answer = input(ui.prompt(f"Confirmer l'exécution locale de {script.name} [oui/N]")).strip().lower()
            if answer == "oui":
                result = run_script(script.name, arguments=arguments)
                if result.returncode:
                    raise EclipseError(f"Script échoué : {script.name} (code {result.returncode}).")
        else:
            print(ui.danger("Choix invalide."))
        pause()


def launch() -> None:
    ui.boot_animation()
    while True:
        status = local_status()
        header()
        menu = [
            ui.menu_line("[1]", "État du Mac"),
            ui.menu_line("[2]", "Fichiers locaux"),
            ui.menu_line("[3]", "Mémoire locale"),
            ui.menu_line("[4]", "Scripts locaux"),
            ui.menu_line("[0]", "Quitter", danger_action=True),
        ]
        ui.columns(menu, local_panel(status))
        print()
        choice = input(ui.prompt()).strip()
        if choice == "0":
            print(f"\n  {ui.neon('ECLIPSE//SHUTDOWN')} {ui.success('● ARRÊT PROPRE')}")
            return
        actions = {
            "1": local_status_menu,
            "2": local_files_menu,
            "3": memory_menu,
            "4": local_scripts_menu,
        }
        action = actions.get(choice)
        if action is None:
            print(ui.danger("Choix invalide."))
            pause()
            continue
        try:
            action()
        except EclipseError as error:
            print(ui.danger(f"\n  ✗ {error}"))
        pause()
