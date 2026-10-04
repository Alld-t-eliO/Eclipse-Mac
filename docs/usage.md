# Eclipse command guide

[Back to README](../README.md) · [Installation](installation.md)

Examples with paths, hosts, IDs, or personal script names must be adapted to your Mac.
Use `eclipse <category> --help` to inspect available commands.

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
eclipse files search ~/Documents invoice --name "*.pdf"
eclipse files preview ~/Documents/config.json
eclipse files script-add ~/scripts/cleanup.sh cleanup
eclipse automation add daily-security-scan --every day
eclipse automation add weekly-snapshot --every week --command recovery snapshot
eclipse automation suggestions
eclipse automation quickstart
eclipse automation run-due --dry-run
eclipse scripts info cleanup
eclipse scripts history
eclipse plugins list
eclipse recovery snapshot
eclipse recovery view
eclipse recovery view snapshot-YYYYMMDD-HHMMSS-SUFFIX
eclipse recovery load snapshot-YYYYMMDD-HHMMSS-SUFFIX --destination ~/Desktop/eclipse-restore --yes
eclipse logs list --source scripts --limit 20
eclipse logs list --source audit --source security --query file-write
eclipse logs list --system --limit 20
eclipse security password status
eclipse security password confirm
eclipse admin status
eclipse security scan --check security --check firewall
eclipse security scan --json
eclipse security checks --verbose
eclipse security history
eclipse security diff
eclipse security remediate plan
eclipse security baseline save
eclipse security baseline compare
eclipse security policy init
eclipse security policy show
eclipse security policy check
eclipse security report export --format markdown --output ~/Desktop/eclipse-security.md
eclipse security secrets scan ~/Projects --limit 50
eclipse security downloads quarantine --folder ~/Downloads
eclipse security dmg inspect ~/Downloads/app.dmg
eclipse admin report
eclipse memory add "Decision or observation" --tag mac,local --project eclipse
eclipse memory search observation --project eclipse
eclipse memory stats
eclipse memory export ~/Backups/eclipse-memory.json
eclipse scripts add cleanup ~/scripts/cleanup.sh --tag maintenance
eclipse scripts list
eclipse scripts run cleanup --dry-run -- --verbose
eclipse scripts run cleanup -- --verbose
eclipse vps upload ~/Documents/report.pdf --host 203.0.113.10 --user deploy --remote-path /srv/uploads --dry-run
eclipse vps upload ~/Projects/site --host example.com --remote-path /var/www/site
```

`eclipse ui` opens the daily overview: alerts from the latest saved scan,
changes compared with an earlier scan covering the same categories, and recent
local activity. The scan date, unknown results, overdue automations, and failed
automation runs help identify what needs attention. Reports older than seven
days are marked for refresh. Opening the overview does not run a security scan.

Quick actions let you check the Mac and save the report, review suggested
actions from that report, create an Eclipse recovery snapshot, review
automations, or browse activity history. `[t] All tools` opens the complete
catalog, including files, memory, scripts, security, recovery, and VPS transfers;
`[r]` refreshes the overview. Recovery snapshots cover Eclipse data, not the
whole Mac. Automations still require `run-due` or an external scheduler.

Scans launched from the interactive scan menu now save their results to report
history. Their default result is a short summary of passed checks, findings to
review, and skipped or uncertain checks. Press `d` for technical details, `a`
for suggested actions, or Enter to return. Raw process arguments and connection
lists remain in the detailed report. The detailed text output explains the score calculation, represented
categories, and unknown results. The score is a heuristic for the reported
findings; unknown results do not lower it and it is not a whole-Mac guarantee.


Inventory results are distinguished from unknown checks. Additional Homebrew
taps and sharing-related listeners alone are informational; detected SSH/SMB/
screen-sharing listeners still require review. An unavailable Docker daemon is
a skipped runtime inspection, not a security penalty. SSH permission warnings
apply to files with a recognized private-key header; unreadable files are
reported as unknown. Existing saved reports retain their original findings;
run a fresh scan to use these classifications.

## Local Files

Eclipse includes a local file explorer for macOS. It can browse folders, preview
UTF-8 text files, create files and folders, copy, move, rename, send files to
the macOS Trash, and open paths through Finder or the default macOS app.
Sensitive paths such as system folders, `~/Library`, `~/.ssh`, `~/.gnupg`, and
`~/.config` require explicit confirmation before write operations.

Useful commands:

```bash
eclipse files favorites
eclipse files ls ~/Documents --hidden
eclipse files info ~/.ssh
eclipse files cat ~/Documents/note.txt
eclipse files write ~/Documents/note.txt "Appended note" --append
eclipse files edit-line ~/Documents/note.txt 2 "Replacement line"
eclipse files mkdir ~/Documents/Eclipse
eclipse files rename ~/Documents/old.txt new.txt
eclipse files copy ~/Documents/new.txt ~/Desktop/new.txt
eclipse files move ~/Desktop/new.txt ~/Documents/Eclipse/new.txt
eclipse files trash ~/Documents/Eclipse/new.txt --yes
eclipse files open ~/Documents
eclipse files preview ~/Downloads/archive.zip
eclipse files search ~/Projects config --name "*.json" --depth 5
eclipse files chmod+x ~/scripts/tool.sh
eclipse files script-add ~/scripts/tool.sh tool
```

`trash` requires `--yes` in the CLI. In the interactive UI, Eclipse asks for
confirmation before moving a path to the Trash. Mutating operations are written
to the private audit log, and Eclipse creates local backups before overwriting,
moving, renaming, editing, or trashing existing paths unless `--no-backup` is
used.

Preview supports directories, UTF-8 text, JSON pretty-printing, image metadata
for common formats, and ZIP archive listings.

Advanced search supports filename, content, extension, size, modification dates,
ignored folders, depth limits, result limits, and JSON export:

```bash
eclipse files search ~/Projects config --content database --extension py
eclipse files search ~/Documents --name "*.pdf" --min-size 10000
eclipse files search ~/Projects token --ignore .git --ignore node_modules --export ~/Desktop/results.json
```

## Automations

Eclipse can store local scheduled automations. It does not install a background
daemon by itself; `run-due` is the command to trigger from the terminal, a
LaunchAgent, cron, or another local scheduler.

Useful commands:

```bash
eclipse automation add daily-security-scan --every day
eclipse automation add weekly-snapshot --every week --command recovery snapshot
eclipse automation suggestions
eclipse automation quickstart
eclipse automation list
eclipse automation run daily-security-scan --dry-run
eclipse automation run-due
eclipse automation disable weekly-snapshot
eclipse automation enable weekly-snapshot
eclipse automation history
```

Automation definitions and history are stored privately in:

```text
~/Library/Application Support/Eclipse/automation
```

When no automation exists, `automation list` prints a small default catalog of
beginner-friendly automations with exact commands to add them. `automation
suggestions` shows that catalog on demand. `automation quickstart` explains how
to preview due jobs, run them manually, and wire `eclipse automation run-due`
into a shell scheduler or LaunchAgent.

## Logs

Eclipse includes a `logs` category that centralizes local activity logs with the
date, time, user, source, action, status, and details for each entry.

Supported sources:

- `audit`: Eclipse actions such as file writes, moves, backups, recovery, and
  automations.
- `scripts`: personal script execution history.
- `automation`: scheduled automation execution history.
- `security`: generated security reports.
- `system`: recent macOS system logs, queried on demand.

Useful commands:

```bash
eclipse logs list
eclipse logs list --source scripts --limit 20
eclipse logs list --source audit --source security --query firewall
eclipse logs list --user "$USER" --since 2026-09-01
eclipse logs list --system --limit 20
eclipse logs list --export ~/Desktop/eclipse-logs.json
```

`system` logs are read from macOS only when requested with `--system` or
`--source system`. Eclipse does not store system logs permanently by default.

## Administration And Security

The `security` category contains Eclipse's local macOS security features. The
main executable action is the security scan:

```bash
eclipse security scan
eclipse security scan --deep
eclipse security scan --check security --check firewall
eclipse security scan --json
```

The scanner is based on the original local Bash scanner, but it is integrated
directly into Eclipse and remains read-only. JSON reports are written by default
to:

```text
~/Library/Application Support/Eclipse/security-reports
```

`--deep` enables slower checks, including the macOS update lookup through
`softwareupdate -l`.

Security findings are written with a versioned JSON schema. New reports include
stable check identifiers, normalized status values, source/evidence fields, and
risk weights so scans can be compared over time.

Useful follow-up commands:

```bash
eclipse security checks
eclipse security checks --verbose
eclipse security history --limit 10
eclipse security diff
eclipse security remediate plan
eclipse security remediate plan --check firewall
eclipse security baseline save
eclipse security baseline compare
eclipse security policy init
eclipse security policy show
eclipse security policy check
eclipse security report export --format markdown --output ~/Desktop/eclipse-security.md
eclipse security report export --format html --output ~/Desktop/eclipse-security.html
eclipse security secrets scan ~/Projects --limit 50
eclipse security downloads quarantine --folder ~/Downloads
eclipse security dmg inspect ~/Downloads/app.dmg
eclipse security dmg inspect ~/Downloads/app.dmg --open
```

`history` lists previous private JSON reports. `diff` compares the latest two
reports and highlights added, removed, changed, new risk, resolved, worse, and
better findings. `remediate plan` runs the selected checks and prints read-only
guidance; it never changes system settings.

`baseline save` stores the current expected security state. `baseline compare`
runs a fresh scan and shows what changed compared with that baseline. The
baseline is stored privately by default at:

```text
~/Library/Application Support/Eclipse/security-baseline.json
```

`policy init` writes a local severity policy with required checks, ignored
finding IDs, alert thresholds, and level overrides. `policy show` displays the
active policy, and `policy check` evaluates a fresh scan against it. The policy
is stored privately by default at:

```text
~/Library/Application Support/Eclipse/security-policy.json
```

`report export` turns the latest JSON report into JSON, Markdown, or HTML.

The Docker check now flags active daemon state, local containers, exposed host
ports, weak image tags such as `latest` or untagged images, privileged
containers, and sensitive host path mounts.

The interactive `eclipse ui` Security menu keeps the main page compact:
`[1] Scans`, `[2] Full JSON report`, `[3] Confirm password change`, `[4] Report
history`, `[5] Latest report diff`, `[6] Remediation plan`, `[7] Save baseline`,
and `[8] Compare baseline`. The `Scans` submenu groups the quick scan, full
scan, targeted checks, local secret pattern scan, downloads quarantine audit,
and DMG inspection.

Eclipse also tracks password rotation. The UI header shows a password indicator
in the upper right:

- red by default when password rotation has not been confirmed;
- green after the user confirms passwords have been changed;
- red again after 6 months.

Useful commands:

```bash
eclipse security password status
eclipse security password confirm
eclipse admin status
eclipse admin report
eclipse security scan --json --output-dir ~/Backups/eclipse-security
```

The password rotation state is stored privately in:

```text
~/Library/Application Support/Eclipse/security-state.json
```

## Local Memory

Local Memory is Eclipse's private local notebook. Use it for decisions, project
context, useful paths, commands you reuse, security observations, and follow-up
tasks. It is intentionally simple: entries stay on the Mac, can be tagged, can
be attached to a project, and can be exported when needed.

By default, memory entries are stored in:

```text
~/Library/Application Support/Eclipse/memory.jsonl
```

The file is created with private permissions. Each entry contains an identifier,
a UTC timestamp, the text, optional tags, a source, and a project.

For tests, scripts, or migrations, set `ECLIPSE_MEMORY_PATH` to override the
default path:

```bash
eclipse memory guide
eclipse memory add "Use recovery snapshots before risky changes" --tag backup,safety --project eclipse
eclipse memory list --limit 10
eclipse memory search snapshot --project eclipse
eclipse memory tags
eclipse memory projects
eclipse memory update MEMORY_ID --text "Updated decision" --tag backup,decision
eclipse memory delete MEMORY_ID --yes
eclipse memory export ~/Desktop/eclipse-memory.json
ECLIPSE_MEMORY_PATH=/path/to/memory.jsonl eclipse memory stats
```

## Local Scripts

By default, Eclipse stores the script registry and private script copies in:

```text
~/Library/Application Support/Eclipse/scripts
```

Scripts ending in `.py`, `.sh`, `.bash`, `.zsh`, and `.js` are executed with the
matching local interpreter. Other files are executed directly.

When running from a source checkout, you can also drop personal scripts directly into the project-level `scripts/`
folder, or into `eclipse/scripts/` if you want the drop-in folder next to the
Python package. Eclipse discovers files from those folders automatically, lists
them in the CLI and UI, and lets you execute them without running
`eclipse scripts add`. Files inside both drop-in folders are ignored by Git so
personal scripts are not published with the project. For a normal installed copy,
prefer `eclipse scripts add` so your scripts stay outside the package and survive updates.

Useful commands:

```bash
eclipse scripts add name ~/scripts/tool.py --description "local tool" --tag mac
eclipse scripts add risky ~/scripts/risky.sh --dry-run-required
eclipse scripts list
eclipse scripts info name
eclipse scripts history
eclipse scripts run name -- --flag
eclipse scripts run risky --dry-run
eclipse scripts run risky --force
eclipse scripts path name
eclipse scripts remove name --delete-file
```

For tests or a separate profile, set `ECLIPSE_SCRIPTS_HOME` to override the
default scripts directory:

```bash
ECLIPSE_SCRIPTS_HOME=/path/to/scripts eclipse scripts list
```

Script metadata can be declared in the first comments of a script:

```bash
# eclipse: description: Clean local build caches
# eclipse: tags: cleanup, maintenance
# eclipse: param: --dry-run
# eclipse: dry-run-required: true
```

Eclipse-level `--dry-run` only prints the command; it does not execute the script.
`--force -- --dry-run` executes a script with its own `--dry-run` argument, which
only works if that script implements it. A previous preview does not remove the
requirement to pass `--force` for protected scripts.

Eclipse reads those comments into the script catalog, displays declared
parameters, tracks execution history, and records the latest return code.

Packaged scripts:

- `daily-maintenance`: runs the security scan, light cleanup checks, and a
  summary report.
- `backup-eclipse-data`: backs up Eclipse data, scripts, logs, memory, recovery,
  and plugins under the Eclipse data directory, plus available project script folders.
- `restore-eclipse-data`: guides a restore from an Eclipse backup.
- `rotate-local-backups`: keeps the latest backups and removes older ones.
- `quarantine-downloads-audit`: lists downloaded files with macOS quarantine
  metadata.
- `safe-open-dmg`: inspects a DMG before opening it.
- `project-clean-cache`: removes common development caches from a project.
- `find-secrets-local`: searches for likely local secrets without printing them
  in clear text.
- `verify-backup`: checks that a `.tar.gz` backup is readable.
- `user-system-backup`: creates a local user system backup on the Desktop.

Examples:

```bash
eclipse scripts info daily-maintenance
eclipse scripts run daily-maintenance --force -- --dry-run
eclipse scripts run backup-eclipse-data --force -- --dry-run
eclipse scripts run safe-open-dmg --force -- --file ~/Downloads/app.dmg
```

## VPS Transfers

The `vps` category manages workflows between the local Mac and a remote VPS.
The first available workflow uploads a local file or folder through `rsync`
over SSH.

Useful commands:

```bash
eclipse vps upload ~/Documents/report.pdf --host 203.0.113.10 --user deploy --remote-path /srv/uploads --dry-run
eclipse vps upload ~/Projects/site --host example.com --remote-path /var/www/site --identity ~/.ssh/id_ed25519
eclipse vps upload ~/Backups/eclipse.tar.gz --host example.com --port 2222 --remote-path /home/deploy/backups
```

`--dry-run` asks `rsync` to show what would be transferred before writing to the
VPS. The command validates the local source, SSH port, identity file, host, user,
and remote path before starting the transfer.

VPS-specific code lives under:

```text
eclipse/vps/
  vps.py
  config/config.sh
```

`config/config.sh` inside the **installed Python package** can store optional defaults.
An installed copy is independent of the downloaded source directory. Locate it with:

```bash
~/.local/share/eclipse-venv/bin/python -c "from eclipse.vps.vps import default_config_path; print(default_config_path())"
```

Package upgrades may replace this file. Prefer explicit CLI options for durable
workflows. These names are file keys, not environment-variable overrides:


```bash
ECLIPSE_VPS_HOST="example.com"
ECLIPSE_VPS_USER="deploy"
ECLIPSE_VPS_REMOTE_PATH="/srv/uploads"
ECLIPSE_VPS_PORT="22"
ECLIPSE_VPS_IDENTITY="~/.ssh/id_ed25519"
```

Eclipse reads simple `KEY=value` lines from this file; it does not execute the
file as shell code. When these values are configured, the upload command can be
shorter:

```bash
eclipse vps upload ~/Documents/report.pdf --dry-run
```

## Plugins

Eclipse has a lightweight plugin layout so future modules can live outside the
core package:

```text
eclipse/plugins/
  docker/
  homebrew/
  git/
  network/
```

Each plugin has a `plugin.json` manifest. These are catalog entries and scaffolding;
Eclipse does not currently load executable extension hooks. User-created manifests
are stored in `~/Library/Application Support/Eclipse/plugins`. Current commands:

```bash
eclipse plugins list
eclipse plugins create local-tools --description "Local helper workflows"
```

## Recovery

Recovery mode snapshots Eclipse's private operational data, including local
memory, script registry/copies, and the audit log when those files exist.

Useful commands:

```bash
eclipse recovery snapshot
eclipse recovery view
eclipse recovery view snapshot-YYYYMMDD-HHMMSS-SUFFIX
eclipse recovery export ~/Library/Application\ Support/Eclipse/recovery/snapshot-YYYYMMDD-HHMMSS-SUFFIX
eclipse recovery export ./snapshot --password "local-passphrase"
eclipse recovery load snapshot-YYYYMMDD-HHMMSS-SUFFIX --destination ~/Desktop/eclipse-restore --yes
eclipse recovery restore ./snapshot --destination ~/Desktop/eclipse-restore --yes
```

Use the exact snapshot name printed by `snapshot` or `view`, including its random
suffix. Restoration requires a new or empty destination and does not automatically
replace live Eclipse data. Snapshots cover memory, registered scripts, and the audit
log; they do not include all Eclipse settings or your whole Mac. Exports are ZIP
archives, or authenticated AES-GCM encrypted archives when a password is supplied,
with a 256 MiB archive limit. CLI passwords can appear in shell history; use the
interactive Recovery menu for a hidden password prompt.

`view` without an argument lists saved snapshots with file counts, directory
counts, size, creation time, and path. `view <snapshot>` shows the contents of
one snapshot. `load <snapshot>` restores a snapshot into a destination folder;
it requires `--yes` because it writes files. `restore` remains available as the
direct path-based restore command.

Snapshots are stored by default in:

```text
~/Library/Application Support/Eclipse/recovery
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
