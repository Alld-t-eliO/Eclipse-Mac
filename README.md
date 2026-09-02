# Eclipse 0.3

Eclipse is a local macOS control center. It helps inspect the current Mac,
browse common user folders, store local notes, run personal scripts, and review
basic administration and security signals from either an interactive terminal UI
or the command line.

## Features

- Local Mac dashboard: macOS version, CPU, memory, disk usage, shell, and home
  folder.
- Quick inspection of Desktop, Downloads, Documents, Pictures, Movies, and
  Music.
- Local JSONL memory for notes, decisions, tags, projects, and exports.
- Personal script registry with private copies and local execution.
- macOS administration and security checks for FileVault, Gatekeeper, SIP,
  firewall, sharing, network state, persistence, services, updates, filesystem
  permissions, processes, and Docker.
- Private JSONL audit log at `~/.local/state/eclipse/audit.jsonl`.

## Local Installation

```bash
cd ~/Eclipse
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Usage

```bash
eclipse ui
eclipse mac status
eclipse mac files downloads --limit 10
eclipse files ls ~/Downloads --limit 30
eclipse files cat ~/Notes/todo.txt
eclipse files write ~/Notes/todo.txt "New note" --append
eclipse files mkdir ~/Work/new-folder
eclipse files copy ~/Notes/todo.txt ~/Backups/todo.txt
eclipse files move ~/Backups/todo.txt ~/Backups/todo-old.txt
eclipse files trash ~/Backups/todo-old.txt --yes
eclipse admin status
eclipse security scan --check security --check firewall
eclipse security scan --json
eclipse admin report
eclipse memory add "Decision or observation" --tag mac,local --project eclipse
eclipse memory search observation --project eclipse
eclipse memory stats
eclipse memory export ~/Backups/eclipse-memory.json
eclipse scripts add cleanup ~/scripts/cleanup.sh --tag maintenance
eclipse scripts list
eclipse scripts run cleanup --dry-run -- --verbose
eclipse scripts run cleanup -- --verbose
```

`eclipse ui` opens the interactive terminal control center. The first screen
shows the Mac status, then gives access to local files, local memory, personal
scripts, and the `Administration & Security` menu.

## Local Files

Eclipse includes a local file explorer for macOS. It can browse folders, preview
UTF-8 text files, create files and folders, copy, move, rename, send files to
the macOS Trash, and open paths through Finder or the default macOS app.

Useful commands:

```bash
eclipse files ls ~/Documents --hidden
eclipse files cat ~/Documents/note.txt
eclipse files write ~/Documents/note.txt "Appended note" --append
eclipse files mkdir ~/Documents/Eclipse
eclipse files rename ~/Documents/old.txt new.txt
eclipse files copy ~/Documents/new.txt ~/Desktop/new.txt
eclipse files move ~/Desktop/new.txt ~/Documents/Eclipse/new.txt
eclipse files trash ~/Documents/Eclipse/new.txt --yes
eclipse files open ~/Documents
```

`trash` requires `--yes` in the CLI. In the interactive UI, Eclipse asks for
confirmation before moving a path to the Trash.

## Administration And Security

The security module is based on the original local Bash scanner, but it is
integrated directly into Eclipse and remains read-only. JSON reports are written
by default to:

```text
~/Library/Application Support/Eclipse/security-reports
```

Useful commands:

```bash
eclipse admin status
eclipse admin report
eclipse security scan
eclipse security scan --deep
eclipse security scan --check security --check firewall
eclipse security scan --json --output-dir ~/Backups/eclipse-security
```

`--deep` enables slower checks, including the macOS update lookup through
`softwareupdate -l`.

## Local Memory

By default, memory entries are stored in:

```text
~/Library/Application Support/Eclipse/memory.jsonl
```

The file is created with private permissions. Each entry contains an identifier,
a UTC timestamp, the text, optional tags, a source, and a project.

For tests, scripts, or migrations, set `ECLIPSE_MEMORY_PATH` to override the
default path:

```bash
ECLIPSE_MEMORY_PATH=/path/to/memory.jsonl eclipse memory stats
```

## Local Scripts

By default, Eclipse stores the script registry and private script copies in:

```text
~/Library/Application Support/Eclipse/scripts
```

Scripts ending in `.py`, `.sh`, `.bash`, `.zsh`, and `.js` are executed with the
matching local interpreter. Other files are executed directly.

You can also drop personal scripts directly into the project-level `scripts/`
folder, or into `eclipse/scripts/` if you want the drop-in folder next to the
Python package. Eclipse discovers files from those folders automatically, lists
them in the CLI and UI, and lets you execute them without running
`eclipse scripts add`. Files inside both drop-in folders are ignored by Git so
personal scripts are not published with the project.

Useful commands:

```bash
eclipse scripts add name ~/scripts/tool.py --description "local tool" --tag mac
eclipse scripts list
eclipse scripts run name -- --flag
eclipse scripts path name
eclipse scripts remove name --delete-file
```

For tests or a separate profile, set `ECLIPSE_SCRIPTS_HOME` to override the
default scripts directory:

```bash
ECLIPSE_SCRIPTS_HOME=/path/to/scripts eclipse scripts list
```

## Privacy

Eclipse is designed to keep local operational data outside the repository.
Generated memory files, script copies, security reports, caches, logs, virtual
environments, environment files, and project-level drop-in scripts are ignored
by Git.

Before publishing the project, review the pending Git changes and run a secret
scan or equivalent check for personal paths, tokens, keys, and credentials.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
