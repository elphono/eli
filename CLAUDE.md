# eli

**Le dépôt est public** (<https://github.com/elphono/eli>). Plugin Claude Code : Claude explique
par niveaux nommés (ELI5, ELI-lambda par défaut, ELI-initiate, ELI-Architect, ELI-Tech), et les
documents s'ouvrent sur une surface simple qui descend au clic vers le détail. Le README est la
vitrine ; ce fichier est le mode d'emploi de qui modifie le dépôt.

| Pièce | Fichier | Testée par |
|---|---|---|
| le style de réponse : le niveau (jusqu'où descendre) et l'ordre des idées (la destination d'abord, puis la chaîne la plus courte), les formes, l'écriture, les commandes | `output-styles/eli.md` (270 lignes au plus : il est renvoyé à chaque requête) | `tests/test_plugin.py` (chaque règle lue là où elle vit, absence de section de fin, plafond de lignes) |
| le skill `eli:documents` et son gabarit | `skills/documents/` | `tests/test_plugin.py` (arbre du gabarit, largeur d'un zoom), `tests/test_figures.py` (rendu sans défaut, surface d'un écran) |
| le skill `eli:figures` : gabarit, galerie des formes, `render.py` | `skills/figures/` | `tests/test_figures.py` |
| le contrôle des documents (HTML, visuels, niveaux, surface, sigles) | `hooks/eli-document.py`, déclaré par `hooks/hooks.json` | `tests/test_eli_document.py` |

**Langue** : tout ce qui est livré (style, skills, gabarits, hook, README) est en anglais et
générique : aucun prénom, aucun chemin personnel. `test_what_ships_is_generic` le vérifie. Ce
fichier et les messages de commit sont en français.

**Invariants** :

- le contrôle **bloque** (sortie 2) un document Markdown ou une page sans visuel (`svg`, `img`,
  `canvas`, `table`, ou un élément `data-figure`), et **avertit** pour le reste : niveaux, TL;DR,
  réseau, surface de plus de `SURFACE_MAX_WORDS` mots, sigles qu'aucun `data-def` ni
  `abbr[title]` n'explique, prose par visuel. Il ne sort jamais autrement qu'en 0 ou 2 : un
  contrôle cassé ne doit jamais casser une session. Il remplace le plugin visual-first de
  docpin, dont il accepte les marqueurs de dérogation ;
- niveaux, figures et définitions se lisent dans les attributs (html.parser), jamais dans le
  texte ; la table de la docstring du hook suit chaque contrôle ;
- l'heuristique des sigles est calibrée sur un corpus réel de documents : la modifier, c'est
  relancer le calibrage et relire la liste qu'elle signale (du jargon, pas des mots en
  capitales) ;
- le bloc CSS entre `/* eli-figures:start */` et `/* eli-figures:end */` est identique, octet
  pour octet, dans `skills/figures/template.html`, `skills/figures/forms.html` et
  `skills/documents/template.html` ; il porte la palette : le gabarit des documents n'y ajoute
  que `--page`, `--shadow` et `--scrim` ;
- la surface du gabarit des documents tient en un écran (900 px de haut à 1400x900) et
  300 mots ; un zoom prend la largeur de la page, seule sa prose est plafonnée vers 90
  caractères ;
- les zooms s'ouvrent par `dlg.show()`, jamais `showModal()` : la couche supérieure du navigateur
  passerait au-dessus de la bulle de note de docpin ;
- le plugin n'installe rien : le hook n'emploie que la bibliothèque standard. `render.py` porte
  ses propres métadonnées (PEP 723, bloc `# /// script` en tête) : `uv run render.py` lui fournit
  Playwright, à lui seul, depuis n'importe quel dossier, sans ce dépôt. L'épingle du script, sa
  constante `PLAYWRIGHT` et la dépendance de développement de `pyproject.toml` sont la même
  version (`test_the_script_pins_the_playwright_of_the_tests`) : en changer une, c'est changer
  les trois ;
- un mot contient au moins une lettre ou un chiffre, pour `render.py` (mots mesurés, libellés de
  plus de 8 mots) comme pour le hook (mots de la surface) : un « : » isolé n'en est pas un ;
- les skills parlent de leurs fichiers par `${CLAUDE_SKILL_DIR}`, que Claude Code remplace par le
  dossier du `SKILL.md` (constaté le 2026-11-23 par une session `claude -p --plugin-dir`), et
  disent quoi faire quand ils tournent dans un sous-agent, qui ne reçoit pas le style de sortie.

Vérifier avant de pousser :

```bash
uv sync --locked && uv run playwright install chromium
uv run pytest -q
uv run ruff check hooks tests tools skills
uv run python skills/figures/render.py skills/documents/template.html skills/figures/template.html skills/figures/forms.html --out /tmp/eli-render
(cd "$(mktemp -d)" && uv run "$OLDPWD/skills/figures/render.py" "$OLDPWD/skills/figures/template.html" --out .)   # hors du dépôt : uv fournit Playwright
claude plugin validate --json . > /tmp/r.json; python3 tools/check_plugin_report.py /tmp/r.json
```

`render.py` sort en 0 sans défaut ; ses PNG se regardent, ils ne se jugent pas sur la table.
La commande donnée par les skills est `uv run ${CLAUDE_SKILL_DIR}/render.py`, `python3` en repli
là où Playwright est installé ; Chromium s'installe une fois par `uvx playwright@1.58.0 install chromium`.

**Le style n'a plus de section de fin.** La section « 80/20 » de la 0.5.0 a été retirée en 0.6.0
à la demande de l'utilisateur (« c'est pire depuis qu'on l'a implémentée ») : la décision ou le
verdict vont en tête, et un choix fait à sa place qui dépend de ce que lui seul sait y est
signalé. Restent les règles des commandes, antérieures à la section.
`test_the_style_carries_no_80_20_section` et les graders `no-80-20-section` fixent l'absence.

**Les évaluations** (`evals/`, `claude plugin eval`) mesurent qu'une session neuve suit la règle :
une demande de dessin donne une page de figure sous `docs/`, jamais un dessin ASCII
(`draw-on-request`, `named-level`) ; une question fermée reste une ligne sans page
(`closed-question`, `closed-question-french`) ; une question posée s'ouvre sur la décision en
titre de niveau 1 en capitales, dessine son embranchement dans un bloc de code et ne pose qu'une
décision (`question-asked`) ; un compte rendu s'ouvre sur le verdict, sans raconter les moyens
ni les vérifications non demandées (`report-verdict`, qui corrige un fichier posé) ;
« explique-moi l'architecture » d'un petit projet posé donne une page de figure ouverte sur
ELI-Architect, en français (`architecture-french`). Chaque cas tourne avec et sans le plugin ;
l'écart est la mesure : sans le plugin, les graders de forme tombent (titre en capitales,
embranchement, page ouverte sur ELI-Architect). L'absence de section 80/20 ne départage pas les
deux bras : elle n'est pas un témoin.

```bash
uv sync --locked   # pyproject.toml impose link-mode = "copy" : l'outil refuse un plugin qui contient des liens physiques ; un .venv plus ancien se refait par uv sync --locked --reinstall
claude plugin eval . --no-publish --trust-plugin --scaffold --allow-tools Write Edit -j 6 --json /tmp/eli-eval.json
```

- `--no-publish` toujours : sans lui, le rapport part sur claude.ai. Les résultats vont dans
  `evals/results/`, ignoré par git.
- `--scaffold` lance `select-eli-style.sh` de chaque cas, qui choisit le style `eli:eli` dans les
  réglages utilisateur du run, comme l'étape 2 de l'installation : sans lui, l'outil démarre en
  style `default`, et le grader `style-active` tombe. Il copie aussi le dossier `workspace/` du
  cas, s'il en a un, dans le dossier de travail de la session (le projet de `architecture-french`,
  le fichier à corriger de `report-verdict`) : ces fichiers existent avant la session, ils
  n'entrent donc pas dans la liste `files` des graders. Les copies du script sont identiques
  (`test_eval_scaffold_copies_are_identical`) : l'outil refuse un lien symbolique ou un chemin hors
  du cas.
- **Pas de Bash dans les cas** : quand Bash est accordé, l'outil crée lui-même `settings.json`
  en exclusif, et le style ne peut plus être choisi. Le rendu par `render.py` n'est donc pas
  exercé par la suite.
- Les graders sur le contenu de la page lisent la trace (le `Write` ou l'`Edit` vers
  `docs/*.html`), parce que l'outil n'accepte pas de motif dans `{source: file, path}` et que le
  nom de la page n'est pas connu d'avance.
