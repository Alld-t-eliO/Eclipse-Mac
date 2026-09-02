from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import EclipseError
from .inbox import (
    copy_path,
    edit_line,
    favorites,
    file_info,
    format_entry,
    list_entries,
    local_files,
    make_directory,
    make_executable,
    move_path,
    open_path,
    preview_path,
    read_text,
    rename_path,
    search_entries,
    trash_path,
    write_text,
)
from .local_system import common_folders, local_status
from .memory import MemoryEntry, add_memory, export_json, filter_memories, load_memories, summarize
from .security import DEFAULT_CHECKS, format_findings, run_checks, write_report
from .scripts import add_script, get_script, load_scripts, remove_script, run_script
from .ui import launch


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="eclipse", description="Centre de contrôle local pour macOS")
    root.add_argument("--version", action="version", version=f"Eclipse {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    mac = commands.add_parser("mac", help="inspecter le Mac local")
    mac_commands = mac.add_subparsers(dest="mac_command", required=True)
    mac_commands.add_parser("status", help="afficher l'état local du Mac")
    item = mac_commands.add_parser("files", help="lister un dossier local courant")
    item.add_argument("folder", nargs="?", choices=["desktop", "downloads", "documents", "pictures", "movies", "music"])
    item.add_argument("--limit", type=int, default=20)

    commands.add_parser("ui", help="ouvrir le centre de contrôle Mac interactif")

    files = commands.add_parser("files", aliases=["file"], help="explorer et gérer les fichiers locaux")
    files_commands = files.add_subparsers(dest="files_command", required=True)

    item = files_commands.add_parser("ls", help="lister un dossier")
    item.add_argument("path", nargs="?", type=Path, default=Path.home())
    item.add_argument("--limit", type=int, default=50)
    item.add_argument("--hidden", action="store_true", help="inclure les fichiers cachés")

    files_commands.add_parser("favorites", help="lister les emplacements rapides")

    item = files_commands.add_parser("info", help="afficher les permissions et métadonnées")
    item.add_argument("path", type=Path)

    item = files_commands.add_parser("cat", help="afficher un fichier texte")
    item.add_argument("path", type=Path)
    item.add_argument("--max-bytes", type=int, default=20000)

    item = files_commands.add_parser("write", help="écrire un fichier texte")
    item.add_argument("path", type=Path)
    item.add_argument("text", nargs="+")
    item.add_argument("--append", action="store_true")
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirmer l'écriture dans un chemin protégé")
    item.add_argument("--no-backup", action="store_true", help="ne pas créer de sauvegarde avant modification")

    item = files_commands.add_parser("edit-line", help="remplacer une ligne dans un fichier texte")
    item.add_argument("path", type=Path)
    item.add_argument("line", type=int)
    item.add_argument("text", nargs="+")
    item.add_argument("--yes", action="store_true", help="confirmer l'édition dans un chemin protégé")
    item.add_argument("--no-backup", action="store_true", help="ne pas créer de sauvegarde avant modification")

    item = files_commands.add_parser("mkdir", help="créer un dossier")
    item.add_argument("path", type=Path)
    item.add_argument("--yes", action="store_true", help="confirmer la création dans un chemin protégé")

    item = files_commands.add_parser("copy", help="copier un fichier ou dossier")
    item.add_argument("source", type=Path)
    item.add_argument("destination", type=Path)
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirmer la copie vers un chemin protégé")
    item.add_argument("--no-backup", action="store_true", help="ne pas sauvegarder la destination avant remplacement")

    item = files_commands.add_parser("move", help="déplacer un fichier ou dossier")
    item.add_argument("source", type=Path)
    item.add_argument("destination", type=Path)
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirmer le déplacement d'un chemin protégé")
    item.add_argument("--no-backup", action="store_true", help="ne pas créer de sauvegarde avant modification")

    item = files_commands.add_parser("rename", help="renommer un fichier ou dossier")
    item.add_argument("source", type=Path)
    item.add_argument("name")
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirmer le renommage d'un chemin protégé")
    item.add_argument("--no-backup", action="store_true", help="ne pas créer de sauvegarde avant modification")

    item = files_commands.add_parser("trash", help="déplacer vers la Corbeille")
    item.add_argument("path", type=Path)
    item.add_argument("--yes", action="store_true", help="confirmer l'action")
    item.add_argument("--no-backup", action="store_true", help="ne pas créer de sauvegarde avant modification")

    item = files_commands.add_parser("open", help="ouvrir avec macOS")
    item.add_argument("path", type=Path)

    item = files_commands.add_parser("preview", help="prévisualiser fichier, dossier, image ou archive")
    item.add_argument("path", type=Path)
    item.add_argument("--max-bytes", type=int, default=20000)

    item = files_commands.add_parser("search", help="chercher par nom sous un dossier")
    item.add_argument("root", type=Path)
    item.add_argument("query", nargs="?")
    item.add_argument("--name", help="motif de nom, par exemple *.py")
    item.add_argument("--depth", type=int, default=4)
    item.add_argument("--limit", type=int, default=50)
    item.add_argument("--hidden", action="store_true")

    item = files_commands.add_parser("chmod+x", help="rendre un fichier exécutable")
    item.add_argument("path", type=Path)
    item.add_argument("--yes", action="store_true", help="confirmer la modification dans un chemin protégé")

    item = files_commands.add_parser("script-add", help="ajouter un fichier aux scripts Eclipse")
    item.add_argument("path", type=Path)
    item.add_argument("name", nargs="?")
    item.add_argument("--tag", action="append", default=[])
    item.add_argument("--overwrite", action="store_true")

    security = commands.add_parser("security", help="auditer la sécurité du Mac")
    security_commands = security.add_subparsers(dest="security_command", required=True)
    item = security_commands.add_parser("scan", help="lancer un audit sécurité")
    item.add_argument("--check", action="append", choices=DEFAULT_CHECKS, help="check ciblé, répétable")
    item.add_argument("--deep", action="store_true", help="lancer les checks plus longs")
    item.add_argument("--json", action="store_true", help="écrire un rapport JSON privé")
    item.add_argument("--output-dir", type=Path, help="dossier des rapports JSON")

    admin = commands.add_parser("admin", help="administrer l'état local du Mac")
    admin_commands = admin.add_subparsers(dest="admin_command", required=True)
    admin_commands.add_parser("status", help="afficher un résumé système et sécurité")
    item = admin_commands.add_parser("report", help="écrire un rapport sécurité JSON")
    item.add_argument("--deep", action="store_true")
    item.add_argument("--output-dir", type=Path)

    memory = commands.add_parser("memory", aliases=["mem"], help="gérer la mémoire locale macOS")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)

    item = memory_commands.add_parser("add", help="capturer une observation locale")
    item.add_argument("text", nargs="+")
    item.add_argument("--tag", action="append", default=[], help="tag, répétable ou séparé par virgules")
    item.add_argument("--source", help="origine de la note")
    item.add_argument("--project", help="projet associé")

    item = memory_commands.add_parser("list", help="lister les dernières mémoires")
    item.add_argument("--tag", help="filtrer par tag")
    item.add_argument("--project", help="filtrer par projet")
    item.add_argument("--limit", type=int, default=20)

    item = memory_commands.add_parser("search", help="chercher dans la mémoire locale")
    item.add_argument("query")
    item.add_argument("--tag", help="filtrer par tag")
    item.add_argument("--project", help="filtrer par projet")
    item.add_argument("--limit", type=int, default=20)

    item = memory_commands.add_parser("export", help="exporter la mémoire en JSON")
    item.add_argument("destination", type=Path)

    memory_commands.add_parser("stats", help="résumer la mémoire locale")

    scripts = commands.add_parser("scripts", aliases=["script"], help="stocker et exécuter des scripts locaux macOS")
    scripts_commands = scripts.add_subparsers(dest="scripts_command", required=True)

    item = scripts_commands.add_parser("add", help="enregistrer un script personnel")
    item.add_argument("name")
    item.add_argument("source", type=Path)
    item.add_argument("--description")
    item.add_argument("--tag", action="append", default=[], help="tag, répétable ou séparé par virgules")
    item.add_argument("--overwrite", action="store_true")

    scripts_commands.add_parser("list", help="lister les scripts enregistrés")

    item = scripts_commands.add_parser("path", help="afficher le chemin local d'un script")
    item.add_argument("name")

    item = scripts_commands.add_parser("remove", help="retirer un script du registre")
    item.add_argument("name")
    item.add_argument("--delete-file", action="store_true", help="supprimer aussi la copie locale")

    item = scripts_commands.add_parser("run", help="exécuter un script local")
    item.add_argument("name")
    item.add_argument("--dry-run", action="store_true")
    item.add_argument("arguments", nargs=argparse.REMAINDER)
    return root


def print_memory(entries: list[MemoryEntry], *, limit: int) -> None:
    if limit < 1:
        raise EclipseError("La limite doit être positive.")
    rows = entries[-limit:]
    if not rows:
        print("Aucune mémoire.")
        return
    for entry in reversed(rows):
        tags = f" #{' #'.join(entry.tags)}" if entry.tags else ""
        project = f" [{entry.project}]" if entry.project else ""
        print(f"{entry.id}  {entry.created_at}{project}{tags}")
        print(f"  {entry.text}")


def print_mac_status() -> None:
    status = local_status()
    print(f"Mac : {status.hostname}")
    print(f"macOS : {status.release or status.system}")
    print(f"Architecture : {status.machine}")
    print(f"CPU : {status.processor or 'N/D'}")
    print(f"RAM : {status.memory_percent:.1f}%")
    print(f"Disque / : {status.disk.percent:.1f}%")
    print(f"Home : {status.home}")


def folder_map() -> dict[str, Path]:
    folders = common_folders()
    return {
        "desktop": folders[0],
        "downloads": folders[1],
        "documents": folders[2],
        "pictures": folders[3],
        "movies": folders[4],
        "music": folders[5],
    }


def script_run_options(values: list[str], *, dry_run: bool) -> tuple[bool, list[str]]:
    if "--" in values:
        separator = values.index("--")
        eclipse_options = values[:separator]
        script_values = values[separator + 1:]
    else:
        eclipse_options = values
        script_values = []
    for option in eclipse_options:
        if option == "--dry-run":
            dry_run = True
        else:
            script_values.append(option)
    return dry_run, script_values


def dispatch(args: argparse.Namespace) -> None:
    if args.command == "ui":
        launch()
        return
    if args.command == "mac":
        if args.mac_command == "status":
            print_mac_status()
        elif args.mac_command == "files":
            folder = folder_map().get(args.folder or "downloads")
            print(f"{folder}")
            print("\n".join(local_files(folder, limit=args.limit)) or "Aucun fichier.")
        return
    if args.command in {"files", "file"}:
        if args.files_command == "ls":
            entries = list_entries(args.path, limit=args.limit, include_hidden=args.hidden)
            print(args.path.expanduser().resolve())
            print("\n".join(format_entry(entry) for entry in entries) or "Aucun fichier.")
        elif args.files_command == "favorites":
            for name, path in favorites().items():
                print(f"{name}: {path}")
        elif args.files_command == "info":
            print("\n".join(file_info(args.path)))
        elif args.files_command == "cat":
            print(read_text(args.path, max_bytes=args.max_bytes), end="")
        elif args.files_command == "write":
            print(
                f"Fichier écrit : "
                f"{write_text(args.path, ' '.join(args.text), append=args.append, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}"
            )
        elif args.files_command == "edit-line":
            print(f"Fichier édité : {edit_line(args.path, args.line, ' '.join(args.text), confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "mkdir":
            print(f"Dossier créé : {make_directory(args.path, confirmed=args.yes)}")
        elif args.files_command == "copy":
            print(f"Copie : {copy_path(args.source, args.destination, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "move":
            print(f"Déplacement : {move_path(args.source, args.destination, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "rename":
            print(f"Renommage : {rename_path(args.source, args.name, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "trash":
            if not args.yes:
                raise EclipseError("Ajoute --yes pour confirmer le déplacement vers la Corbeille.")
            print(f"Corbeille : {trash_path(args.path, confirmed=True, create_backup=not args.no_backup)}")
        elif args.files_command == "open":
            print(f"Ouverture : {open_path(args.path)}")
        elif args.files_command == "preview":
            preview = preview_path(args.path, max_bytes=args.max_bytes)
            print("\n".join(preview.details))
            if preview.content is not None:
                print()
                print(preview.content)
        elif args.files_command == "search":
            entries = search_entries(args.root, args.query, name=args.name, max_depth=args.depth, limit=args.limit, include_hidden=args.hidden)
            print("\n".join(f"{entry.path}  ({entry.kind})" for entry in entries) or "Aucun résultat.")
        elif args.files_command == "chmod+x":
            print(f"Exécutable : {make_executable(args.path, confirmed=args.yes)}")
        elif args.files_command == "script-add":
            script = add_script(args.name or args.path.stem, args.path, tags=args.tag or ["explorer"], overwrite=args.overwrite)
            print(f"Script ajouté : {script.name} → {script.path}")
        return
    if args.command == "security":
        if args.security_command == "scan":
            findings = run_checks(args.check or DEFAULT_CHECKS, deep=args.deep)
            print(format_findings(findings))
            if args.json:
                print(f"\nRapport : {write_report(findings, args.output_dir)}")
        return
    if args.command == "admin":
        if args.admin_command == "status":
            print_mac_status()
            findings = run_checks(("security", "firewall", "sharing", "updates"))
            print()
            print(format_findings(findings))
        elif args.admin_command == "report":
            findings = run_checks(DEFAULT_CHECKS, deep=args.deep)
            print(f"Rapport : {write_report(findings, args.output_dir)}")
        return
    if args.command in {"memory", "mem"}:
        if args.memory_command == "add":
            entry = add_memory(
                " ".join(args.text),
                tags=args.tag,
                source=args.source,
                project=args.project,
            )
            print(f"Mémoire ajoutée : {entry.id}")
        elif args.memory_command == "list":
            entries = filter_memories(load_memories(), tag=args.tag, project=args.project)
            print_memory(entries, limit=args.limit)
        elif args.memory_command == "search":
            entries = filter_memories(load_memories(), query=args.query, tag=args.tag, project=args.project)
            print_memory(entries, limit=args.limit)
        elif args.memory_command == "export":
            print(f"Export : {export_json(args.destination)}")
        elif args.memory_command == "stats":
            data = summarize(load_memories())
            print(f"Mémoires : {data['count']}")
            print("Tags :", data["tags"] or "{}")
            print("Projets :", data["projects"] or "{}")
        return
    if args.command in {"scripts", "script"}:
        if args.scripts_command == "add":
            script = add_script(
                args.name,
                args.source,
                description=args.description,
                tags=args.tag,
                overwrite=args.overwrite,
            )
            print(f"Script ajouté : {script.name} → {script.path}")
        elif args.scripts_command == "list":
            scripts = load_scripts()
            if not scripts:
                print("Aucun script.")
            for script in scripts.values():
                tags = f" #{' #'.join(script.tags)}" if script.tags else ""
                description = f" · {script.description}" if script.description else ""
                source = " · drop-in" if script.source == "drop-in" else ""
                print(f"{script.name}{tags}{source}{description}")
                print(f"  {script.path}")
        elif args.scripts_command == "path":
            print(get_script(args.name).path)
        elif args.scripts_command == "remove":
            script = remove_script(args.name, delete_file=args.delete_file)
            print(f"Script retiré : {script.name}")
        elif args.scripts_command == "run":
            dry_run, arguments = script_run_options(args.arguments, dry_run=args.dry_run)
            result = run_script(args.name, arguments=arguments, dry_run=dry_run)
            if result.returncode:
                raise EclipseError(f"Script échoué : {args.name} (code {result.returncode}).")


def main() -> int:
    try:
        dispatch(parser().parse_args())
        print("✓ Terminé")
        return 0
    except (EclipseError, KeyboardInterrupt) as error:
        message = "Opération interrompue." if isinstance(error, KeyboardInterrupt) else str(error)
        print(f"✗ {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
