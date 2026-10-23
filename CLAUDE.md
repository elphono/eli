# eli

**Le dépôt est public** (<https://github.com/elphono/eli>). Plugin Claude Code : Claude explique
par niveaux nommés (ELI5, ELI-lambda par défaut, ELI-initiate, ELI-Architect, ELI-Tech), et les
documents s'ouvrent sur une surface simple qui descend au clic vers le détail. Le README est la
vitrine ; ce fichier est le mode d'emploi de qui modifie le dépôt.

| Pièce | Fichier | Testée par |
|---|---|---|
| le style de réponse | `output-styles/eli.md` | `tests/test_plugin.py` |
| le skill `eli:documents` et son gabarit | `skills/documents/` | `tests/test_plugin.py` (arbre du gabarit) |
| le contrôle des documents (HTML, visuels, niveaux) | `hooks/eli-document.py`, déclaré par `hooks/hooks.json` | `tests/test_eli_document.py` |

**Langue** : tout ce qui est livré (style, skill, gabarit, hook, README) est en anglais et
générique : aucun prénom, aucun chemin personnel. `test_what_ships_is_generic` le vérifie. Ce
fichier et les messages de commit sont en français.

**Invariants** :

- le contrôle **bloque** (sortie 2) un document Markdown ou une page sans visuel, et
  **avertit** pour le reste, les niveaux d'abord ; il ne sort jamais autrement qu'en 0 ou 2 : un
  contrôle cassé ne doit jamais casser une session. Il remplace le plugin visual-first de docpin,
  dont il accepte les marqueurs de dérogation ;
- les niveaux se lisent dans les attributs `data-eli` (html.parser), jamais dans le texte ;
- les zooms s'ouvrent par `dlg.show()`, jamais `showModal()` : la couche supérieure du navigateur
  passerait au-dessus de la bulle de note de docpin ;
- aucune dépendance d'exécution : le hook n'emploie que la bibliothèque standard.

Vérifier avant de pousser : `uv run pytest -q`, `uv run ruff check hooks tests tools`, et
`claude plugin validate --json . > /tmp/r.json; python3 tools/check_plugin_report.py /tmp/r.json`.
