# Installation, updates and troubleshooting

[Back to README](../README.md)

## Requirements

- macOS; terminal features and checks use macOS utilities.
- Python 3.11 or newer, with `venv` and `pip`.
- Internet access for Python build tools and dependencies, including `cryptography`.
- SSH access and `ssh`/`rsync` only if using VPS uploads.

Get Python from [python.org](https://www.python.org/downloads/macos/).
The Python version supplied by another tool may be older: check `python3 --version`.
Eclipse does not install Python, Homebrew, Docker, or an SSH server.
No minimum macOS release or full Intel/Apple Silicon compatibility matrix has
been established; a supported Python interpreter and available utilities are required.

## Install from GitHub source

Download and extract **Code → Download ZIP**, or clone using the URL shown by the
repository's **Code** button. In Terminal, enter the extracted repository folder:

```bash
bash install.sh
~/.local/share/eclipse-venv/bin/eclipse ui
```

The installer always uses current source by default, even when old archives exist
in `dist/`. It verifies the installed command before modifying `~/.zprofile`.
It appends its PATH line only if that exact line is absent. It does not launch
Eclipse automatically or install a scheduler.

Options:

```bash
bash install.sh --help
bash install.sh --python python3.14
bash install.sh --no-path
bash install.sh --install-dir "$HOME/Applications/Eclipse Env" --no-path
```

`--no-path` leaves your shell profile alone; use the full launch command printed
by the installer. For bash/fish or a non-login shell, configure PATH in that shell
or keep using the full command. `--no-pip-upgrade` skips the pip upgrade but does
not make installation offline. `ECLIPSE_PYTHON` can select the interpreter too.
Do not move an installed virtual environment; reinstall at its new location.

## Install a release wheel or source archive

If the maintainer has uploaded a release, download its `eclipse_mac-*.whl` or
`eclipse_mac-*.tar.gz` asset. The commands below use the 0.3.0 wheel in Downloads;
adjust its filename and location to the file you downloaded.

```bash
python3 -m venv ~/.local/share/eclipse-venv
~/.local/share/eclipse-venv/bin/python -m pip install --upgrade pip
~/.local/share/eclipse-venv/bin/python -m pip install "$HOME/Downloads/eclipse_mac-0.3.0-py3-none-any.whl"
~/.local/share/eclipse-venv/bin/eclipse --version
~/.local/share/eclipse-venv/bin/eclipse ui
```

For a source archive, use its `.tar.gz` path in the same pip command. A wheel
already contains Eclipse's packaged scripts and manifests, but pip still needs
to install dependencies. This manual method does not update PATH.

From a checkout, `bash install.sh --wheel` or `--archive` installs the respective
artifact from `dist/`. Exactly one matching artifact must be present; ambiguity
is rejected instead of silently choosing an older build. `dist/` is not tracked
in Git; downloading source does not imply prebuilt assets exist.

## Update

Download/extract newer source and rerun `bash install.sh` from that folder.
For a clone, update your checkout first, preserving any local edits. This installs
into the existing environment; Eclipse's operational data stays separate.
Close the running Eclipse process and launch it again to load the new code.

For a downloaded wheel:

```bash
~/.local/share/eclipse-venv/bin/python -m pip install --upgrade "$HOME/Downloads/eclipse_mac-0.3.0-py3-none-any.whl"
```

Use the new asset's actual filename. Prefer uniquely versioned releases; if you
intentionally replace a wheel with the same version, pip may require
`--force-reinstall` to install its new contents.

## Uninstall

```bash
~/.local/share/eclipse-venv/bin/python -m pip uninstall eclipse-mac
```

Your notes, scripts, reports and snapshots remain in the locations listed in the
README. To remove the environment too, delete only `~/.local/share/eclipse-venv`
after checking its contents. Remove the `# Eclipse` PATH entry in `~/.zprofile`
if you no longer use it. Back up operational data before removing it separately.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `python3` missing or older than 3.11 | Install a supported Python and reopen Terminal, or pass `--python` with its executable path. |
| `eclipse: command not found` | Use `~/.local/share/eclipse-venv/bin/eclipse ui`; open a new zsh terminal for the installer PATH change. |
| Another `eclipse` program starts | Run `command -v eclipse`; use Eclipse's full virtual-environment path to avoid name conflicts. |
| `No module named cryptography` | Rerun `bash install.sh` from source, or reinstall your wheel using that environment's `python -m pip`. |
| pip reports an externally managed environment | Use the installer or the documented virtual environment instead of global pip. |
| Download, proxy or certificate error | Check connectivity and your proxy/certificate configuration; rerun installation after fixing it. Do not disable TLS verification. |
| Permission denied in Desktop/Documents or other folders | Review the Terminal application's macOS Privacy & Security permissions for the specific operation. |
| A check is unknown or skipped | Read `d` details. Utilities, permissions, stopped services and omitted deep checks affect coverage. |
| Docker unavailable | Start Docker only if you intend to inspect containers, then rerun the scan. |
| UI still shows old output after updating | Exit Eclipse completely and relaunch the newly installed command. |
| VPS defaults edited in source have no effect | Installed packages have a separate config copy. Prefer CLI flags; see the command guide. |

For a reproducible issue, include macOS version/architecture, `python3 --version`,
`eclipse --version`, your installation method, the command and the error text.
Review output for personal data before sharing. `eclipse --help` and
`eclipse security --help` list available commands.
