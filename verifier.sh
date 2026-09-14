#!/usr/bin/env bash
# Contrôles à lancer avant tout déploiement. Aucune dépendance externe requise.
set -e
echo "== compilation =="
python3 -m py_compile app/*.py
echo "== doublons de définitions =="
python3 - <<'PY'
import ast, pathlib
from collections import Counter
def doublons(corps):
    noms = [x.name for x in corps if isinstance(x, (ast.FunctionDef, ast.ClassDef))]
    noms += [t.id for x in corps if isinstance(x, ast.Assign)
             for t in x.targets if isinstance(t, ast.Name)]
    return [n for n, k in Counter(noms).items() if k > 1]
faute = 0
for f in sorted(pathlib.Path("app").glob("*.py")):
    arbre = ast.parse(f.read_text())
    trouve = doublons(arbre.body)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.ClassDef, ast.FunctionDef)):
            trouve += [x for x in doublons(n.body)
                       if any(isinstance(y, (ast.FunctionDef, ast.ClassDef)) and y.name == x
                              for y in n.body)]
    if trouve:
        faute = 1
        print(f"  {f} : {sorted(set(trouve))}")
print("  aucun" if not faute else "  À CORRIGER")
raise SystemExit(faute)
PY
echo "== routes en double =="
python3 - <<'PY'
import ast, pathlib
from collections import Counter
arbre = ast.parse(pathlib.Path("app/main.py").read_text())
routes = []
for n in arbre.body:
    if not isinstance(n, ast.FunctionDef):
        continue
    for d in n.decorator_list:
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.args and isinstance(d.args[0], ast.Constant)):
            routes.append((d.func.attr.upper(), d.args[0].value))
doubles = [k for k, v in Counter(routes).items() if v > 1]
print("  " + (str(doubles) if doubles else "aucune"))
raise SystemExit(1 if doubles else 0)
PY
echo "== migration deduite du modele, pas d une liste a la main =="
python3 - <<'PY'
import pathlib
src = pathlib.Path("app/main.py").read_text()
assert "COLONNES_AJOUTEES" not in src, (
    "une liste de colonnes tenue a la main est reapparue : elle finira par oublier une colonne")
assert "Base.metadata.sorted_tables" in src, "la migration doit se deduire du modele"
print("  ok")
PY

echo "== cohérence modèle, API et interface =="
python3 tests_hors_ligne.py
echo "== interface : execution des fonctions de rendu =="
if command -v node >/dev/null 2>&1; then
  node tests_interface.js | sed "s/^/  /"
else
  echo "  node absent, controle saute"
fi

echo "== interface : identifiants et équilibrage =="
python3 - <<'PY'
import pathlib, re
h = pathlib.Path("app/static/index.html").read_text()
js = h.split("<script>")[1].split("</script>")[0]
assert js.count("{") == js.count("}"), "accolades déséquilibrées"
assert js.count("(") == js.count(")"), "parenthèses déséquilibrées"
manquants = sorted(set(re.findall(r'byId\("([\w\-]+)"\)', js))
                   - set(re.findall(r'id="([\w\-]+)"', h)))
assert not manquants, f"identifiants absents du DOM : {manquants}"
print("  ok")
PY
echo
echo "Tous les contrôles passent."
