from __future__ import annotations
import argparse
import sys
from pathlib import Path
from eclipse import __version__
from eclipse.modules.automation import add_job, format_quickstart, format_suggestions, load_history as load_automation_history, load_jobs, run_due, run_job, set_enabled
from eclipse.system.errors import EclipseError
from eclipse.system.inbox import (
    copy_path,
    edit_line,
    export_entries,
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
from eclipse.system.status import common_folders, local_status
from eclipse.core.logs import LOG_SOURCES, collect_logs, export_logs, format_log
from eclipse.system.memory import MemoryEntry, add_memory, export_json, filter_memories, load_memories, summarize
from eclipse.modules.plugins import create_plugin, list_plugins
from eclipse.system.recovery import archive_snapshot, format_snapshot_info, format_snapshot_list, list_snapshots, resolve_snapshot, restore_snapshot, snapshot, snapshot_info
from eclipse.modules.security import (
    DEFAULT_CHECKS,
    REPORT_FORMATS,
    compare_baseline,
    confirm_password_rotation,
    evaluate_policy,
    export_report,
    format_diff_categories,
    format_findings,
    format_policy,
    format_policy_evaluation,
    format_password_status,
    format_report_diff,
    format_report_history,
    format_remediation_plan,
    latest_report_pair,
    load_latest_report,
    load_policy,
    list_checks,
    load_reports,
    password_status,
    remediation_plan,
    run_checks,
    save_baseline,
    write_default_policy,
    write_report,
)
from eclipse.modules.scripts import add_script, get_script, load_history as load_script_history, load_scripts, remove_script, run_script
from eclipse.vps.vps import format_upload_result, upload_path, upload_result_json
from eclipse.core.ui import launch


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="eclipse", description="Local control center for macOS")
    root.add_argument("--version", action="version", version=f"Eclipse {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    mac = commands.add_parser("mac", help="inspect the local Mac")
    mac_commands = mac.add_subparsers(dest="mac_command", required=True)
    mac_commands.add_parser("status", help="show local Mac status")
    item = mac_commands.add_parser("files", help="list a common local folder")
    item.add_argument("folder", nargs="?", choices=["desktop", "downloads", "documents", "pictures", "movies", "music"])
    item.add_argument("--limit", type=int, default=20)

    commands.add_parser("ui", help="open the interactive Mac control center")

    files = commands.add_parser("files", aliases=["file"], help="explore and manage local files")
    files_commands = files.add_subparsers(dest="files_command", required=True)

    item = files_commands.add_parser("ls", help="list a directory")
    item.add_argument("path", nargs="?", type=Path, default=Path.home())
    item.add_argument("--limit", type=int, default=50)
    item.add_argument("--hidden", action="store_true", help="include hidden files")

    files_commands.add_parser("favorites", help="list quick locations")

    item = files_commands.add_parser("info", help="show permissions and metadata")
    item.add_argument("path", type=Path)

    item = files_commands.add_parser("cat", help="show a text file")
    item.add_argument("path", type=Path)
    item.add_argument("--max-bytes", type=int, default=20000)

    item = files_commands.add_parser("write", help="write a text file")
    item.add_argument("path", type=Path)
    item.add_argument("text", nargs="+")
    item.add_argument("--append", action="store_true")
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirm writing to a protected path")
    item.add_argument("--no-backup", action="store_true", help="do not create a backup before modifying")

    item = files_commands.add_parser("edit-line", help="replace a line in a text file")
    item.add_argument("path", type=Path)
    item.add_argument("line", type=int)
    item.add_argument("text", nargs="+")
    item.add_argument("--yes", action="store_true", help="confirm editing a protected path")
    item.add_argument("--no-backup", action="store_true", help="do not create a backup before modifying")

    item = files_commands.add_parser("mkdir", help="create a directory")
    item.add_argument("path", type=Path)
    item.add_argument("--yes", action="store_true", help="confirm creation in a protected path")

    item = files_commands.add_parser("copy", help="copy a file or directory")
    item.add_argument("source", type=Path)
    item.add_argument("destination", type=Path)
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirm copying to a protected path")
    item.add_argument("--no-backup", action="store_true", help="do not back up the destination before replacing")

    item = files_commands.add_parser("move", help="move a file or directory")
    item.add_argument("source", type=Path)
    item.add_argument("destination", type=Path)
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirm moving a protected path")
    item.add_argument("--no-backup", action="store_true", help="do not create a backup before modifying")

    item = files_commands.add_parser("rename", help="rename a file or directory")
    item.add_argument("source", type=Path)
    item.add_argument("name")
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--yes", action="store_true", help="confirm renaming a protected path")
    item.add_argument("--no-backup", action="store_true", help="do not create a backup before modifying")

    item = files_commands.add_parser("trash", help="move to Trash")
    item.add_argument("path", type=Path)
    item.add_argument("--yes", action="store_true", help="confirm the action")
    item.add_argument("--no-backup", action="store_true", help="do not create a backup before modifying")

    item = files_commands.add_parser("open", help="open with macOS")
    item.add_argument("path", type=Path)

    item = files_commands.add_parser("preview", help="preview a file, directory, image, or archive")
    item.add_argument("path", type=Path)
    item.add_argument("--max-bytes", type=int, default=20000)

    item = files_commands.add_parser("search", help="search under a directory")
    item.add_argument("root", type=Path)
    item.add_argument("query", nargs="?")
    item.add_argument("--name", help="name pattern, for example *.py")
    item.add_argument("--content", help="search UTF-8 content")
    item.add_argument("--extension", help="filter by extension")
    item.add_argument("--min-size", type=int)
    item.add_argument("--max-size", type=int)
    item.add_argument("--modified-after", help="date ISO YYYY-MM-DD")
    item.add_argument("--modified-before", help="date ISO YYYY-MM-DD")
    item.add_argument("--ignore", action="append", default=[], help="directory/file pattern to ignore")
    item.add_argument("--depth", type=int, default=4)
    item.add_argument("--limit", type=int, default=50)
    item.add_argument("--hidden", action="store_true")
    item.add_argument("--export", type=Path, help="export JSON results")

    item = files_commands.add_parser("chmod+x", help="make a file executable")
    item.add_argument("path", type=Path)
    item.add_argument("--yes", action="store_true", help="confirm modification of a protected path")

    item = files_commands.add_parser("script-add", help="add a file to Eclipse scripts")
    item.add_argument("path", type=Path)
    item.add_argument("name", nargs="?")
    item.add_argument("--tag", action="append", default=[])
    item.add_argument("--overwrite", action="store_true")

    security = commands.add_parser("security", help="audit Mac security")
    security_commands = security.add_subparsers(dest="security_command", required=True)
    item = security_commands.add_parser("scan", help="run a security audit")
    item.add_argument("--check", action="append", choices=DEFAULT_CHECKS, help="targeted check, repeatable")
    item.add_argument("--deep", action="store_true", help="run slower checks")
    item.add_argument("--json", action="store_true", help="write a private JSON report")
    item.add_argument("--output-dir", type=Path, help="JSON reports directory")
    checks_item = security_commands.add_parser("checks", help="list available security checks")
    checks_item.add_argument("--verbose", action="store_true")
    item = security_commands.add_parser("history", help="list security report history")
    item.add_argument("--limit", type=int, default=20)
    item.add_argument("--report-dir", type=Path)
    item = security_commands.add_parser("diff", help="compare the latest two security reports")
    item.add_argument("--report-dir", type=Path)
    baseline = security_commands.add_parser("baseline", help="save or compare a security baseline")
    baseline_commands = baseline.add_subparsers(dest="baseline_command", required=True)
    item = baseline_commands.add_parser("save", help="save the current expected security state")
    item.add_argument("--path", type=Path)
    item.add_argument("--check", action="append", choices=DEFAULT_CHECKS, help="targeted check, repeatable")
    item.add_argument("--deep", action="store_true")
    item = baseline_commands.add_parser("compare", help="compare current security state with the saved baseline")
    item.add_argument("--path", type=Path)
    item.add_argument("--check", action="append", choices=DEFAULT_CHECKS, help="targeted check, repeatable")
    item.add_argument("--deep", action="store_true")
    policy = security_commands.add_parser("policy", help="manage local security severity policy")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    item = policy_commands.add_parser("init", help="write the default local security policy")
    item.add_argument("--path", type=Path)
    item.add_argument("--overwrite", action="store_true")
    item = policy_commands.add_parser("show", help="show the active local security policy")
    item.add_argument("--path", type=Path)
    item = policy_commands.add_parser("check", help="evaluate a scan against the active policy")
    item.add_argument("--path", type=Path)
    item.add_argument("--check", action="append", choices=DEFAULT_CHECKS, help="targeted check, repeatable")
    item.add_argument("--deep", action="store_true")
    report = security_commands.add_parser("report", help="export the latest security report")
    report_commands = report.add_subparsers(dest="report_command", required=True)
    item = report_commands.add_parser("export", help="export the latest report as JSON, Markdown, or HTML")
    item.add_argument("--format", choices=REPORT_FORMATS, default="markdown")
    item.add_argument("--output", required=True, type=Path)
    item.add_argument("--report-dir", type=Path)
    remediate = security_commands.add_parser("remediate", help="show read-only remediation guidance")
    remediate_commands = remediate.add_subparsers(dest="remediate_command", required=True)
    item = remediate_commands.add_parser("plan", help="plan remediations without changing the system")
    item.add_argument("--check", action="append", choices=DEFAULT_CHECKS, help="targeted check, repeatable")
    item.add_argument("--deep", action="store_true", help="run slower checks")
    secrets = security_commands.add_parser("secrets", help="run local secret checks")
    secrets_commands = secrets.add_subparsers(dest="secrets_command", required=True)
    item = secrets_commands.add_parser("scan", help="scan a folder for likely secrets")
    item.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    item.add_argument("--limit", type=int, default=100)
    downloads = security_commands.add_parser("downloads", help="inspect downloaded files")
    downloads_commands = downloads.add_subparsers(dest="downloads_command", required=True)
    item = downloads_commands.add_parser("quarantine", help="list quarantined downloaded files")
    item.add_argument("--folder", type=Path, default=Path.home() / "Downloads")
    dmg = security_commands.add_parser("dmg", help="inspect disk images before opening")
    dmg_commands = dmg.add_subparsers(dest="dmg_command", required=True)
    item = dmg_commands.add_parser("inspect", help="inspect a local DMG")
    item.add_argument("path", type=Path)
    item.add_argument("--open", action="store_true", help="open the DMG after inspection")
    password = security_commands.add_parser("password", help="track password rotation")
    password_commands = password.add_subparsers(dest="password_command", required=True)
    password_commands.add_parser("status", help="show rotation status")
    password_commands.add_parser("confirm", help="confirm that passwords have been changed")

    admin = commands.add_parser("admin", help="administer local Mac state")
    admin_commands = admin.add_subparsers(dest="admin_command", required=True)
    admin_commands.add_parser("status", help="show a system and security summary")
    item = admin_commands.add_parser("report", help="write a JSON security report")
    item.add_argument("--deep", action="store_true")
    item.add_argument("--output-dir", type=Path)

    memory = commands.add_parser("memory", aliases=["mem"], help="manage local macOS memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)

    item = memory_commands.add_parser("add", help="capture a local observation")
    item.add_argument("text", nargs="+")
    item.add_argument("--tag", action="append", default=[], help="tag, repeatable or comma-separated")
    item.add_argument("--source", help="note source")
    item.add_argument("--project", help="associated project")

    item = memory_commands.add_parser("list", help="list latest memories")
    item.add_argument("--tag", help="filter by tag")
    item.add_argument("--project", help="filter by project")
    item.add_argument("--limit", type=int, default=20)

    item = memory_commands.add_parser("search", help="search local memory")
    item.add_argument("query")
    item.add_argument("--tag", help="filter by tag")
    item.add_argument("--project", help="filter by project")
    item.add_argument("--limit", type=int, default=20)

    item = memory_commands.add_parser("export", help="export memory as JSON")
    item.add_argument("destination", type=Path)

    memory_commands.add_parser("stats", help="summarize local memory")

    scripts = commands.add_parser("scripts", aliases=["script"], help="store and run local macOS scripts")
    scripts_commands = scripts.add_subparsers(dest="scripts_command", required=True)

    item = scripts_commands.add_parser("add", help="register a personal script")
    item.add_argument("name")
    item.add_argument("source", type=Path)
    item.add_argument("--description")
    item.add_argument("--tag", action="append", default=[], help="tag, repeatable or comma-separated")
    item.add_argument("--overwrite", action="store_true")
    item.add_argument("--dry-run-required", action="store_true")

    scripts_commands.add_parser("list", help="list registered scripts")

    item = scripts_commands.add_parser("info", help="show the detailed catalog for a script")
    item.add_argument("name")

    item = scripts_commands.add_parser("history", help="show script execution history")
    item.add_argument("--limit", type=int, default=20)

    item = scripts_commands.add_parser("path", help="show a script's local path")
    item.add_argument("name")

    item = scripts_commands.add_parser("remove", help="remove a script from the registry")
    item.add_argument("name")
    item.add_argument("--delete-file", action="store_true", help="also delete the local copy")

    item = scripts_commands.add_parser("run", help="run a local script")
    item.add_argument("name")
    item.add_argument("--dry-run", action="store_true")
    item.add_argument("--force", action="store_true", help="force execution of a script marked dry-run required")
    item.add_argument("arguments", nargs=argparse.REMAINDER)

    automation = commands.add_parser("automation", aliases=["auto"], help="manage scheduled automations")
    automation_commands = automation.add_subparsers(dest="automation_command", required=True)
    item = automation_commands.add_parser("add", help="add an automation")
    item.add_argument("name")
    item.add_argument("--every", required=True, choices=["hour", "day", "week"])
    item.add_argument("--command", dest="automation_exec", nargs="+", help="Eclipse command to run, without the word eclipse")
    item.add_argument("--overwrite", action="store_true")
    automation_commands.add_parser("list", help="list automations")
    automation_commands.add_parser("suggestions", help="show beginner-friendly automation suggestions")
    automation_commands.add_parser("quickstart", help="show simple commands for running automations")
    item = automation_commands.add_parser("run", help="run an automation")
    item.add_argument("name")
    item.add_argument("--dry-run", action="store_true")
    item = automation_commands.add_parser("run-due", help="run due automations")
    item.add_argument("--dry-run", action="store_true")
    item = automation_commands.add_parser("enable", help="enable an automation")
    item.add_argument("name")
    item = automation_commands.add_parser("disable", help="disable an automation")
    item.add_argument("name")
    item = automation_commands.add_parser("history", help="show automation history")
    item.add_argument("--limit", type=int, default=20)

    plugins = commands.add_parser("plugins", aliases=["plugin"], help="manage Eclipse modules")
    plugins_commands = plugins.add_subparsers(dest="plugins_command", required=True)
    plugins_commands.add_parser("list", help="list plugins")
    item = plugins_commands.add_parser("create", help="create a plugin skeleton")
    item.add_argument("name")
    item.add_argument("--description", default="")

    recovery = commands.add_parser("recovery", help="snapshots, backups, and restore")
    recovery_commands = recovery.add_subparsers(dest="recovery_command", required=True)
    item = recovery_commands.add_parser("snapshot", help="create a local snapshot")
    item.add_argument("--destination", type=Path)
    item = recovery_commands.add_parser("view", help="list snapshots or show one snapshot's contents")
    item.add_argument("snapshot", nargs="?")
    item.add_argument("--root", type=Path, help="recovery folder to inspect")
    item.add_argument("--limit", type=int, default=200, help="maximum content entries to show")
    item = recovery_commands.add_parser("export", help="export a snapshot as an archive")
    item.add_argument("snapshot", type=Path)
    item.add_argument("--destination", type=Path)
    item.add_argument("--password", help="password for simple encrypted export")
    item = recovery_commands.add_parser("load", help="load a snapshot into a destination folder")
    item.add_argument("snapshot")
    item.add_argument("--destination", type=Path)
    item.add_argument("--root", type=Path, help="recovery folder used for snapshot names")
    item.add_argument("--yes", action="store_true")
    item = recovery_commands.add_parser("restore", help="restore a snapshot to a directory")
    item.add_argument("snapshot", type=Path)
    item.add_argument("--destination", type=Path)
    item.add_argument("--yes", action="store_true")

    logs = commands.add_parser("logs", aliases=["log"], help="view Eclipse and macOS logs")
    logs_commands = logs.add_subparsers(dest="logs_command", required=True)
    item = logs_commands.add_parser("list", help="list logs")
    item.add_argument("--source", action="append", choices=LOG_SOURCES, help="repeatable source: audit, scripts, automation, security, system")
    item.add_argument("--limit", type=int, default=50)
    item.add_argument("--user", help="filter by user")
    item.add_argument("--query", help="search logs")
    item.add_argument("--since", help="minimum ISO date")
    item.add_argument("--until", help="maximum ISO date")
    item.add_argument("--system", action="store_true", help="include macOS system logs")
    item.add_argument("--export", type=Path, help="export as JSON")

    vps = commands.add_parser("vps", help="manage Mac to VPS workflows")
    vps_commands = vps.add_subparsers(dest="vps_command", required=True)
    item = vps_commands.add_parser("upload", help="send a local file or folder to a VPS")
    item.add_argument("source", type=Path)
    item.add_argument("--host", help="VPS host or IP")
    item.add_argument("--user", help="SSH user")
    item.add_argument("--remote-path", help="remote destination folder")
    item.add_argument("--port", type=int, help="SSH port")
    item.add_argument("--identity", type=Path, help="SSH private key")
    item.add_argument("--dry-run", action="store_true", help="show transfer plan without uploading")
    item.add_argument("--json", action="store_true", help="print JSON output")
    return root


def print_memory(entries: list[MemoryEntry], *, limit: int) -> None:
    if limit < 1:
        raise EclipseError("Limit must be positive.")
    rows = entries[-limit:]
    if not rows:
        print("No memory entries.")
        return
    for entry in reversed(rows):
        tags = f" #{' #'.join(entry.tags)}" if entry.tags else ""
        project = f" [{entry.project}]" if entry.project else ""
        print(f"{entry.id}  {entry.created_at}{project}{tags}")
        print(f"  {entry.text}")


def print_mac_status() -> None:
    status = local_status()
    gpu_usage = f"{status.gpu.usage_percent:.1f}%" if status.gpu.usage_percent is not None else "N/A"
    print(f"Mac : {status.hostname}")
    print(f"macOS : {status.release or status.system}")
    print(f"Architecture : {status.machine}")
    print(f"CPU : {status.processor or 'N/A'}")
    print(f"RAM : {status.memory_percent:.1f}%")
    print(f"Disk / : {status.disk.percent:.1f}%")
    print(f"GPU : {gpu_usage}")
    print(f"GPU name : {', '.join(status.gpu.names) or 'N/A'}")
    print(f"Admin users : {', '.join(status.admin_users) or 'N/A'}")
    print(f"Network interface : {status.network.interface}")
    print(f"IP address : {status.network.ip_address}")
    print(f"Router : {status.network.router}")
    print(f"Wi-Fi : {status.network.wifi}")
    print(f"DNS : {', '.join(status.network.dns) or 'N/A'}")
    print(f"Firewall : {status.network.firewall}")
    print(f"Stealth mode : {status.network.stealth}")
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
            print("\n".join(local_files(folder, limit=args.limit)) or "No files.")
        return
    if args.command in {"files", "file"}:
        if args.files_command == "ls":
            entries = list_entries(args.path, limit=args.limit, include_hidden=args.hidden)
            print(args.path.expanduser().resolve())
            print("\n".join(format_entry(entry) for entry in entries) or "No files.")
        elif args.files_command == "favorites":
            for name, path in favorites().items():
                print(f"{name}: {path}")
        elif args.files_command == "info":
            print("\n".join(file_info(args.path)))
        elif args.files_command == "cat":
            print(read_text(args.path, max_bytes=args.max_bytes), end="")
        elif args.files_command == "write":
            print(
                f"File written: "
                f"{write_text(args.path, ' '.join(args.text), append=args.append, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}"
            )
        elif args.files_command == "edit-line":
            print(f"File edited: {edit_line(args.path, args.line, ' '.join(args.text), confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "mkdir":
            print(f"Directory created: {make_directory(args.path, confirmed=args.yes)}")
        elif args.files_command == "copy":
            print(f"Copy: {copy_path(args.source, args.destination, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "move":
            print(f"Move: {move_path(args.source, args.destination, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "rename":
            print(f"Rename: {rename_path(args.source, args.name, overwrite=args.overwrite, confirmed=args.yes, create_backup=not args.no_backup)}")
        elif args.files_command == "trash":
            if not args.yes:
                raise EclipseError("Add --yes to confirm moving to Trash.")
            print(f"Trash: {trash_path(args.path, confirmed=True, create_backup=not args.no_backup)}")
        elif args.files_command == "open":
            print(f"Opened: {open_path(args.path)}")
        elif args.files_command == "preview":
            preview = preview_path(args.path, max_bytes=args.max_bytes)
            print("\n".join(preview.details))
            if preview.content is not None:
                print()
                print(preview.content)
        elif args.files_command == "search":
            entries = search_entries(
                args.root,
                args.query,
                name=args.name,
                content=args.content,
                extension=args.extension,
                min_size=args.min_size,
                max_size=args.max_size,
                modified_after=args.modified_after,
                modified_before=args.modified_before,
                ignore=args.ignore,
                max_depth=args.depth,
                limit=args.limit,
                include_hidden=args.hidden,
            )
            print("\n".join(f"{entry.path}  ({entry.kind})" for entry in entries) or "No results.")
            if args.export:
                print(f"Export : {export_entries(entries, args.export)}")
        elif args.files_command == "chmod+x":
            print(f"Executable: {make_executable(args.path, confirmed=args.yes)}")
        elif args.files_command == "script-add":
            script = add_script(args.name or args.path.stem, args.path, tags=args.tag or ["explorer"], overwrite=args.overwrite)
            print(f"Script added: {script.name} -> {script.path}")
        return
    if args.command == "security":
        if args.security_command == "scan":
            findings = run_checks(args.check or DEFAULT_CHECKS, deep=args.deep)
            print(format_findings(findings))
            if args.json:
                print(f"\nReport: {write_report(findings, args.output_dir)}")
        elif args.security_command == "checks":
            for check in list_checks():
                suffix = f" - {check.description}" if args.verbose and check.description else ""
                print(f"{check.name}: {check.label}{suffix}")
        elif args.security_command == "history":
            print(format_report_history(load_reports(args.report_dir, limit=args.limit)))
        elif args.security_command == "diff":
            previous, current = latest_report_pair(args.report_dir)
            print(format_report_diff(previous, current))
        elif args.security_command == "baseline":
            if args.baseline_command == "save":
                findings = run_checks(args.check or DEFAULT_CHECKS, deep=args.deep)
                print(f"Baseline: {save_baseline(findings, args.path)}")
            elif args.baseline_command == "compare":
                findings = run_checks(args.check or DEFAULT_CHECKS, deep=args.deep)
                diff = compare_baseline(findings, args.path)
                print("Baseline comparison:")
                print(format_diff_categories(diff))
        elif args.security_command == "policy":
            if args.policy_command == "init":
                print(f"Policy: {write_default_policy(args.path, overwrite=args.overwrite)}")
            elif args.policy_command == "show":
                print(format_policy(load_policy(args.path)))
            elif args.policy_command == "check":
                findings = run_checks(args.check or DEFAULT_CHECKS, deep=args.deep)
                print(format_policy_evaluation(evaluate_policy(findings, load_policy(args.path), checks=args.check or DEFAULT_CHECKS)))
        elif args.security_command == "report":
            if args.report_command == "export":
                print(f"Report export: {export_report(load_latest_report(args.report_dir), args.output, format=args.format)}")
        elif args.security_command == "remediate":
            if args.remediate_command == "plan":
                findings = run_checks(args.check or DEFAULT_CHECKS, deep=args.deep)
                print(format_remediation_plan(remediation_plan(findings)))
        elif args.security_command == "secrets":
            if args.secrets_command == "scan":
                result = run_script("find-secrets-local", arguments=["--path", str(args.path), "--limit", str(args.limit)], force=True)
                if result.returncode:
                    raise EclipseError(f"Secret scan failed with code {result.returncode}.")
        elif args.security_command == "downloads":
            if args.downloads_command == "quarantine":
                result = run_script("quarantine-downloads-audit", arguments=["--folder", str(args.folder)], force=True)
                if result.returncode:
                    raise EclipseError(f"Downloads quarantine audit failed with code {result.returncode}.")
        elif args.security_command == "dmg":
            if args.dmg_command == "inspect":
                arguments = ["--file", str(args.path)]
                if args.open:
                    arguments.append("--open")
                result = run_script("safe-open-dmg", arguments=arguments, force=True)
                if result.returncode:
                    raise EclipseError(f"DMG inspection failed with code {result.returncode}.")
        elif args.security_command == "password":
            if args.password_command == "status":
                print(format_password_status(password_status()))
            elif args.password_command == "confirm":
                print(format_password_status(confirm_password_rotation()))
        return
    if args.command == "admin":
        if args.admin_command == "status":
            print_mac_status()
            findings = run_checks(("security", "firewall", "sharing", "updates"))
            print()
            print(format_findings(findings))
        elif args.admin_command == "report":
            findings = run_checks(DEFAULT_CHECKS, deep=args.deep)
            print(f"Report: {write_report(findings, args.output_dir)}")
        return
    if args.command in {"memory", "mem"}:
        if args.memory_command == "add":
            entry = add_memory(
                " ".join(args.text),
                tags=args.tag,
                source=args.source,
                project=args.project,
            )
            print(f"Memory added: {entry.id}")
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
            print(f"Memories: {data['count']}")
            print("Tags :", data["tags"] or "{}")
            print("Projects :", data["projects"] or "{}")
        return
    if args.command in {"scripts", "script"}:
        if args.scripts_command == "add":
            script = add_script(
                args.name,
                args.source,
                description=args.description,
                tags=args.tag,
                overwrite=args.overwrite,
                dry_run_required=args.dry_run_required,
            )
            print(f"Script added: {script.name} -> {script.path}")
        elif args.scripts_command == "list":
            scripts = load_scripts()
            if not scripts:
                print("No scripts.")
            for script in scripts.values():
                tags = f" #{' #'.join(script.tags)}" if script.tags else ""
                description = f" · {script.description}" if script.description else ""
                source = " · drop-in" if script.source == "drop-in" else ""
                dry = " · dry-run-required" if script.dry_run_required else ""
                last = f" · last={script.last_returncode}" if script.last_returncode is not None else ""
                print(f"{script.name}{tags}{source}{dry}{last}{description}")
                print(f"  {script.path}")
        elif args.scripts_command == "info":
            script = get_script(args.name)
            print(f"Name: {script.name}")
            print(f"Path: {script.path}")
            print(f"Source: {script.source}")
            print(f"Description: {script.description or ''}")
            print(f"Tags: {', '.join(script.tags)}")
            print(f"Parameters: {', '.join(script.parameters)}")
            print(f"Dry-run required: {script.dry_run_required}")
            print(f"Last run: {script.last_run_at or ''}")
            print(f"Last return code: {script.last_returncode if script.last_returncode is not None else ''}")
        elif args.scripts_command == "history":
            for item in load_script_history(limit=args.limit):
                print(f"{item.get('timestamp')} {item.get('script')} dry_run={item.get('dry_run')} code={item.get('returncode')}")
        elif args.scripts_command == "path":
            print(get_script(args.name).path)
        elif args.scripts_command == "remove":
            script = remove_script(args.name, delete_file=args.delete_file)
            print(f"Script removed: {script.name}")
        elif args.scripts_command == "run":
            dry_run, arguments = script_run_options(args.arguments, dry_run=args.dry_run)
            result = run_script(args.name, arguments=arguments, dry_run=dry_run, force=args.force)
            if result.returncode:
                raise EclipseError(f"Script failed: {args.name} (code {result.returncode}).")
        return
    if args.command in {"automation", "auto"}:
        if args.automation_command == "add":
            job = add_job(args.name, every=args.every, command=args.automation_exec, overwrite=args.overwrite)
            print(f"Automation added: {job.name} every={job.every} command={' '.join(job.command)}")
        elif args.automation_command == "list":
            jobs = load_jobs()
            if not jobs:
                print("No automation.")
                print()
                print(format_suggestions())
            for job in jobs.values():
                state = "enabled" if job.enabled else "disabled"
                last = job.last_returncode if job.last_returncode is not None else ""
                print(f"{job.name} [{state}] every={job.every} last={last}")
                print(f"  eclipse {' '.join(job.command)}")
        elif args.automation_command == "suggestions":
            print(format_suggestions())
        elif args.automation_command == "quickstart":
            print(format_quickstart())
        elif args.automation_command == "run":
            result = run_job(args.name, dry_run=args.dry_run)
            if args.dry_run and result.stdout:
                print(result.stdout)
            if result.returncode:
                raise EclipseError(f"Automation failed: {args.name} (code {result.returncode}).")
        elif args.automation_command == "run-due":
            rows = run_due(dry_run=args.dry_run)
            if not rows:
                print("No automation due.")
            for job, result in rows:
                print(f"{job.name}: code={result.returncode}")
                if args.dry_run and result.stdout:
                    print(f"  {result.stdout}")
        elif args.automation_command == "enable":
            print(f"Automation enabled: {set_enabled(args.name, True).name}")
        elif args.automation_command == "disable":
            print(f"Automation disabled: {set_enabled(args.name, False).name}")
        elif args.automation_command == "history":
            for item in load_automation_history(limit=args.limit):
                print(f"{item.get('timestamp')} {item.get('job')} dry_run={item.get('dry_run')} code={item.get('returncode')}")
        return
    if args.command in {"plugins", "plugin"}:
        if args.plugins_command == "list":
            plugins = list_plugins()
            if not plugins:
                print("No plugins.")
            for plugin in plugins:
                state = "enabled" if plugin.enabled else "disabled"
                print(f"{plugin.name} [{state}] {plugin.description}")
                print(f"  {plugin.path}")
        elif args.plugins_command == "create":
            plugin = create_plugin(args.name, description=args.description)
            print(f"Plugin created: {plugin.name} -> {plugin.path}")
        return
    if args.command == "recovery":
        if args.recovery_command == "snapshot":
            print(f"Snapshot : {snapshot(args.destination)}")
        elif args.recovery_command == "view":
            if args.snapshot:
                print(format_snapshot_info(snapshot_info(resolve_snapshot(args.snapshot, root=args.root)), limit=args.limit))
            else:
                print(format_snapshot_list(list_snapshots(args.root)))
        elif args.recovery_command == "export":
            print(f"Export : {archive_snapshot(args.snapshot, args.destination, password=args.password)}")
        elif args.recovery_command == "load":
            print(f"Load : {restore_snapshot(resolve_snapshot(args.snapshot, root=args.root), args.destination, confirmed=args.yes)}")
        elif args.recovery_command == "restore":
            print(f"Restore : {restore_snapshot(args.snapshot, args.destination, confirmed=args.yes)}")
        return
    if args.command in {"logs", "log"}:
        if args.logs_command == "list":
            entries = collect_logs(
                args.source,
                limit=args.limit,
                user=args.user,
                query=args.query,
                since=args.since,
                until=args.until,
                include_system=args.system,
            )
            print("\n".join(format_log(entry) for entry in entries) or "No logs.")
            if args.export:
                print(f"Export : {export_logs(entries, args.export)}")
        return
    if args.command == "vps":
        if args.vps_command == "upload":
            result = upload_path(
                args.source,
                host=args.host,
                user=args.user,
                remote_path=args.remote_path,
                port=args.port,
                identity=args.identity,
                dry_run=args.dry_run,
            )
            print(upload_result_json(result) if args.json else format_upload_result(result))
            if result.returncode:
                raise EclipseError(f"VPS upload failed with code {result.returncode}.")
        return


def main() -> int:
    try:
        dispatch(parser().parse_args())
        print("✓ Done")
        return 0
    except (EclipseError, KeyboardInterrupt) as error:
        message = "Operation interrupted." if isinstance(error, KeyboardInterrupt) else str(error)
        print(f"✗ {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
