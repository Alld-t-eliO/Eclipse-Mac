from __future__ import annotations
import shlex
from pathlib import Path
from eclipse.core import style as ui
from eclipse.modules.automation import add_job, load_history as load_automation_history, load_jobs, run_due, run_job, set_enabled
from eclipse.system.errors import EclipseError
from eclipse.system.inbox import (
    copy_path,
    edit_line,
    favorites,
    file_info,
    format_entry,
    is_protected_path,
    list_entries,
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
from eclipse.system.status import LocalStatus, local_status
from eclipse.core.logs import LOG_SOURCES, collect_logs, export_logs, format_log
from eclipse.system.memory import add_memory, filter_memories, load_memories, summarize
from eclipse.modules.plugins import list_plugins
from eclipse.system.recovery import archive_snapshot, snapshot
from eclipse.modules.security import (
    DEFAULT_CHECKS,
    confirm_password_rotation,
    format_findings,
    format_report_diff,
    format_report_history,
    latest_report_pair,
    list_checks,
    load_reports,
    password_status,
    run_checks,
    write_report,
)
from eclipse.modules.scripts import add_script, load_scripts, run_script
from eclipse.vps.vps import format_upload_result, upload_path

LOGO = r"""
    ______     __  _
   / ____/____/ /_(_)___  ________
  / __/ / ___/ / / / __ \/ ___/ _ \
 / /___/ /__/ / / / /_/ (__  )  __/
/_____/\___/_/_/_/ .___/____/\___/
                /_/

   ==== By Aegon ====
"""


def human_size(value: object) -> str:
    size = float(value or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def is_yes(value: str) -> bool:
    return value.strip().lower() in {"y", "yes", "oui"}


def header(title: str = "CONTROL CENTER") -> None:
    status = local_status()
    passwords = password_status()
    password_light = ui.success("● PWD OK") if passwords.changed and not passwords.expired else ui.danger("● PWD CHANGE DUE")
    ui.clear()
    for index, line in enumerate(LOGO.strip("\n").splitlines()):
        rendered = ui.paint(line, ui.CYAN if index < 3 else ui.MAGENTA, bold=True)
        if index == 0:
            padding = " " * max(2, 78 - ui.visible_length(rendered) - ui.visible_length(password_light))
            rendered = f"{rendered}{padding}{password_light}"
        print(rendered)
    print(f"\n  {ui.neon(title, bold=True)}")
    print(f"  {ui.muted('MAC')} {ui.accent(status.hostname)} {ui.muted('· SHELL')} {ui.success(status.shell or 'local')}")
    print(f"  {ui.muted('─' * 54)}\n")


def pause() -> None:
    input(f"\n  {ui.muted('Press Enter to return to the menu...')}")


def local_panel(status: LocalStatus) -> list[str]:
    gpu_usage = f"{status.gpu.usage_percent:.1f}%" if status.gpu.usage_percent is not None else "N/A"
    return [
        ui.neon("╭─ MAC // LOCAL CORE ────────────╮", bold=True),
        f"{ui.neon('│')} {ui.muted('RAM')}  {ui.gauge(status.memory_percent, 13)} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('SSD')}  {ui.gauge(status.disk.percent, 13)} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('GPU')}  {ui.accent(gpu_usage):>24} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('OS')}   {ui.accent(status.release or status.system):>24} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('ARCH')} {ui.paint(status.machine, ui.WHITE):>24} {ui.neon('│')}",
        ui.neon("╰────────────────────────────────╯", bold=True),
    ]


def network_panel(status: LocalStatus) -> list[str]:
    firewall = ui.success(status.network.firewall) if status.network.firewall == "enabled" else ui.danger(status.network.firewall)
    stealth = ui.success(status.network.stealth) if status.network.stealth == "enabled" else ui.muted(status.network.stealth)
    dns = ", ".join(status.network.dns[:2]) if status.network.dns else "N/A"
    interface = status.network.interface[:23]
    ip_address = status.network.ip_address[:23]
    router = status.network.router[:22]
    wifi = status.network.wifi[:23]
    dns = dns[:23]
    return [
        ui.neon("╭─ NETWORK // FIREWALL ──────────╮", bold=True),
        f"{ui.neon('│')} {ui.muted('IFACE')} {ui.accent(interface):>23} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('IP')}    {ui.paint(ip_address, ui.WHITE):>23} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('ROUTER')} {ui.paint(router, ui.WHITE):>22} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('WIFI')}  {ui.paint(wifi, ui.WHITE):>23} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('DNS')}   {ui.paint(dns, ui.WHITE):>23} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('FW')}    {firewall:>23} {ui.neon('│')}",
        f"{ui.neon('│')} {ui.muted('STEALTH')} {stealth:>20} {ui.neon('│')}",
        ui.neon("╰────────────────────────────────╯", bold=True),
    ]


def local_status_menu() -> None:
    status = local_status()
    header("MAC // LOCAL STATUS")
    gpu_usage = f"{status.gpu.usage_percent:.1f}%" if status.gpu.usage_percent is not None else "N/A"
    left = [
        f"{ui.muted('Host'):<18} {ui.accent(status.hostname)}",
        f"{ui.muted('macOS'):<18} {status.release or status.system}",
        f"{ui.muted('Architecture'):<18} {status.machine}",
        f"{ui.muted('CPU'):<18} {status.processor or 'N/A'}",
        f"{ui.muted('GPU'):<18} {', '.join(status.gpu.names) or 'N/A'}",
        f"{ui.muted('GPU usage'):<18} {gpu_usage} ({status.gpu.detail})",
        f"{ui.muted('Admin users'):<18} {', '.join(status.admin_users) or 'N/A'}",
        f"{ui.muted('Home folder'):<18} {status.home}",
        f"{ui.muted('Shell'):<18} {status.shell or 'N/A'}",
        "",
        f"{ui.muted('Memory')} {ui.gauge(status.memory_percent, 24)} {human_size(status.memory_used)} / {human_size(status.memory_total)}",
        f"{ui.muted('Disk /')} {ui.gauge(status.disk.percent, 24)} {human_size(status.disk.used)} / {human_size(status.disk.total)}",
    ]
    ui.columns([f"  {line}" for line in left], network_panel(status), left_width=76)


def local_files_menu() -> None:
    current = Path.home()
    while True:
        current = current.expanduser().resolve()
        header("FILES // EXPLORER")
        print(f"  {ui.neon(str(current), bold=True)}\n")
        entries = list_entries(current, limit=30)
        if entries:
            for index, entry in enumerate(entries, 1):
                marker = "/" if entry.kind == "directory" else ""
                print(ui.menu_line(f"[{index}]", f"{format_entry(entry)}{marker}"))
        else:
            print(f"  {ui.muted('No visible files.')}")
        print()
        print(ui.menu_line("[cd]", "go to path"))
        print(ui.menu_line("[fav]", "quick locations"))
        print(ui.menu_line("[..]", "parent folder"))
        print(ui.menu_line("[view]", "preview"))
        print(ui.menu_line("[info]", "info and permissions"))
        print(ui.menu_line("[search]", "search"))
        print(ui.menu_line("[new]", "create text file"))
        print(ui.menu_line("[edit]", "replace a line"))
        print(ui.menu_line("[mkdir]", "create folder"))
        print(ui.menu_line("[ren]", "rename"))
        print(ui.menu_line("[cp]", "copy"))
        print(ui.menu_line("[mv]", "move"))
        print(ui.menu_line("[trash]", "move to Trash"))
        print(ui.menu_line("[open]", "open with macOS"))
        print(ui.menu_line("[chmod]", "make executable"))
        print(ui.menu_line("[script]", "add to Eclipse scripts"))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt("Action or number")).strip()
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
                    preview = preview_path(selected.path, max_bytes=12000)
                    print("\n".join(f"  {line}" for line in preview.details))
                    if preview.content is not None:
                        print()
                        print(preview.content)
                    pause()
            elif choice == "cd":
                current = Path(input(ui.prompt("Path")).strip() or str(current))
            elif choice == "fav":
                shortcuts = list(favorites().items())
                print()
                for index, (name, path) in enumerate(shortcuts, 1):
                    print(ui.menu_line(f"[{index}]", f"{name}: {path}"))
                selected = input(ui.prompt("Favorite")).strip()
                if selected.isdigit() and 1 <= int(selected) <= len(shortcuts):
                    current = shortcuts[int(selected) - 1][1]
            elif choice == "view":
                path = Path(input(ui.prompt("Path")).strip() or str(current))
                target = path if path.is_absolute() else current / path
                preview = preview_path(target, max_bytes=12000)
                print()
                print("\n".join(f"  {line}" for line in preview.details))
                if preview.content is not None:
                    print()
                    print(preview.content)
                pause()
            elif choice == "info":
                path = Path(input(ui.prompt("Path")).strip() or str(current))
                target = path if path.is_absolute() else current / path
                print()
                print("\n".join(f"  {line}" for line in file_info(target)))
                pause()
            elif choice == "search":
                query = input(ui.prompt("Search")).strip()
                pattern = input(ui.prompt("Optional pattern (*.py)")).strip()
                results = search_entries(current, query or None, name=pattern or None, max_depth=5, limit=40)
                print()
                if not results:
                    print(f"  {ui.muted('No results.')}")
                for entry in results:
                    print(f"  {entry.path} ({entry.kind})")
                pause()
            elif choice == "new":
                path = Path(input(ui.prompt("File")).strip())
                target = path if path.is_absolute() else current / path
                text = input(ui.prompt("Text")).strip()
                overwrite = is_yes(input(ui.prompt("Overwrite if exists [yes/N]")))
                confirmed = not is_protected_path(target) or is_yes(input(ui.prompt("Protected path, confirm [yes/N]")))
                print(f"  {ui.success('●')} File written: {write_text(target, text, overwrite=overwrite, confirmed=confirmed)}")
                pause()
            elif choice == "edit":
                path = Path(input(ui.prompt("File")).strip())
                target = path if path.is_absolute() else current / path
                line = int(input(ui.prompt("Line")).strip())
                text = input(ui.prompt("New text")).strip()
                confirmed = not is_protected_path(target) or is_yes(input(ui.prompt("Protected path, confirm [yes/N]")))
                print(f"  {ui.success('●')} File edited: {edit_line(target, line, text, confirmed=confirmed)}")
                pause()
            elif choice == "mkdir":
                path = Path(input(ui.prompt("Folder")).strip())
                target = path if path.is_absolute() else current / path
                confirmed = not is_protected_path(target) or is_yes(input(ui.prompt("Protected path, confirm [yes/N]")))
                print(f"  {ui.success('●')} Folder created: {make_directory(target, confirmed=confirmed)}")
                pause()
            elif choice == "ren":
                path = Path(input(ui.prompt("Path")).strip())
                target = path if path.is_absolute() else current / path
                name = input(ui.prompt("New name")).strip()
                confirmed = not is_protected_path(target) or is_yes(input(ui.prompt("Protected path, confirm [yes/N]")))
                print(f"  {ui.success('●')} Rename: {rename_path(target, name, confirmed=confirmed)}")
                pause()
            elif choice in {"cp", "mv"}:
                source_raw = Path(input(ui.prompt("Source")).strip())
                destination_raw = Path(input(ui.prompt("Destination")).strip())
                source = source_raw if source_raw.is_absolute() else current / source_raw
                destination = destination_raw if destination_raw.is_absolute() else current / destination_raw
                overwrite = is_yes(input(ui.prompt("Overwrite if exists [yes/N]")))
                protected = is_protected_path(source) if choice == "mv" else False
                protected = protected or is_protected_path(destination)
                confirmed = not protected or is_yes(input(ui.prompt("Protected path, confirm [yes/N]")))
                action = copy_path if choice == "cp" else move_path
                print(f"  {ui.success('●')} Result: {action(source, destination, overwrite=overwrite, confirmed=confirmed)}")
                pause()
            elif choice == "trash":
                path = Path(input(ui.prompt("Path")).strip())
                target = path if path.is_absolute() else current / path
                answer = input(ui.prompt(f"Move {target} to Trash [yes/N]"))
                if is_yes(answer):
                    print(f"  {ui.success('●')} Trash: {trash_path(target, confirmed=True)}")
                pause()
            elif choice == "open":
                path = Path(input(ui.prompt("Path")).strip() or str(current))
                target = path if path.is_absolute() else current / path
                print(f"  {ui.success('●')} Opened: {open_path(target)}")
                pause()
            elif choice == "chmod":
                path = Path(input(ui.prompt("File")).strip())
                target = path if path.is_absolute() else current / path
                confirmed = not is_protected_path(target) or is_yes(input(ui.prompt("Protected path, confirm [yes/N]")))
                print(f"  {ui.success('●')} Executable: {make_executable(target, confirmed=confirmed)}")
                pause()
            elif choice == "script":
                path = Path(input(ui.prompt("File")).strip())
                target = path if path.is_absolute() else current / path
                name = input(ui.prompt("Eclipse script name")).strip() or target.stem
                script = add_script(name, target, tags=["explorer"], overwrite=False)
                print(f"  {ui.success('●')} Script added: {script.name}")
                pause()
            else:
                print(ui.danger("Invalid choice."))
                pause()
        except EclipseError as error:
            print(ui.danger(f"\n  ✗ {error}"))
            pause()


def memory_menu() -> None:
    while True:
        header("MEMORY // LOCAL MAC")
        data = summarize(load_memories())
        print(f"  {ui.muted('Entries')} {ui.accent(data['count'])}")
        print(f"  {ui.muted('Tags')}    {data['tags'] or '{}'}")
        print(f"  {ui.muted('Projects')} {data['projects'] or '{}'}\n")
        print(ui.menu_line("[1]", "List latest memories"))
        print(ui.menu_line("[2]", "Search memory"))
        print(ui.menu_line("[3]", "Add memory"))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "1":
            entries = load_memories()[-20:]
        elif choice == "2":
            query = input(ui.prompt("Search")).strip()
            entries = filter_memories(load_memories(), query=query)
        elif choice == "3":
            text = input(ui.prompt("Text")).strip()
            tags = input(ui.prompt("Tags")).strip()
            project = input(ui.prompt("Project")).strip()
            entry = add_memory(text, tags=[tags] if tags else [], project=project or None, source="eclipse-ui")
            print(f"  {ui.success('●')} Memory added: {entry.id}")
            pause()
            continue
        else:
            print(ui.danger("Invalid choice."))
            pause()
            continue
        print()
        if not entries:
            print(f"  {ui.muted('No memory entries.')}")
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
            print(f"  {ui.muted('No local script registered.')}")
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt("Script to run")).strip()
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(scripts):
            script = scripts[int(choice) - 1]
            raw_arguments = input(ui.prompt("Optional arguments")).strip()
            try:
                arguments = shlex.split(raw_arguments) if raw_arguments else []
            except ValueError as error:
                raise EclipseError(f"Invalid arguments: {error}") from error
            answer = input(ui.prompt(f"Confirm local execution of {script.name} [yes/N]"))
            if is_yes(answer):
                result = run_script(script.name, arguments=arguments)
                if result.returncode:
                    raise EclipseError(f"Script failed: {script.name} (code {result.returncode}).")
        else:
            print(ui.danger("Invalid choice."))
        pause()


def security_menu() -> None:
    checks = tuple((check.name, check.label) for check in list_checks())
    while True:
        header("SECURITY")
        status = password_status()
        light = ui.success("GREEN") if status.changed and not status.expired else ui.danger("RED")
        print(f"  {ui.muted('Passwords')} {light}")
        if status.next_due_at:
            print(f"  {ui.muted('Next due date')} {status.next_due_at}")
        print()
        print(ui.menu_line("[1]", "Run security scan"))
        print(ui.menu_line("[2]", "Full JSON report"))
        print(ui.menu_line("[3]", "Confirm password change"))
        print(ui.menu_line("[hist]", "Report history"))
        print(ui.menu_line("[diff]", "Latest report diff"))
        print(ui.menu_line("[secrets]", "Secret pattern scan"))
        print(ui.menu_line("[quarantine]", "Downloads quarantine audit"))
        print(ui.menu_line("[dmg]", "Inspect DMG"))
        for index, (_, label) in enumerate(checks, 4):
            print(ui.menu_line(f"[{index}]", label))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "1":
            findings = run_checks(("security", "firewall", "sharing", "updates"))
            print()
            print(format_findings(findings))
        elif choice == "2":
            findings = run_checks(DEFAULT_CHECKS)
            print(f"\n  {ui.success('●')} Report: {write_report(findings)}")
        elif choice == "3":
            answer = input(ui.prompt("Have you changed your passwords? [yes/N]"))
            if is_yes(answer):
                updated = confirm_password_rotation()
                print(f"\n  {ui.success('●')} Confirmed until {updated.next_due_at}")
        elif choice == "hist":
            print()
            print(format_report_history(load_reports(limit=10)))
        elif choice == "diff":
            print()
            previous, current = latest_report_pair()
            print(format_report_diff(previous, current))
        elif choice == "secrets":
            path = Path(input(ui.prompt("Folder")).strip() or str(Path.cwd()))
            limit = input(ui.prompt("Limit")).strip() or "100"
            result = run_script("find-secrets-local", arguments=["--path", str(path), "--limit", limit], force=True)
            if result.returncode:
                raise EclipseError(f"Secret scan failed with code {result.returncode}.")
        elif choice == "quarantine":
            folder = Path(input(ui.prompt("Downloads folder")).strip() or str(Path.home() / "Downloads"))
            result = run_script("quarantine-downloads-audit", arguments=["--folder", str(folder)], force=True)
            if result.returncode:
                raise EclipseError(f"Downloads quarantine audit failed with code {result.returncode}.")
        elif choice == "dmg":
            path = Path(input(ui.prompt("DMG path")).strip())
            open_after = is_yes(input(ui.prompt("Open after inspection [yes/N]")))
            arguments = ["--file", str(path)]
            if open_after:
                arguments.append("--open")
            result = run_script("safe-open-dmg", arguments=arguments, force=True)
            if result.returncode:
                raise EclipseError(f"DMG inspection failed with code {result.returncode}.")
        elif choice.isdigit() and 4 <= int(choice) < 4 + len(checks):
            check = checks[int(choice) - 4][0]
            findings = run_checks((check,))
            print()
            print(format_findings(findings))
        else:
            print(ui.danger("Invalid choice."))
        pause()


def automation_menu() -> None:
    while True:
        header("AUTOMATIONS // SCHEDULED")
        jobs = load_jobs()
        if jobs:
            for index, job in enumerate(jobs.values(), 1):
                state = "on" if job.enabled else "off"
                print(ui.menu_line(f"[{index}]", f"{job.name} · {state} · every {job.every}"))
        else:
            print(f"  {ui.muted('No automation.')}")
        print()
        print(ui.menu_line("[add]", "add"))
        print(ui.menu_line("[run]", "run"))
        print(ui.menu_line("[due]", "run due automations"))
        print(ui.menu_line("[off]", "disable"))
        print(ui.menu_line("[on]", "enable"))
        print(ui.menu_line("[hist]", "history"))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "add":
            name = input(ui.prompt("Name")).strip()
            every = input(ui.prompt("Interval hour/day/week")).strip()
            command = input(ui.prompt("Optional Eclipse command")).strip()
            job = add_job(name, every=every, command=shlex.split(command) if command else None)
            print(f"  {ui.success('●')} Automation added: {job.name}")
        elif choice == "run":
            name = input(ui.prompt("Name")).strip()
            dry = is_yes(input(ui.prompt("Dry-run [yes/N]")))
            result = run_job(name, dry_run=dry)
            print(f"  {ui.success('●')} Code: {result.returncode}")
            if result.stdout:
                print(f"  {result.stdout}")
        elif choice == "due":
            rows = run_due(dry_run=is_yes(input(ui.prompt("Dry-run [yes/N]"))))
            print(f"  {ui.success('●')} Automations run: {len(rows)}")
        elif choice in {"off", "on"}:
            name = input(ui.prompt("Name")).strip()
            set_enabled(name, choice == "on")
        elif choice == "hist":
            for item in load_automation_history(limit=20):
                print(f"  {item.get('timestamp')} {item.get('job')} code={item.get('returncode')}")
        else:
            print(ui.danger("Invalid choice."))
        pause()


def plugins_menu() -> None:
    header("PLUGINS // MODULES")
    plugins = list_plugins()
    if plugins:
        for plugin in plugins:
            state = "on" if plugin.enabled else "off"
            print(f"  {ui.accent(plugin.name)} [{state}] {plugin.description}")
            print(f"    {plugin.path}")
    else:
        print(f"  {ui.muted('No plugin.')}")


def recovery_menu() -> None:
    while True:
        header("RECOVERY // BACKUP")
        print(ui.menu_line("[1]", "Create snapshot"))
        print(ui.menu_line("[2]", "Export snapshot"))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "1":
            print(f"  {ui.success('●')} Snapshot : {snapshot()}")
        elif choice == "2":
            path = Path(input(ui.prompt("Snapshot")).strip())
            password = input(ui.prompt("Optional password")).strip()
            print(f"  {ui.success('●')} Export : {archive_snapshot(path, password=password or None)}")
        else:
            print(ui.danger("Invalid choice."))
        pause()


def logs_menu() -> None:
    choices = {
        "1": ("audit",),
        "2": ("security",),
        "3": ("scripts",),
        "4": ("automation",),
        "5": ("system",),
        "6": ("audit", "security", "scripts", "automation"),
    }
    while True:
        header("LOGS // JOURNALS")
        print(ui.menu_line("[1]", "Audit Eclipse"))
        print(ui.menu_line("[2]", "Security"))
        print(ui.menu_line("[3]", "Used scripts"))
        print(ui.menu_line("[4]", "Automations"))
        print(ui.menu_line("[5]", "macOS system"))
        print(ui.menu_line("[6]", "All Eclipse"))
        print(ui.menu_line("[export]", "export JSON"))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        try:
            if choice in choices:
                entries = collect_logs(choices[choice], limit=30, include_system=choice == "5")
                print()
                print("\n".join(f"  {format_log(entry)}" for entry in entries) if entries else f"  {ui.muted('No logs.')}")
            elif choice == "export":
                source = input(ui.prompt(f"Source {LOG_SOURCES}")).strip()
                destination = Path(input(ui.prompt("Destination JSON")).strip())
                entries = collect_logs((source,), limit=200, include_system=source == "system")
                print(f"  {ui.success('●')} Export : {export_logs(entries, destination)}")
            else:
                print(ui.danger("Invalid choice."))
        except EclipseError as error:
            print(ui.danger(f"\n  ✗ {error}"))
        pause()


def vps_menu() -> None:
    while True:
        header("VPS ")
        print(ui.menu_line("[1]", "Upload file or folder"))
        print(ui.menu_line("[0]", "Back"), "\n")
        choice = input(ui.prompt()).strip()
        if choice == "0":
            return
        if choice == "1":
            try:
                source = Path(input(ui.prompt("Local source")).strip())
                host = input(ui.prompt("VPS host")).strip()
                user = input(ui.prompt("SSH user optional")).strip() or None
                remote_path = input(ui.prompt("Remote folder")).strip()
                port_raw = input(ui.prompt("SSH port optional")).strip()
                identity_raw = input(ui.prompt("SSH key optional")).strip()
                dry_run = is_yes(input(ui.prompt("Dry-run [yes/N]")))
                result = upload_path(
                    source,
                    host=host,
                    user=user,
                    remote_path=remote_path,
                    port=int(port_raw) if port_raw else None,
                    identity=Path(identity_raw) if identity_raw else None,
                    dry_run=dry_run,
                )
                print()
                print("\n".join(f"  {line}" for line in format_upload_result(result).splitlines()))
            except (EclipseError, ValueError) as error:
                print(ui.danger(f"\n  ✗ {error}"))
        else:
            print(ui.danger("Invalid choice."))
        pause()


def launch() -> None:
    ui.boot_animation()
    while True:
        status = local_status()
        header()
        menu = [
            ui.menu_line("[1]", "Mac status"),
            ui.menu_line("[2]", "Local files"),
            ui.menu_line("[3]", "Local memory"),
            ui.menu_line("[4]", "Local scripts"),
            ui.menu_line("[5]", "Security"),
            ui.menu_line("[6]", "Automations"),
            ui.menu_line("[7]", "Plugins"),
            ui.menu_line("[8]", "Recovery"),
            ui.menu_line("[9]", "Logs"),
            ui.menu_line("[10]", "VPS"),
            ui.menu_line("[0]", "Quit", danger_action=True),
        ]
        ui.columns(menu, local_panel(status))
        print()
        choice = input(ui.prompt()).strip()
        if choice == "0":
            print(f"\n  {ui.neon('ECLIPSE//SHUTDOWN')} {ui.success('● CLEAN EXIT')}")
            return
        actions = {
            "1": local_status_menu,
            "2": local_files_menu,
            "3": memory_menu,
            "4": local_scripts_menu,
            "5": security_menu,
            "6": automation_menu,
            "7": plugins_menu,
            "8": recovery_menu,
            "9": logs_menu,
            "10": vps_menu,
        }
        action = actions.get(choice)
        if action is None:
            print(ui.danger("Invalid choice."))
            pause()
            continue
        try:
            action()
        except EclipseError as error:
            print(ui.danger(f"\n  ✗ {error}"))
        pause()
