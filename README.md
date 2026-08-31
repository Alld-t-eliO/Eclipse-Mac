# Eclipse 0.3

Eclipse est un centre de contrôle local pour macOS. Il permet d'inspecter le
Mac, parcourir les dossiers courants, stocker une mémoire locale et lancer des
scripts personnels depuis une interface terminal ou la CLI.

## Fonctions disponibles

- tableau de bord local : macOS, CPU, mémoire, disque, shell et dossier perso ;
- inspection rapide de Desktop, Downloads, Documents, Pictures, Movies et Music ;
- mémoire locale JSONL pour notes, décisions, tags, projets et exports ;
- registre de scripts personnels avec copie privée et exécution locale ;
- journal JSONL privé dans `~/.local/state/eclipse/audit.jsonl`.

## Installation locale

```bash
cd ~/Eclipse
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Exemples

```bash
eclipse ui
eclipse mac status
eclipse mac files downloads --limit 10
eclipse memory add "Décision ou observation" --tag mac,local --project eclipse
eclipse memory search observation --project eclipse
eclipse memory stats
eclipse memory export ~/Backups/eclipse-memory.json
eclipse scripts add cleanup ~/scripts/cleanup.sh --tag maintenance
eclipse scripts list
eclipse scripts run cleanup --dry-run -- --verbose
eclipse scripts run cleanup -- --verbose
```

`eclipse ui` ouvre le centre de contrôle interactif cyan, vert et rouge. Le
premier écran affiche l'état du Mac, puis donne accès aux fichiers locaux, à la
mémoire et aux scripts.

## Mémoire locale

Par défaut, la mémoire est écrite dans
`~/Library/Application Support/Eclipse/memory.jsonl` avec des permissions
privées. Chaque entrée contient un identifiant, une date UTC, le texte, des tags
optionnels, une source et un projet.

Pour tests, scripts ou migrations, `ECLIPSE_MEMORY_PATH=/chemin/memory.jsonl`
remplace le chemin par défaut.

## Scripts locaux

Par défaut, Eclipse stocke le registre et les copies privées dans
`~/Library/Application Support/Eclipse/scripts`. Les scripts `.py`, `.sh`,
`.bash`, `.zsh` et `.js` sont lancés avec l'interpréteur local correspondant ;
les autres fichiers sont exécutés directement.

Commandes utiles :

```bash
eclipse scripts add nom ~/scripts/outil.py --description "outil local" --tag mac
eclipse scripts path nom
eclipse scripts remove nom --delete-file
```

Pour tests ou profil séparé, `ECLIPSE_SCRIPTS_HOME=/chemin/scripts` remplace le
dossier par défaut.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
