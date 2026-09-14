"""Contrôles exécutables sans FastAPI ni base de données.

Ils rejouent la sérialisation et le récapitulatif sur des objets dont les attributs
sont strictement ceux déclarés dans models.py. Toute lecture d'un attribut non
déclaré lève une erreur ici plutôt qu'un 500 en production.
"""

import ast
import collections
import datetime as dtm
import pathlib
import sys
from datetime import date, datetime

RACINE = pathlib.Path(__file__).parent


def colonnes_du_modele():
    arbre = ast.parse((RACINE / "app/models.py").read_text())
    champs = {}
    for n in arbre.body:
        if not isinstance(n, ast.ClassDef):
            continue
        noms = set()
        for x in n.body:
            if isinstance(x, ast.Assign) and isinstance(x.targets[0], ast.Name):
                noms.add(x.targets[0].id)
            if isinstance(x, ast.FunctionDef):
                noms.add(x.name)
        champs[n.name] = noms
    return champs


CHAMPS = colonnes_du_modele()


class Strict:
    """Objet qui n'accepte que les attributs déclarés sur son modèle."""

    def __init__(self, modele, **valeurs):
        object.__setattr__(self, "_modele", modele)
        object.__setattr__(self, "_valeurs", dict(valeurs))
        inconnus = set(valeurs) - CHAMPS[modele]
        if inconnus:
            raise AssertionError(f"{modele} : le test invente {sorted(inconnus)}")

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        if nom not in CHAMPS[self._modele]:
            raise AttributeError(
                f"{self._modele} n'a pas de champ « {nom} » : le code le lit, "
                "le modèle ne le déclare pas.")
        return self._valeurs.get(nom)

    def __setattr__(self, nom, valeur):
        self._valeurs[nom] = valeur


def charger_fragment(fichier, debut, fin, espace):
    """Exécute la portion d'un module comprise entre deux repères, le second
    étant cherché après le premier."""
    src = (RACINE / fichier).read_text()
    i = src.index(debut)
    j = src.index(fin, i + len(debut))
    exec(src[i:j], espace)
    return espace


def construire_espace():
    espace = {"defaultdict": collections.defaultdict, "date": date, "datetime": datetime,
              "timedelta": dtm.timedelta}
    charger_fragment("app/seed_data.py", "JOURS = [", "def _obstacle", espace)

    class FauxSeed:
        nom_ferie = staticmethod(espace["nom_ferie"])
        libelle_regle = staticmethod(espace["libelle_regle"])

    espace["seed_data"] = FauxSeed

    class FauxModeles:
        """Les annotations de type des sérialiseurs référencent models.*"""
        def __getattr__(self, nom):
            return object

    espace["models"] = FauxModeles()
    # bloc de sérialisation complet, jusqu'au séparateur suivant
    charger_fragment("app/main.py", "def s_projet(", "# ---------", espace)
    charger_fragment("app/main.py", "def _chevauche(", "def recapitulatif(", espace)
    return espace


def heures_de(debut, fin, duree=None):
    if duree is not None:
        return float(duree)
    if not debut or not fin:
        return 0.0
    h1, m1 = (int(x) for x in debut.split(":"))
    h2, m2 = (int(x) for x in fin.split(":"))
    delta = (h2 * 60 + m2) - (h1 * 60 + m1)
    return (delta + 1440 if delta < 0 else delta) / 60.0


def jeu_d_essai():
    valideur = Strict("Utilisateur", id=1, nom="GANS COMBE Caroline", email="c@ece.fr",
                      role_global="admin", actif=True, doit_changer=False,
                      derniere_connexion=datetime(2026, 9, 14, 9, 0))
    personnes = [
        Strict("Personne", id=1, projet_id=1, nom="GANS COMBE Caroline",
               organisation="ECE Paris", role="Lead Lot 3", taux_horaire=85.0,
               imputable=True, note=""),
        Strict("Personne", id=2, projet_id=1, nom="BHUYAN Bikram Pratim",
               organisation="ECE Paris", role="Chercheur", taux_horaire=0.0,
               imputable=True, note=""),
    ]
    index = {p.id: p for p in personnes}

    def activite(i, jour, libelle, type_id, pid, h, statut="mesure", theorique=None,
                 source="agenda", mixte=False, validee=False, origine=False,
                 debut="09:00", fin="16:00", rec=None):
        a = Strict("Activite", id=i, projet_id=1, date=jour, date_theorique=theorique,
                   heure_debut=debut, heure_fin=fin, duree_h=h, libelle=libelle,
                   livrable="", part_imputable=100.0, source=source, statut=statut,
                   mixte=mixte, note="", type_tache_id=type_id, personne_id=pid,
                   recurrence_id=rec, origine_estimee=origine,
                   valide_le=datetime(2026, 9, 12, 10, 30) if validee else None,
                   valide_par_id=valideur.id if validee else None,
                   valide_par=valideur if validee else None,
                   personne=index[pid])
        a.heures = heures_de(debut, fin, h)
        a.heures_imputees = a.heures * a.part_imputable / 100
        a.cout = a.heures_imputees * (index[pid].taux_horaire or 0)
        a.validee = a.valide_le is not None
        a.mesuree_a_la_source = (statut == "mesure" and not origine)
        return a

    activites = [
        activite(1, date(2025, 6, 2), "Journée de recherche", 2, 1, 7.0,
                 source="declaratif", validee=True, origine=True, rec=1),
        activite(2, date(2026, 5, 4), "Journée de recherche", 2, 1, 7.0, statut="estime",
                 theorique=date(2026, 5, 1), source="declaratif", rec=1),
        activite(3, date(2026, 5, 14), "Tests de modèles", 3, 1, 3.0),
        activite(4, date(2026, 4, 22), "Journée mixte", 3, 1, 8.0, mixte=True),
        activite(5, date(2026, 7, 3), "Ligne sans durée", 2, 2, 0.0, statut="estime",
                 debut="", fin=""),
        # recouvrement volontaire : deux comités le même matin pour la même personne
        activite(6, date(2026, 6, 10), "Comité de pilotage", 1, 1, 4.0,
                 debut="08:30", fin="12:30"),
        activite(7, date(2026, 6, 10), "Comité de coordination", 1, 1, 3.0,
                 debut="09:00", fin="12:00"),
    ]
    depenses = [
        Strict("Depense", id=1, projet_id=1, date=date(2026, 5, 13), libelle="Colab L4",
               quantite=4.0, unite="heure-GPU", cout_unitaire=85.0, statut="mesure",
               reference="relevé", note="", categorie_id=1, personne_id=1),
    ]
    for d in depenses:
        d.montant = d.quantite * d.cout_unitaire
    projet = Strict("Projet", id=1, code="DEXTER4LLM", intitule="DEXTER4LLM Lot 3",
                    financeur="BPI France", date_debut=date(2025, 6, 1),
                    date_fin=date(2026, 9, 30), devise="EUR", heures_jour=7.0,
                    taux_defaut=0.0, actif=True)
    recurrence = Strict("Recurrence", id=1, projet_id=1, libelle="Journée de recherche",
                        jour_semaine=0, rang=1, date_debut=date(2025, 6, 1),
                        date_fin=date(2026, 2, 28), duree_h=7.0, part_imputable=100.0,
                        heure_debut="", heure_fin="", statut="estime", source="declaratif",
                        livrable="", note="", active=True, reporter=True,
                        type_tache_id=2, personne_id=1)
    types = [Strict("TypeTache", id=i, projet_id=1, code=c, libelle=l, couleur=k, ordre=i)
             for i, (c, l, k) in enumerate([("gouv", "Comité", "#0073EA"),
                                            ("travail", "Recherche", "#FDAB3D"),
                                            ("test", "Tests", "#E2445C")], start=1)]
    return projet, types, personnes, activites, depenses, recurrence


def principal():
    espace = construire_espace()
    projet, types, personnes, activites, depenses, recurrence = jeu_d_essai()
    echecs = []

    def verifier(intitule, fonction):
        try:
            fonction()
            print(f"ok     {intitule}")
        except Exception as erreur:
            echecs.append((intitule, erreur))
            print(f"ÉCHEC  {intitule} : {type(erreur).__name__} — {erreur}")

    verifier("sérialisation d'un projet", lambda: espace["s_projet"](projet, "gestionnaire"))
    verifier("sérialisation d'un type", lambda: espace["s_type"](types[0]))
    verifier("sérialisation d'une personne", lambda: espace["s_personne"](personnes[0]))
    verifier("sérialisation des lignes de temps",
             lambda: [espace["s_activite"](a) for a in activites])
    verifier("sérialisation des dépenses",
             lambda: [espace["s_depense"](d) for d in depenses])
    verifier("sérialisation d'une récurrence",
             lambda: espace["s_recurrence"](recurrence, 9))

    def controles():
        alertes = espace["controles"](activites, depenses, personnes, projet)
        types_vus = [a["type"] for a in alertes]
        assert len(types_vus) == len(set(types_vus)), f"alerte répétée : {types_vus}"
        for attendu in ("mixte", "duree", "ferie", "report", "a_valider", "validee",
                        "declaratif"):
            assert attendu in types_vus, f"alerte manquante : {attendu}"
    verifier("contrôles de cohérence", controles)

    def serialisation_complete():
        lignes = [espace["s_activite"](a) for a in activites]
        attendus = {"validee", "valide_le", "valide_par", "origine_estimee",
                    "mesuree_a_la_source", "reportee", "date_theorique"}
        manquants = attendus - set(lignes[0])
        assert not manquants, f"champs absents de la sortie : {sorted(manquants)}"
        validee = [l for l in lignes if l["validee"]][0]
        assert validee["origine_estimee"] is True
        assert validee["mesuree_a_la_source"] is False, \
            "une ligne validée ne doit jamais être présentée comme mesurée à la source"
    verifier("la validation reste distinguée de la mesure", serialisation_complete)

    def doublons():
        groupes = espace["groupes_doublons"](activites)
        assert len(groupes) == 1, f"un seul recouvrement attendu, {len(groupes)} trouvé(s)"
        groupe = groupes[0]
        assert set(groupe["ids"]) == {6, 7}, groupe["ids"]
        assert groupe["heures_cumulees"] == 7.0, groupe["heures_cumulees"]
        assert groupe["heures_retenues"] == 4.0, groupe["heures_retenues"]
        assert groupe["ids"][0] == 6, "la ligne la plus longue doit venir en tête"
    verifier("regroupement des recouvrements", doublons)

    def sans_faux_positif():
        isolees = [a for a in activites if a.id in (1, 3)]
        assert espace["groupes_doublons"](isolees) == [], \
            "deux lignes de personnes ou de jours différents ne sont pas un recouvrement"
        sans_horaire = [a for a in activites if a.id == 5]
        assert espace["groupes_doublons"](sans_horaire * 1) == []
    verifier("pas de faux positif sur les recouvrements", sans_faux_positif)

    print()
    if echecs:
        print(f"{len(echecs)} contrôle(s) en échec.")
        return 1
    print("Tous les contrôles passent.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
