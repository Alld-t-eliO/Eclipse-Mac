from __future__ import annotations

import shlex
from pathlib import Path

from . import style as ui
from .errors import EclipseError
from .inbox import copy_path, format_entry, list_entries, make_directory, move_path, open_path, read_text, rename_path, trash_path, write_text
from .local_system import LocalStatus, local_status
from .memory import add_memory, filter_memories, load_memories, summarize
from .security import DEFAULT_CHECKS, format_findings, run_checks, write_report
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
    current = Path.home()
    while True:
        current = current.expanduser().resolve()
        header("FICHIERS // EXPLORATEUR")
        print(f"  {ui.neon(str(current), bold=True)}\n")
        entries = list_entries(current, limit=30)
        if entries:
            for index, entry in enumerate(entries, 1):
                marker = "/" if entry.kind == "directory" else ""
                print(ui.menu_line(f"[{index}]", f"{format_entry(entry)}{marker}"))
        else:
            print(f"  {ui.muted('Aucun fichier visible.')}")
        print()
        print(ui.menu_line("[cd]", "aller à un chemin"))
        print(ui.menu_line("[..]", "dossier parent"))
        print(ui.menu_line("[cat]", "aperçu fichier texte"))
        print(ui.menu_line("[new]", "créer fichier texte"))
        print(ui.menu_line("[mkdir]", "créer dossier"))
        print(ui.menu_line("[ren]", "renommer"))
        print(ui.menu_line("[cp]", "copier"))
        print(ui.menu_line("[mv]", "déplacer"))
        print(ui.menu_line("[trash]", "envoyer à la Corbeille"))
        print(ui.menu_line("[open]", "ouvrir avec macOS"))
        print(ui.menu_line("[0]", "Retour"), "\n")
        choice = input(ui.prompt("Action ou numéro")).strip()
        if choice == "0":
            return
        try:
            if choice == "..":
                current = current.parent
            elif choice.isdigit() and 1 <= int(choice) <= len(entries):
                selected = entries[int(choice) - 1]
                if selected.kind == "directory":
                    current = selected.path
                else:
                    print()
                    print(read_text(selected.path, max_bytes=12000))
                    pause()
            elif choice == "cd":
                current = Path(input(ui.prompt("Chemin")).strip() or str(current))
            elif choice == "cat":
                path = Path(input(ui.prompt("Fichier")).strip())
                target = path if path.is_absolute() else current / path
                print()
                print(read_text(target, max_bytes=12000))
                pause()
            elif choice == "new":
                path = Path(input(ui.prompt("Fichier")).strip())
                target = path if path.is_absolute() else current / path
                text = input(ui.prompt("Texte")).strip()
                overwrite = input(ui.prompt("Écraser si existe [oui/N]")).strip().lower() == "oui"
                print(f"  {ui.success('●')} Fichier écrit : {write_text(target, text, overwrite=overwrite)}")
                pause()
            elif choice == "mkdir":
                path = Path(input(ui.prompt("Dossier")).strip())
                target = path if path.is_absolute() else current / path
                print(f"  {ui.success('●')} Dossier créé : {make_directory(target)}")
                pause()
            elif choice == "ren":
                path = Path(input(ui.prompt("Chemin")).strip())
                target = path if path.is_absolute() else current / path
                name = input(ui.prompt("Nouveau nom")).strip()
                print(f"  {ui.success('●')} Renommage : {rename_path(target, name)}")
                pause()
            elif choice in {"cp", "mv"}:
                source_raw = Path(input(ui.prompt("Source")).strip())
                destination_raw = Path(input(ui.prompt("Destination")).strip())
                source = source_raw if source_raw.is_absolute() else current / source_raw
                destination = destination_raw if destination_raw.is_absolute() else current / destination_raw
                overwrite = input(ui.prompt("Écraser si existe [oui/N]")).strip().lower() == "oui"
                action = copy_path if choice == "cp" else move_path
                print(f"  {ui.success('●')} Résultat : {action(source, destination, overwrite=overwrite)}")
                pause()
            elif choice == "trash":
                path = Path(input(ui.prompt("Chemin")).strip())
                target = path if path.is_absolute() else current / path
                answer = input(ui.prompt(f"Envoyer {target} à la Corbeille [oui/N]")).strip().lower()
                if answer == "oui":
                    print(f"  {ui.success('●')} Corbeille : {trash_path(target)}")
                pause()
            elif choice == "open":
                path = Path(input(ui.prompt("Chemin")).strip() or str(current))
                target = path if path.is_absolute() else current / path
                print(f"  {ui.success('●')} Ouverture : {open_path(target)}")
                pause()
            else:
                print(ui.danger("Choix invalide."))
                pause()
        except EclipseError as error:
            print(ui.danger(f"\n  ✗ {error}"))
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
                source = " · drop-in" if script.source == "drop-in" else ""
                print(ui.menu_line(f"[{index}]", f"{script.name}{tags}{source}{description}"))
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


def security_menu() -> None:
    checks = (
        ("security", "Contrôles Apple"),
        ("firewall", "Firewall"),
        ("sharing", "Partage distant"),
        ("network", "Réseau"),
        ("persistence", "Persistance"),
        ("services", "Services"),
        ("updates", "Mises à jour"),
        ("filesystem", "Fichiers sensibles"),
        ("processes", "Processus"),
        ("docker", "Docker"),
    )
    while True:
        header("ADMINISTRATION & SÉCURITÉ")
        print(ui.menu_line("[1]", "Scan rapide"))
        print(ui.menu_line("[2]", "Rapport JSON complet"))
        for index, (_, label) in enumerate(checks, 3):
            print(ui.menu_line(f"[{index}]", label))
        print(ui.menu_line("[0]", "Retour"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "1":
            findings = run_checks(("security", "firewall", "sharing", "updates"))
            print()
            print(format_findings(findings))
        elif choice == "2":
            findings = run_checks(DEFAULT_CHECKS)
            print(f"\n  {ui.success('●')} Rapport : {write_report(findings)}")
        elif choice.isdigit() and 3 <= int(choice) < 3 + len(checks):
            check = checks[int(choice) - 3][0]
            findings = run_checks((check,))
            print()
            print(format_findings(findings))
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
            ui.menu_line("[5]", "Administration & sécurité"),
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
            "5": security_menu,
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
