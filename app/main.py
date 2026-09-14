"""Suivi des temps et dépenses, API multi-projet.

Trois niveaux de droits par projet : gestionnaire qui voit et modifie tout,
contributeur qui ne voit et ne modifie que ses propres lignes, lecteur en
consultation. L'administration gère les comptes, les projets et les accès.
"""

import csv
import io
import os
import traceback
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, joinedload

from . import models, schemas, securite, seed_data, tableau_bord
from .database import Base, SessionLocal, engine, get_db

VERSION = "2.3.0"
REVISION = "tableau-doublons-r5"

app = FastAPI(title="Suivi des temps et dépenses", version=VERSION)
STATIC_DIR = Path(__file__).parent / "static"

# Une erreur non prévue doit arriver lisible à l'écran plutôt que sous la forme d'un 500
# muet. La trace complète part dans les journaux ; le détail renvoyé reste court.
DETAIL_ERREURS = os.getenv("DETAIL_ERREURS", "1") == "1"


@app.exception_handler(Exception)
def erreur_inattendue(requete, exc):
    traceback.print_exc()
    detail = "Erreur interne. Consultez les journaux du service."
    if DETAIL_ERREURS:
        detail = f"Erreur interne : {type(exc).__name__} — {exc}"
    return JSONResponse({"detail": detail}, status_code=500)

def _valeur_sql(valeur) -> str:
    """Littéral SQL correspondant au défaut Python d'une colonne."""
    if isinstance(valeur, bool):
        return "TRUE" if valeur else "FALSE"
    if isinstance(valeur, (int, float)):
        return str(valeur)
    return "'" + str(valeur).replace("'", "''") + "'"


def _definition_colonne(colonne) -> str:
    """Fragment DDL d'ajout d'une colonne, dérivé du modèle lui-même.

    Une colonne non nulle exige une valeur pour les lignes déjà présentes : on
    reprend le défaut Python déclaré sur le modèle. À défaut de défaut, la colonne
    est créée nullable plutôt que de faire échouer la migration.
    """
    fragment = colonne.type.compile(engine.dialect)
    defaut = getattr(colonne.default, "arg", None) if colonne.default is not None else None
    if defaut is not None and not callable(defaut):
        fragment += f" DEFAULT {_valeur_sql(defaut)}"
        if not colonne.nullable:
            fragment += " NOT NULL"
    elif not colonne.nullable:
        print(f"Migration : {colonne.name} est déclarée non nulle sans valeur par défaut, "
              "elle est ajoutée nullable pour ne pas rompre les lignes existantes.")
    return fragment


def colonnes_manquantes():
    """Colonnes présentes dans le modèle et absentes de la base."""
    with engine.connect() as connexion:
        inspecteur = inspect(connexion)
        tables = set(inspecteur.get_table_names())
        manquantes = []
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            presentes = {c["name"] for c in inspecteur.get_columns(table.name)}
            for colonne in table.columns:
                if colonne.name not in presentes:
                    manquantes.append((table.name, colonne))
    return manquantes


def migrer() -> None:
    """Aligne la base sur le modèle, sans liste tenue à la main.

    Les colonnes à ajouter sont déduites de Base.metadata : une colonne ajoutée au
    modèle est donc migrée d'office, ce qu'une liste manuelle ne garantissait pas.
    Chaque ALTER a sa propre transaction, afin qu'un échec isolé n'annule pas les
    autres, ce que Postgres ferait dans une transaction commune.
    """
    for nom_table, colonne in colonnes_manquantes():
        ordre = (f"ALTER TABLE {nom_table} ADD COLUMN "
                 f"{colonne.name} {_definition_colonne(colonne)}")
        try:
            with engine.begin() as connexion:
                connexion.execute(text(ordre))
            print(f"Migration : colonne {nom_table}.{colonne.name} ajoutée.")
        except Exception as erreur:
            print(f"Migration : échec sur {nom_table}.{colonne.name} ({erreur}).")
            print(f"            ordre exécuté : {ordre}")

    try:
        with engine.begin() as connexion:
            connexion.execute(text(
                "UPDATE activites SET date_theorique = date "
                "WHERE recurrence_id IS NOT NULL AND date_theorique IS NULL"))
    except Exception as erreur:
        print(f"Migration : reprise des dates théoriques impossible ({erreur}).")


def verifier_schema() -> None:
    """Dernier contrôle après migration : ce qui manque encore est nommé."""
    manquantes = [f"{table}.{colonne.name}" for table, colonne in colonnes_manquantes()]
    tables_absentes = []
    with engine.connect() as connexion:
        existantes = set(inspect(connexion).get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existantes:
            tables_absentes.append(f"table {table.name}")
    ecarts = tables_absentes + manquantes
    if ecarts:
        print("=" * 68)
        print("SCHÉMA INCOMPLET, l'application renverra des erreurs sur ces objets :")
        for nom in ecarts:
            print("  manque " + nom)
        print("Exécutez migration_manuelle.sql dans la console Postgres, ou redémarrez")
        print("une fois avec REINIT_SCHEMA=1 pour tout recréer. REINIT_SCHEMA efface les données.")
        print("=" * 68)
    else:
        print("Schéma vérifié : toutes les colonnes attendues sont présentes.")


@app.on_event("startup")
def demarrage() -> None:
    # Bandeau de démarrage : permet de lire dans les journaux quelle version tourne
    # réellement, plutôt que de la supposer d'après le dépôt.
    print("=" * 68)
    print(f"Suivi des temps et dépenses, version {VERSION}, révision {REVISION}")
    print("=" * 68)
    if os.getenv("REINIT_SCHEMA") == "1":
        print("REINIT_SCHEMA=1, suppression et recréation de toutes les tables.")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    migrer()
    verifier_schema()
    db = SessionLocal()
    try:
        seed_data.amorcer(db)
    finally:
        db.close()


# --------------------------------------------------------------------------
# sérialisation
# --------------------------------------------------------------------------

def s_projet(p: models.Projet, role=None) -> dict:
    return {
        "id": p.id, "code": p.code, "intitule": p.intitule, "financeur": p.financeur or "",
        "date_debut": p.date_debut.isoformat(), "date_fin": p.date_fin.isoformat(),
        "devise": p.devise, "heures_jour": p.heures_jour, "taux_defaut": p.taux_defaut,
        "actif": p.actif, "role": role,
        "artefacts_tableau": p.artefacts_tableau or models.ARTEFACTS_DEFAUT,
    }


def s_utilisateur(u: models.Utilisateur, acces=None) -> dict:
    d = {
        "id": u.id, "email": u.email, "nom": u.nom, "role_global": u.role_global,
        "actif": u.actif, "doit_changer": u.doit_changer,
        "derniere_connexion": u.derniere_connexion.isoformat() if u.derniere_connexion else None,
    }
    if acces is not None:
        d["acces"] = acces
    return d


def s_personne(p: models.Personne) -> dict:
    return {"id": p.id, "nom": p.nom, "organisation": p.organisation or "", "role": p.role or "",
            "taux_horaire": p.taux_horaire, "imputable": p.imputable, "note": p.note or ""}


def s_type(t) -> dict:
    return {"id": t.id, "code": t.code, "libelle": t.libelle, "couleur": t.couleur, "ordre": t.ordre}


def s_activite(a: models.Activite) -> dict:
    return {
        "id": a.id, "date": a.date.isoformat(),
        "date_theorique": a.date_theorique.isoformat() if a.date_theorique else None,
        "reportee": bool(a.date_theorique and a.date_theorique != a.date),
        "heure_debut": a.heure_debut or "", "heure_fin": a.heure_fin or "",
        "duree_h": a.duree_h, "libelle": a.libelle, "livrable": a.livrable or "",
        "part_imputable": a.part_imputable, "source": a.source, "statut": a.statut,
        "mixte": a.mixte, "note": a.note or "", "type_tache_id": a.type_tache_id,
        "personne_id": a.personne_id, "recurrence_id": a.recurrence_id,
        "heures": round(a.heures, 4), "heures_imputees": round(a.heures_imputees, 4),
        "cout": round(a.cout, 2),
        "validee": a.valide_le is not None,
        "valide_le": a.valide_le.isoformat() if a.valide_le else None,
        "valide_par": (a.valide_par.nom or a.valide_par.email) if a.valide_par else None,
        "origine_estimee": bool(a.origine_estimee),
        "mesuree_a_la_source": a.mesuree_a_la_source,
    }


def s_depense(d: models.Depense) -> dict:
    return {"id": d.id, "date": d.date.isoformat(), "libelle": d.libelle, "quantite": d.quantite,
            "unite": d.unite or "", "cout_unitaire": d.cout_unitaire, "statut": d.statut,
            "reference": d.reference or "", "note": d.note or "", "categorie_id": d.categorie_id,
            "personne_id": d.personne_id, "montant": round(d.montant, 2)}


def s_recurrence(r: models.Recurrence, nb: int) -> dict:
    return {"id": r.id, "libelle": r.libelle, "jour_semaine": r.jour_semaine, "rang": r.rang,
            "regle": seed_data.libelle_regle(r.jour_semaine, r.rang),
            "date_debut": r.date_debut.isoformat(), "date_fin": r.date_fin.isoformat(),
            "duree_h": r.duree_h, "part_imputable": r.part_imputable,
            "heure_debut": r.heure_debut or "", "heure_fin": r.heure_fin or "",
            "statut": r.statut, "source": r.source, "livrable": r.livrable or "",
            "note": r.note or "", "active": r.active, "reporter": bool(r.reporter),
            "type_tache_id": r.type_tache_id, "personne_id": r.personne_id, "occurrences": nb}


# --------------------------------------------------------------------------
# authentification
# --------------------------------------------------------------------------

@app.post("/api/connexion")
def connexion(corps: schemas.Connexion, db: Session = Depends(get_db)):
    u = db.query(models.Utilisateur).filter_by(email=corps.email.strip().lower()).first()
    if not u or not securite.verifier(corps.mot_de_passe, u.mot_de_passe):
        raise HTTPException(401, "Identifiants incorrects.")
    if not u.actif:
        raise HTTPException(403, "Ce compte est désactivé.")
    u.derniere_connexion = datetime.utcnow()
    db.commit()
    reponse = JSONResponse({"utilisateur": s_utilisateur(u)})
    reponse.set_cookie(securite.COOKIE, securite.creer_jeton(u.id), httponly=True,
                       samesite="lax", max_age=securite.DUREE_SESSION,
                       secure=os.getenv("COOKIE_SECURE", "1") == "1")
    return reponse


@app.post("/api/deconnexion")
def deconnexion():
    reponse = JSONResponse({"deconnecte": True})
    reponse.delete_cookie(securite.COOKIE)
    return reponse


def _mes_projets(u: models.Utilisateur, db: Session):
    if u.est_admin:
        return [s_projet(p, models.GESTIONNAIRE)
                for p in db.query(models.Projet).order_by(models.Projet.intitule).all()]
    projets = [s_projet(a.projet, a.role)
               for a in db.query(models.Acces).filter_by(utilisateur_id=u.id).all()
               if a.projet and a.projet.actif]
    projets.sort(key=lambda p: p["intitule"])
    return projets


@app.get("/api/moi")
def moi(u: models.Utilisateur = Depends(securite.utilisateur_courant),
        db: Session = Depends(get_db)):
    return {"utilisateur": s_utilisateur(u), "projets": _mes_projets(u, db)}


@app.post("/api/moi/mot-de-passe")
def changer_mot_de_passe(corps: schemas.ChangementMotDePasse,
                         u: models.Utilisateur = Depends(securite.utilisateur_courant),
                         db: Session = Depends(get_db)):
    if not u.doit_changer and not securite.verifier(corps.ancien, u.mot_de_passe):
        raise HTTPException(403, "Mot de passe actuel incorrect.")
    u.mot_de_passe = securite.hacher(corps.nouveau)
    u.doit_changer = False
    db.commit()
    return {"change": True}


# --------------------------------------------------------------------------
# périmètre
# --------------------------------------------------------------------------

def scope(projet_id: int, db: Session = Depends(get_db),
          u: models.Utilisateur = Depends(securite.utilisateur_courant)) -> securite.Portee:
    return securite.portee(projet_id, db, u)


def activites_visibles(p: securite.Portee, db: Session):
    q = db.query(models.Activite).options(joinedload(models.Activite.personne)) \
        .filter(models.Activite.projet_id == p.projet.id)
    if p.restreint:
        q = q.filter(models.Activite.personne_id == p.personne_id)
    return q.order_by(models.Activite.date.desc()).all()


def depenses_visibles(p: securite.Portee, db: Session):
    q = db.query(models.Depense).filter(models.Depense.projet_id == p.projet.id)
    if p.restreint:
        q = q.filter(models.Depense.personne_id == p.personne_id)
    return q.order_by(models.Depense.date.desc()).all()


def verifier_projet(p: securite.Portee, objet, nom="Cet élément"):
    if objet is None or objet.projet_id != p.projet.id:
        raise HTTPException(404, f"{nom} est introuvable dans ce projet.")
    return objet


# --------------------------------------------------------------------------
# état d'un projet
# --------------------------------------------------------------------------

@app.get("/api/projets")
def liste_projets(u: models.Utilisateur = Depends(securite.utilisateur_courant),
                  db: Session = Depends(get_db)):
    return _mes_projets(u, db)


@app.get("/api/projets/{projet_id}/etat")
def etat(projet_id: int, p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    activites = activites_visibles(p, db)
    recurrences = db.query(models.Recurrence).filter_by(projet_id=p.projet.id) \
        .order_by(models.Recurrence.date_debut).all()
    if p.restreint:
        recurrences = [r for r in recurrences if r.personne_id == p.personne_id]
    compte = defaultdict(int)
    for a in activites:
        if a.recurrence_id:
            compte[a.recurrence_id] += 1
    return {
        "projet": s_projet(p.projet, p.role),
        "droits": {"pilote": p.pilote, "restreint": p.restreint,
                   "lecture_seule": p.lecture_seule, "admin": p.est_admin,
                   "personne_id": p.personne_id},
        "types": [s_type(t) for t in db.query(models.TypeTache).filter_by(projet_id=p.projet.id)
                  .order_by(models.TypeTache.ordre, models.TypeTache.id).all()],
        "categories": [s_type(c) for c in db.query(models.CategorieDepense)
                       .filter_by(projet_id=p.projet.id)
                       .order_by(models.CategorieDepense.ordre, models.CategorieDepense.id).all()],
        "personnes": [s_personne(x) for x in db.query(models.Personne)
                      .filter_by(projet_id=p.projet.id).order_by(models.Personne.nom).all()],
        "activites": [s_activite(a) for a in activites],
        "depenses": [s_depense(d) for d in depenses_visibles(p, db)],
        "recurrences": [s_recurrence(r, compte[r.id]) for r in recurrences],
        "doublons": groupes_doublons(activites),
        "recapitulatif": recapitulatif(p, db),
    }


@app.put("/api/projets/{projet_id}")
def maj_projet(projet_id: int, corps: schemas.ProjetIn,
               p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    doublon = db.query(models.Projet).filter(models.Projet.code == corps.code,
                                             models.Projet.id != projet_id).first()
    if doublon:
        raise HTTPException(409, "Un autre projet porte déjà ce code.")
    donnees = corps.model_dump()
    artefacts = donnees.pop("artefacts_tableau", None)
    for champ, valeur in donnees.items():
        setattr(p.projet, champ, valeur)
    if artefacts is not None:
        connus = {code for code, _ in models.ARTEFACTS}
        retenus = [c.strip() for c in artefacts.split(",") if c.strip() in connus]
        p.projet.artefacts_tableau = ",".join(retenus)
    db.commit()
    return s_projet(p.projet, p.role)


# --------------------------------------------------------------------------
# référentiels
# --------------------------------------------------------------------------

def _code_unique(db, modele, projet_id, libelle):
    base = libelle.lower().replace(" ", "-")[:34] or "item"
    code, i = base, 1
    while db.query(modele).filter_by(projet_id=projet_id, code=code).first():
        code = f"{base}-{i}"
        i += 1
    return code


@app.post("/api/projets/{projet_id}/types")
def creer_type(projet_id: int, corps: schemas.TypeTacheIn,
               p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    t = models.TypeTache(projet_id=projet_id,
                         code=_code_unique(db, models.TypeTache, projet_id, corps.libelle),
                         libelle=corps.libelle, couleur=corps.couleur,
                         ordre=db.query(models.TypeTache).filter_by(projet_id=projet_id).count())
    db.add(t)
    db.commit()
    return s_type(t)


@app.put("/api/projets/{projet_id}/types/{type_id}")
def maj_type(projet_id: int, type_id: int, corps: schemas.TypeTacheIn,
             p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    t = verifier_projet(p, db.get(models.TypeTache, type_id), "Ce type de tâche")
    t.libelle, t.couleur = corps.libelle, corps.couleur
    db.commit()
    return s_type(t)


@app.delete("/api/projets/{projet_id}/types/{type_id}")
def suppr_type(projet_id: int, type_id: int,
               p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    t = verifier_projet(p, db.get(models.TypeTache, type_id), "Ce type de tâche")
    n = db.query(models.Activite).filter_by(type_tache_id=type_id).count()
    if n:
        raise HTTPException(409, f"{n} ligne(s) de temps sont rattachées à ce type.")
    db.delete(t)
    db.commit()
    return {"supprime": True}


@app.post("/api/projets/{projet_id}/categories")
def creer_categorie(projet_id: int, corps: schemas.CategorieIn,
                    p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    c = models.CategorieDepense(
        projet_id=projet_id,
        code=_code_unique(db, models.CategorieDepense, projet_id, corps.libelle),
        libelle=corps.libelle, couleur=corps.couleur,
        ordre=db.query(models.CategorieDepense).filter_by(projet_id=projet_id).count())
    db.add(c)
    db.commit()
    return s_type(c)


@app.put("/api/projets/{projet_id}/categories/{cat_id}")
def maj_categorie(projet_id: int, cat_id: int, corps: schemas.CategorieIn,
                  p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    c = verifier_projet(p, db.get(models.CategorieDepense, cat_id), "Cette catégorie")
    c.libelle, c.couleur = corps.libelle, corps.couleur
    db.commit()
    return s_type(c)


@app.delete("/api/projets/{projet_id}/categories/{cat_id}")
def suppr_categorie(projet_id: int, cat_id: int,
                    p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    c = verifier_projet(p, db.get(models.CategorieDepense, cat_id), "Cette catégorie")
    n = db.query(models.Depense).filter_by(categorie_id=cat_id).count()
    if n:
        raise HTTPException(409, f"{n} dépense(s) sont rattachées à cette catégorie.")
    db.delete(c)
    db.commit()
    return {"supprime": True}


# --------------------------------------------------------------------------
# personnes
# --------------------------------------------------------------------------

@app.post("/api/projets/{projet_id}/personnes")
def creer_personne(projet_id: int, corps: schemas.PersonneIn,
                   p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    if db.query(models.Personne).filter_by(projet_id=projet_id, nom=corps.nom).first():
        raise HTTPException(409, "Une personne porte déjà ce nom dans ce projet.")
    x = models.Personne(projet_id=projet_id, **corps.model_dump())
    db.add(x)
    db.commit()
    return s_personne(x)


@app.put("/api/projets/{projet_id}/personnes/{personne_id}")
def maj_personne(projet_id: int, personne_id: int, corps: schemas.PersonneIn,
                 p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    x = verifier_projet(p, db.get(models.Personne, personne_id), "Cette personne")
    doublon = db.query(models.Personne).filter(models.Personne.projet_id == projet_id,
                                               models.Personne.nom == corps.nom,
                                               models.Personne.id != personne_id).first()
    if doublon:
        raise HTTPException(409, "Une autre personne porte déjà ce nom dans ce projet.")
    for champ, valeur in corps.model_dump().items():
        setattr(x, champ, valeur)
    db.commit()
    return s_personne(x)


@app.delete("/api/projets/{projet_id}/personnes/{personne_id}")
def suppr_personne(projet_id: int, personne_id: int,
                   p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    x = verifier_projet(p, db.get(models.Personne, personne_id), "Cette personne")
    n = db.query(models.Activite).filter_by(personne_id=personne_id).count()
    if n:
        raise HTTPException(409, f"{n} ligne(s) de temps sont rattachées à {x.nom}.")
    db.query(models.Depense).filter_by(personne_id=personne_id).update({"personne_id": None})
    db.query(models.Acces).filter_by(personne_id=personne_id).update({"personne_id": None})
    db.query(models.Recurrence).filter_by(personne_id=personne_id).delete()
    db.delete(x)
    db.commit()
    return {"supprime": True}


# --------------------------------------------------------------------------
# activités
# --------------------------------------------------------------------------

@app.post("/api/projets/{projet_id}/activites")
def creer_activite(projet_id: int, corps: schemas.ActiviteIn,
                   p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    p.exiger_personne(corps.personne_id)
    verifier_projet(p, db.get(models.Personne, corps.personne_id), "Cette personne")
    verifier_projet(p, db.get(models.TypeTache, corps.type_tache_id), "Ce type de tâche")
    a = models.Activite(projet_id=projet_id, **corps.model_dump())
    db.add(a)
    db.commit()
    return s_activite(a)


@app.put("/api/projets/{projet_id}/activites/{activite_id}")
def maj_activite(projet_id: int, activite_id: int, corps: schemas.ActiviteIn,
                 p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    a = verifier_projet(p, db.get(models.Activite, activite_id), "Cette ligne de temps")
    p.exiger_personne(a.personne_id)
    p.exiger_personne(corps.personne_id)
    for champ, valeur in corps.model_dump().items():
        setattr(a, champ, valeur)
    # Repasser une ligne en durée estimée annule la validation qui la portait.
    if a.statut != "mesure":
        a.valide_le, a.valide_par_id = None, None
    db.commit()
    return s_activite(a)


@app.delete("/api/projets/{projet_id}/activites/{activite_id}")
def suppr_activite(projet_id: int, activite_id: int,
                   p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    a = verifier_projet(p, db.get(models.Activite, activite_id), "Cette ligne de temps")
    p.exiger_personne(a.personne_id)
    db.delete(a)
    db.commit()
    return {"supprime": True}


# --------------------------------------------------------------------------
# validation des durées estimées
# --------------------------------------------------------------------------

def _valider(a: models.Activite, utilisateur: models.Utilisateur, note: str = "") -> None:
    """Une durée estimée validée devient une durée retenue, sans effacer son origine.

    origine_estimee reste vrai pour toujours distinguer, dans les récapitulatifs et les
    exports, ce qui a été mesuré à la source de ce qui a été arbitré après coup.
    """
    a.statut = "mesure"
    a.origine_estimee = True
    a.valide_le = datetime.utcnow()
    a.valide_par_id = utilisateur.id
    if note:
        a.note = (a.note + " " + note).strip() if a.note else note


@app.post("/api/projets/{projet_id}/activites/{activite_id}/valider")
def valider_activite(projet_id: int, activite_id: int,
                     p: securite.Portee = Depends(scope),
                     u: models.Utilisateur = Depends(securite.utilisateur_courant),
                     db: Session = Depends(get_db)):
    p.exiger_pilotage()
    a = verifier_projet(p, db.get(models.Activite, activite_id), "Cette ligne de temps")
    if a.heures <= 0:
        raise HTTPException(409, "Une ligne sans durée ne peut pas être validée : "
                                 "renseignez d'abord la durée réellement passée.")
    _valider(a, u)
    db.commit()
    return s_activite(a)


@app.post("/api/projets/{projet_id}/activites/{activite_id}/devalider")
def devalider_activite(projet_id: int, activite_id: int,
                       p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_pilotage()
    a = verifier_projet(p, db.get(models.Activite, activite_id), "Cette ligne de temps")
    if not a.validee:
        raise HTTPException(409, "Cette ligne n'a pas été validée.")
    a.statut = "estime"
    a.origine_estimee = False
    a.valide_le, a.valide_par_id = None, None
    db.commit()
    return s_activite(a)


@app.post("/api/projets/{projet_id}/activites/valider")
def valider_en_masse(projet_id: int, corps: schemas.ValidationEnMasse,
                     p: securite.Portee = Depends(scope),
                     u: models.Utilisateur = Depends(securite.utilisateur_courant),
                     db: Session = Depends(get_db)):
    """Valide en une fois toutes les durées estimées d'une sélection.

    Les lignes sans durée sont écartées et signalées plutôt que validées à vide.
    """
    p.exiger_pilotage()
    q = db.query(models.Activite).filter(models.Activite.projet_id == projet_id,
                                         models.Activite.statut == "estime")
    if corps.ids:
        q = q.filter(models.Activite.id.in_(corps.ids))
    else:
        if corps.type_tache_id:
            q = q.filter(models.Activite.type_tache_id == corps.type_tache_id)
        if corps.personne_id:
            q = q.filter(models.Activite.personne_id == corps.personne_id)
        if corps.recurrence_id:
            q = q.filter(models.Activite.recurrence_id == corps.recurrence_id)
        if corps.date_debut:
            q = q.filter(models.Activite.date >= corps.date_debut)
        if corps.date_fin:
            q = q.filter(models.Activite.date <= corps.date_fin)

    candidates = q.all()
    validees, ecartees = 0, []
    for a in candidates:
        if a.heures <= 0:
            ecartees.append(f"{a.libelle} ({a.date.strftime('%d/%m/%Y')})")
            continue
        _valider(a, u, corps.note)
        validees += 1
    db.commit()
    return {"validees": validees, "ecartees": ecartees,
            "examinees": len(candidates)}


@app.post("/api/projets/{projet_id}/activites/arbitrer-doublon")
def arbitrer_doublon(projet_id: int, corps: schemas.ArbitrageDoublon,
                     p: securite.Portee = Depends(scope),
                     u: models.Utilisateur = Depends(securite.utilisateur_courant),
                     db: Session = Depends(get_db)):
    """Tranche un recouvrement en retenant une seule ligne.

    Neutraliser vaut mieux que supprimer : la ligne écartée reste au dossier avec
    zéro pour cent d'imputation, ce qui garde la trace de la réunion tout en la
    retirant du total. La suppression reste possible quand la ligne est une simple
    scorie d'agenda.
    """
    p.exiger_ecriture()
    if corps.action not in ("neutraliser", "supprimer"):
        raise HTTPException(422, "Action inconnue.")
    garder = verifier_projet(p, db.get(models.Activite, corps.garder_id), "La ligne retenue")
    p.exiger_personne(garder.personne_id)

    ecartees = []
    for identifiant in corps.ids:
        if identifiant == corps.garder_id:
            continue
        a = verifier_projet(p, db.get(models.Activite, identifiant), "Cette ligne de temps")
        p.exiger_personne(a.personne_id)
        ecartees.append(a)

    trace = (f"Recouvrement du {garder.date.strftime('%d/%m/%Y')} arbitré le "
             f"{datetime.utcnow().strftime('%d/%m/%Y')} par {u.nom or u.email} : "
             f"« {garder.libelle} » est la ligne retenue.")
    for a in ecartees:
        if corps.action == "supprimer":
            db.delete(a)
        else:
            a.part_imputable = 0.0
            a.note = f"{a.note or ''} {trace}".strip()
    if ecartees and corps.action == "neutraliser":
        garder.note = f"{garder.note or ''} {trace}".strip()
    db.commit()
    return {"retenue": corps.garder_id, "ecartees": len(ecartees), "action": corps.action}


# --------------------------------------------------------------------------
# dépenses
# --------------------------------------------------------------------------

@app.post("/api/projets/{projet_id}/depenses")
def creer_depense(projet_id: int, corps: schemas.DepenseIn,
                  p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    if corps.personne_id:
        p.exiger_personne(corps.personne_id)
    verifier_projet(p, db.get(models.CategorieDepense, corps.categorie_id), "Cette catégorie")
    d = models.Depense(projet_id=projet_id, **corps.model_dump())
    db.add(d)
    db.commit()
    return s_depense(d)


@app.put("/api/projets/{projet_id}/depenses/{depense_id}")
def maj_depense(projet_id: int, depense_id: int, corps: schemas.DepenseIn,
                p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    d = verifier_projet(p, db.get(models.Depense, depense_id), "Cette dépense")
    if p.restreint and d.personne_id != p.personne_id:
        raise HTTPException(403, "Cette dépense ne relève pas de votre périmètre.")
    for champ, valeur in corps.model_dump().items():
        setattr(d, champ, valeur)
    db.commit()
    return s_depense(d)


@app.delete("/api/projets/{projet_id}/depenses/{depense_id}")
def suppr_depense(projet_id: int, depense_id: int,
                  p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    d = verifier_projet(p, db.get(models.Depense, depense_id), "Cette dépense")
    if p.restreint and d.personne_id != p.personne_id:
        raise HTTPException(403, "Cette dépense ne relève pas de votre périmètre.")
    db.delete(d)
    db.commit()
    return {"supprime": True}


@app.get("/api/projets/{projet_id}/activites/a-valider")
def a_valider(projet_id: int, p: securite.Portee = Depends(scope),
              db: Session = Depends(get_db)):
    """Inventaire de ce qui attend une validation, groupé par acteur et par mois."""
    lignes = [a for a in activites_visibles(p, db) if a.statut == "estime"]
    par_personne = defaultdict(lambda: {"n": 0, "heures": 0.0})
    par_mois = defaultdict(lambda: {"n": 0, "heures": 0.0})
    for a in lignes:
        par_personne[a.personne_id]["n"] += 1
        par_personne[a.personne_id]["heures"] += a.heures_imputees
        cle = a.date.strftime("%Y-%m")
        par_mois[cle]["n"] += 1
        par_mois[cle]["heures"] += a.heures_imputees
    noms = {x.id: x.nom for x in db.query(models.Personne).filter_by(projet_id=projet_id).all()}
    return {
        "total": len(lignes),
        "heures": round(sum(a.heures_imputees for a in lignes), 2),
        "par_personne": [{"personne_id": pid, "nom": noms.get(pid, ""), "n": v["n"],
                          "heures": round(v["heures"], 2)}
                         for pid, v in sorted(par_personne.items(), key=lambda kv: -kv[1]["heures"])],
        "par_mois": [{"mois": m, "n": v["n"], "heures": round(v["heures"], 2)}
                     for m, v in sorted(par_mois.items())],
    }


# --------------------------------------------------------------------------
# récurrences
# --------------------------------------------------------------------------

@app.post("/api/projets/{projet_id}/recurrences")
def creer_recurrence(projet_id: int, corps: schemas.RecurrenceIn,
                     p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    p.exiger_personne(corps.personne_id)
    verifier_projet(p, db.get(models.Personne, corps.personne_id), "Cette personne")
    r = models.Recurrence(projet_id=projet_id, **corps.model_dump())
    db.add(r)
    db.commit()
    cree = seed_data.generer_recurrence(db, r)
    return {"recurrence": s_recurrence(r, cree), "crees": cree}


@app.put("/api/projets/{projet_id}/recurrences/{rec_id}")
def maj_recurrence(projet_id: int, rec_id: int, corps: schemas.RecurrenceIn,
                   p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    r = verifier_projet(p, db.get(models.Recurrence, rec_id), "Cette règle")
    p.exiger_personne(r.personne_id)
    p.exiger_personne(corps.personne_id)
    for champ, valeur in corps.model_dump().items():
        setattr(r, champ, valeur)
    db.commit()
    # Jour, rang, fenêtre et report peuvent tous déplacer les séances : la règle est
    # rejouée intégralement plutôt que rattrapée partiellement.
    db.query(models.Activite).filter_by(recurrence_id=rec_id).delete()
    db.commit()
    cree = seed_data.generer_recurrence(db, r)
    return {"recurrence": s_recurrence(r, cree), "crees": cree}


@app.post("/api/projets/{projet_id}/recurrences/{rec_id}/generer")
def generer(projet_id: int, rec_id: int,
            p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    r = verifier_projet(p, db.get(models.Recurrence, rec_id), "Cette règle")
    p.exiger_personne(r.personne_id)
    cree = seed_data.generer_recurrence(db, r)
    total = db.query(models.Activite).filter_by(recurrence_id=rec_id).count()
    return {"crees": cree, "occurrences": total}


@app.delete("/api/projets/{projet_id}/recurrences/{rec_id}")
def suppr_recurrence(projet_id: int, rec_id: int, supprimer_occurrences: bool = False,
                     p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    p.exiger_ecriture()
    r = verifier_projet(p, db.get(models.Recurrence, rec_id), "Cette règle")
    p.exiger_personne(r.personne_id)
    if supprimer_occurrences:
        db.query(models.Activite).filter_by(recurrence_id=rec_id).delete()
    else:
        db.query(models.Activite).filter_by(recurrence_id=rec_id).update({"recurrence_id": None})
    db.delete(r)
    db.commit()
    return {"supprime": True}


# --------------------------------------------------------------------------
# récapitulatif et contrôles
# --------------------------------------------------------------------------

def _chevauche(a, b) -> bool:
    if a.date != b.date or a.personne_id != b.personne_id:
        return False
    if not (a.heure_debut and a.heure_fin and b.heure_debut and b.heure_fin):
        return False
    minutes = lambda t: int(t[:2]) * 60 + int(t[3:5])
    return minutes(a.heure_debut) < minutes(b.heure_fin) and \
        minutes(b.heure_debut) < minutes(a.heure_fin)


def groupes_doublons(activites):
    """Groupes de lignes qui se recouvrent pour une même personne le même jour.

    Deux lignes qui se chevauchent ne peuvent pas être imputées toutes les deux :
    l'une au moins doit être neutralisée, sans quoi le total compte deux fois la
    même heure de travail.
    """
    par_jour = defaultdict(list)
    for a in activites:
        par_jour[(a.date, a.personne_id)].append(a)

    groupes = []
    for (jour, personne_id), lot in sorted(par_jour.items()):
        restants = list(lot)
        while restants:
            courant = [restants.pop(0)]
            change = True
            while change:
                change = False
                for autre in list(restants):
                    if any(_chevauche(autre, membre) for membre in courant):
                        courant.append(autre)
                        restants.remove(autre)
                        change = True
            if len(courant) > 1:
                courant.sort(key=lambda a: (a.heures_imputees, a.id), reverse=True)
                groupes.append({
                    "date": jour.isoformat(),
                    "personne_id": personne_id,
                    "ids": [a.id for a in courant],
                    "heures_cumulees": round(sum(a.heures_imputees for a in courant), 2),
                    "heures_retenues": round(max(a.heures_imputees for a in courant), 2),
                })
    return groupes


def controles(activites, depenses, personnes, projet, masquer_couts=False):
    """Contrôles de cohérence présentés comme points à arbitrer."""
    alertes = []
    noms = {x.id: x.nom for x in personnes}

    vus = set()
    for i, a in enumerate(activites):
        for b in activites[i + 1:]:
            if _chevauche(a, b) and (a.id, b.id) not in vus:
                vus.add((a.id, b.id))
                alertes.append({"type": "chevauchement", "texte":
                    f"Chevauchement horaire le {a.date.strftime('%d/%m/%Y')} pour "
                    f"{noms.get(a.personne_id, '')} entre « {a.libelle} » et « {b.libelle} ». "
                    "Une seule de ces lignes doit être imputée, sauf répartition explicite."})

    mixtes = [a for a in activites if a.mixte and float(a.part_imputable) >= 100]
    if mixtes:
        alertes.append({"type": "mixte", "texte":
            f"{len(mixtes)} session(s) à objet mixte encore imputée(s) à 100 % : "
            + " ; ".join(f"{a.libelle} ({a.date.strftime('%d/%m/%Y')})" for a in mixtes)
            + ". Fixez la part revenant au projet avant transmission."})

    sans_duree = [a for a in activites if a.heures <= 0]
    if sans_duree:
        alertes.append({"type": "duree", "texte":
            f"{len(sans_duree)} ligne(s) sans durée : "
            + " ; ".join(f"{a.libelle} ({a.date.strftime('%d/%m/%Y')})" for a in sans_duree) + "."})

    if not masquer_couts:
        actifs = {a.personne_id for a in activites}
        sans_taux = [x for x in personnes
                     if x.imputable and x.id in actifs and not (x.taux_horaire or 0) > 0]
        if sans_taux and not (projet.taux_defaut or 0) > 0:
            alertes.append({"type": "taux", "texte":
                "Taux horaire manquant pour " + ", ".join(x.nom for x in sans_taux)
                + ". Le coût de main d'œuvre reste nul tant qu'il n'est pas renseigné."})

        dep_vides = [d for d in depenses if d.montant <= 0]
        if dep_vides:
            alertes.append({"type": "depense_vide", "texte":
                f"{len(dep_vides)} dépense(s) sans quantité ni tarif : "
                + " ; ".join(d.libelle for d in dep_vides)
                + ". Reportez les relevés de consommation puis le tarif applicable."})

        dep_est = [d for d in depenses if d.statut == "estime" and d.montant > 0]
        if dep_est:
            alertes.append({"type": "depense_estimee", "texte":
                f"{len(dep_est)} dépense(s) chiffrée(s) sans justificatif, pour "
                f"{sum(d.montant for d in dep_est):.2f} {projet.devise}."})

    par_jour = defaultdict(list)
    for a in activites:
        par_jour[(a.date, a.personne_id)].append(a)
    collisions = []
    for cle, lot in sorted(par_jour.items()):
        rec = [a for a in lot if a.recurrence_id]
        autres = [a for a in lot if not a.recurrence_id]
        if rec and autres:
            collisions.append(
                f"{cle[0].strftime('%d/%m/%Y')} : « {rec[0].libelle} » coexiste avec "
                + " et ".join(f"« {a.libelle} »" for a in autres))
    if collisions:
        alertes.append({"type": "collision", "texte":
            f"{len(collisions)} journée(s) où une séance récurrente coïncide avec une réunion "
            "déjà tracée. " + " ; ".join(collisions)
            + ". Réduisez la durée de la séance ce jour-là ou retirez-la."})

    sur_ferie = [(a, seed_data.nom_ferie(a.date)) for a in activites if seed_data.nom_ferie(a.date)]
    if sur_ferie:
        alertes.append({"type": "ferie", "texte":
            f"{len(sur_ferie)} ligne(s) tombent un jour férié : "
            + " ; ".join(f"{a.date.strftime('%d/%m/%Y')}, {nom}, « {a.libelle} »"
                         for a, nom in sur_ferie)
            + ". Les séances récurrentes sont reportées automatiquement, mais une réunion "
              "saisie à la main reste à justifier."})

    reportees = [a for a in activites if a.date_theorique and a.date_theorique != a.date]
    if reportees:
        alertes.append({"type": "report", "texte":
            f"{len(reportees)} séance(s) récurrente(s) déplacées vers le premier jour ouvrable "
            "libre : " + " ; ".join(f"{a.date_theorique.strftime('%d/%m/%Y')} vers "
                                    f"{a.date.strftime('%d/%m/%Y')}" for a in reportees)
            + ". Vérifiez que la date retenue correspond à une journée réellement travaillée."})

    en_attente = [a for a in activites if a.statut == "estime" and a.heures > 0]
    if en_attente:
        alertes.append({"type": "a_valider", "texte":
            f"{len(en_attente)} durée(s) estimée(s) attendent une validation, pour "
            f"{sum(a.heures_imputees for a in en_attente):.2f} heures. Le pilotage peut les "
            "valider en masse depuis l'onglet du temps passé."})

    validees = [a for a in activites if a.valide_le]
    if validees:
        valideurs = sorted({(a.valide_par.nom or a.valide_par.email) for a in validees
                            if a.valide_par})
        alertes.append({"type": "validee", "texte":
            f"{len(validees)} ligne(s) retenues comme durées fermes proviennent d'une estimation "
            f"validée, pour {sum(a.heures_imputees for a in validees):.2f} heures"
            + (", par " + ", ".join(valideurs) if valideurs else "")
            + ". Leur origine estimée reste inscrite sur chaque ligne et dans les exports. Une "
              "estimation validée n'est pas un relevé horaire : mentionnez-le au financeur "
              "plutôt que de le laisser découvrir."})

    declaratives = [a for a in activites if a.source == "declaratif"]
    if declaratives:
        alertes.append({"type": "declaratif", "texte":
            f"{len(declaratives)} journée(s) issues d'un régime déclaré et non d'une trace "
            f"d'agenda, pour {sum(a.heures_imputees for a in declaratives):.2f} heures. "
            "Adossez-les à une preuve d'exécution datée."})

    return alertes


def recapitulatif(p: securite.Portee, db: Session) -> dict:
    projet = p.projet
    activites = activites_visibles(p, db)
    depenses = depenses_visibles(p, db)
    personnes = db.query(models.Personne).filter_by(projet_id=projet.id).all()
    types = {t.id: t for t in db.query(models.TypeTache).filter_by(projet_id=projet.id).all()}
    cats = {c.id: c for c in db.query(models.CategorieDepense).filter_by(projet_id=projet.id).all()}
    index = {x.id: x for x in personnes}

    par_type = defaultdict(lambda: {"n": 0, "heures": 0.0, "imputees": 0.0, "cout": 0.0})
    par_personne = defaultdict(lambda: {"n": 0, "imputees": 0.0, "cout": 0.0})
    par_mois = defaultdict(lambda: {"n": 0, "imputees": 0.0, "cout": 0.0, "depenses": 0.0})
    for a in activites:
        par_type[a.type_tache_id]["n"] += 1
        par_type[a.type_tache_id]["heures"] += a.heures
        par_type[a.type_tache_id]["imputees"] += a.heures_imputees
        par_type[a.type_tache_id]["cout"] += a.cout
        par_personne[a.personne_id]["n"] += 1
        par_personne[a.personne_id]["imputees"] += a.heures_imputees
        par_personne[a.personne_id]["cout"] += a.cout
        cle = a.date.strftime("%Y-%m")
        par_mois[cle]["n"] += 1
        par_mois[cle]["imputees"] += a.heures_imputees
        par_mois[cle]["cout"] += a.cout

    par_categorie = defaultdict(lambda: {"n": 0, "montant": 0.0, "justifie": 0.0})
    for d in depenses:
        par_categorie[d.categorie_id]["n"] += 1
        par_categorie[d.categorie_id]["montant"] += d.montant
        if d.statut == "mesure":
            par_categorie[d.categorie_id]["justifie"] += d.montant
        par_mois[d.date.strftime("%Y-%m")]["depenses"] += d.montant

    total_hi = sum(a.heures_imputees for a in activites)
    total_mes = sum(a.heures_imputees for a in activites if a.statut == "mesure")
    total_validees = sum(a.heures_imputees for a in activites if a.valide_le)
    total_source = sum(a.heures_imputees for a in activites if a.mesuree_a_la_source)
    total_estimees = sum(a.heures_imputees for a in activites if a.statut == "estime")
    total_attente = sum(a.heures_imputees for a in activites
                        if a.statut == "estime" and a.heures > 0)
    total_cout = sum(a.cout for a in activites)
    total_dep = sum(d.montant for d in depenses)
    hj = projet.heures_jour or 7.0
    arrondi = lambda v: round(v, 2) if isinstance(v, float) else v

    return {
        "totaux": {
            "heures": round(sum(a.heures for a in activites), 2),
            "imputees": round(total_hi, 2),
            "jours_homme": round(total_hi / hj, 2),
            "part_mesuree": round(total_mes / total_hi * 100, 1) if total_hi else 0.0,
            "heures_validees": round(total_validees, 2),
            "heures_mesurees_source": round(total_source, 2),
            "heures_estimees": round(total_estimees, 2),
            "heures_a_valider": round(total_attente, 2),
            "lignes_a_valider": len([a for a in activites
                                     if a.statut == "estime" and a.heures > 0]),
            "cout_main_oeuvre": round(total_cout, 2),
            "depenses": round(total_dep, 2),
            "depenses_justifiees": round(
                sum(d.montant for d in depenses if d.statut == "mesure"), 2),
            "total": round(total_cout + total_dep, 2),
            "acteurs": len(par_personne),
        },
        "par_type": [{"id": tid, "libelle": types[tid].libelle, "couleur": types[tid].couleur,
                      **{k: arrondi(v) for k, v in vals.items()}}
                     for tid, vals in sorted(par_type.items(), key=lambda kv: -kv[1]["imputees"])
                     if tid in types],
        "par_personne": [{"id": pid, "nom": index[pid].nom,
                          "organisation": index[pid].organisation or "",
                          "imputable": index[pid].imputable,
                          "jours_homme": round(vals["imputees"] / hj, 2),
                          **{k: arrondi(v) for k, v in vals.items()}}
                         for pid, vals in sorted(par_personne.items(),
                                                 key=lambda kv: -kv[1]["imputees"]) if pid in index],
        "par_categorie": [{"id": cid, "libelle": cats[cid].libelle, "couleur": cats[cid].couleur,
                           **{k: arrondi(v) for k, v in vals.items()}}
                          for cid, vals in sorted(par_categorie.items(),
                                                  key=lambda kv: -kv[1]["montant"]) if cid in cats],
        "par_mois": [{"mois": mois, **{k: arrondi(v) for k, v in vals.items()}}
                     for mois, vals in sorted(par_mois.items())],
        "alertes": controles(activites, depenses, personnes, projet, p.restreint),
    }


@app.get("/api/projets/{projet_id}/recapitulatif")
def api_recapitulatif(projet_id: int, p: securite.Portee = Depends(scope),
                      db: Session = Depends(get_db)):
    return recapitulatif(p, db)


# --------------------------------------------------------------------------
# exports
# --------------------------------------------------------------------------

def _csv(lignes, nom) -> Response:
    tampon = io.StringIO()
    csv.writer(tampon, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(lignes)
    return Response(content=("\ufeff" + tampon.getvalue()).encode("utf-8"),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


def _fr(v: float, n: int = 2) -> str:
    return f"{v:.{n}f}".replace(".", ",")


@app.get("/api/projets/{projet_id}/export/temps.csv")
def export_temps(projet_id: int, p: securite.Portee = Depends(scope),
                 db: Session = Depends(get_db)):
    types = {t.id: t.libelle for t in db.query(models.TypeTache)
             .filter_by(projet_id=projet_id).all()}
    lignes = [["Date", "Début", "Fin", "Libellé", "Type de tâche", "Personne", "Organisation",
               "Livrable", "Durée (h)", "Part imputable (%)", "Heures imputées", "Taux horaire",
               "Coût", "Source", "Statut durée", "Origine estimée", "Validée le", "Validée par",
               "Objet mixte", "Récurrente", "Date théorique", "Reportée", "Note"]]
    for a in sorted(activites_visibles(p, db), key=lambda x: x.date):
        taux = a.personne.taux_horaire or p.projet.taux_defaut or 0
        lignes.append([
            a.date.strftime("%d/%m/%Y"), a.heure_debut or "", a.heure_fin or "", a.libelle,
            types.get(a.type_tache_id, ""), a.personne.nom, a.personne.organisation or "",
            a.livrable or "", _fr(a.heures), _fr(a.part_imputable, 0), _fr(a.heures_imputees),
            _fr(taux), _fr(a.cout), a.source, "mesurée" if a.statut == "mesure" else "estimée",
            "oui" if a.origine_estimee else "non",
            a.valide_le.strftime("%d/%m/%Y %H:%M") if a.valide_le else "",
            (a.valide_par.nom or a.valide_par.email) if a.valide_par else "",
            "oui" if a.mixte else "non", "oui" if a.recurrence_id else "non",
            a.date_theorique.strftime("%d/%m/%Y") if a.date_theorique else "",
            "oui" if (a.date_theorique and a.date_theorique != a.date) else "non", a.note or ""])
    return _csv(lignes, f"{p.projet.code}-temps.csv")


@app.get("/api/projets/{projet_id}/export/depenses.csv")
def export_depenses(projet_id: int, p: securite.Portee = Depends(scope),
                    db: Session = Depends(get_db)):
    cats = {c.id: c.libelle for c in db.query(models.CategorieDepense)
            .filter_by(projet_id=projet_id).all()}
    noms = {x.id: x.nom for x in db.query(models.Personne).filter_by(projet_id=projet_id).all()}
    lignes = [["Date", "Catégorie", "Élément technique", "Engagée par", "Quantité", "Unité",
               "Coût unitaire", "Montant", "Statut", "Justificatif", "Note"]]
    for d in sorted(depenses_visibles(p, db), key=lambda x: x.date):
        lignes.append([d.date.strftime("%d/%m/%Y"), cats.get(d.categorie_id, ""), d.libelle,
                       noms.get(d.personne_id, ""), _fr(d.quantite), d.unite or "",
                       _fr(d.cout_unitaire, 4), _fr(d.montant),
                       "justifiée" if d.statut == "mesure" else "estimée", d.reference or "",
                       d.note or ""])
    return _csv(lignes, f"{p.projet.code}-depenses.csv")


@app.get("/api/projets/{projet_id}/export/synthese.csv")
def export_synthese(projet_id: int, p: securite.Portee = Depends(scope),
                    db: Session = Depends(get_db)):
    projet, r = p.projet, recapitulatif(p, db)
    lignes = [["Récapitulatif des temps et dépenses", projet.intitule],
              ["Financeur", projet.financeur or ""],
              ["Période", f"{projet.date_debut.strftime('%d/%m/%Y')} au "
                          f"{projet.date_fin.strftime('%d/%m/%Y')}"],
              ["Devise", projet.devise], ["Heures par jour-homme", _fr(projet.heures_jour, 1)], [],
              ["Type de tâche", "Lignes", "Heures", "Heures imputées", "Coût"]]
    for t in r["par_type"]:
        lignes.append([t["libelle"], t["n"], _fr(t["heures"]), _fr(t["imputees"]), _fr(t["cout"])])
    lignes += [[], ["Acteur", "Organisation", "Lignes", "Heures imputées", "Jours-homme", "Coût"]]
    for x in r["par_personne"]:
        lignes.append([x["nom"], x["organisation"], x["n"], _fr(x["imputees"]),
                       _fr(x["jours_homme"]), _fr(x["cout"])])
    lignes += [[], ["Mois", "Lignes", "Heures imputées", "Main d'œuvre", "Dépenses techniques"]]
    for m in r["par_mois"]:
        lignes.append([m["mois"], m["n"], _fr(m["imputees"]), _fr(m["cout"]), _fr(m["depenses"])])
    lignes += [[], ["Catégorie de dépense", "Lignes", "Montant", "Dont justifié"]]
    for c in r["par_categorie"]:
        lignes.append([c["libelle"], c["n"], _fr(c["montant"]), _fr(c["justifie"])])
    t = r["totaux"]
    lignes += [[], ["Heures imputées", _fr(t["imputees"])], ["Jours-homme", _fr(t["jours_homme"])],
               ["Part adossée à une durée retenue (%)", _fr(t["part_mesuree"], 1)],
               ["Heures mesurées à la source", _fr(t["heures_mesurees_source"])],
               ["Heures retenues par validation", _fr(t["heures_validees"])],
               ["Heures encore estimées", _fr(t["heures_estimees"])],
               ["Coût de main d'œuvre", _fr(t["cout_main_oeuvre"])],
               ["Dépenses techniques", _fr(t["depenses"])],
               ["Dont justifiées par une pièce", _fr(t["depenses_justifiees"])],
               ["Total à date", _fr(t["total"])], [], ["Points à arbitrer"]]
    for a in r["alertes"]:
        lignes.append([a["texte"]])
    return _csv(lignes, f"{p.projet.code}-synthese.csv")


def _donnees_tableau(p: securite.Portee, db: Session, personne_id=None):
    activites = activites_visibles(p, db)
    depenses = depenses_visibles(p, db)
    if personne_id:
        activites = [a for a in activites if a.personne_id == personne_id]
        depenses = [d for d in depenses if d.personne_id == personne_id]
    personnes = db.query(models.Personne).filter_by(projet_id=p.projet.id).all()
    return {
        "activites": activites,
        "depenses": depenses,
        "types": db.query(models.TypeTache).filter_by(projet_id=p.projet.id)
                   .order_by(models.TypeTache.ordre).all(),
        "categories": db.query(models.CategorieDepense).filter_by(projet_id=p.projet.id).all(),
        "noms_personnes": {x.id: {"nom": x.nom, "organisation": x.organisation or "",
                                  "taux": x.taux_horaire, "imputable": x.imputable}
                           for x in personnes},
        "personnes": personnes,
    }


def _artefacts(projet, demande=None):
    """Artefacts retenus : le paramètre d'URL prime sur le réglage du projet."""
    connus = [code for code, _ in models.ARTEFACTS]
    source = demande if demande is not None else (projet.artefacts_tableau or models.ARTEFACTS_DEFAUT)
    retenus = [c.strip() for c in source.split(",") if c.strip() in connus]
    return retenus or connus


@app.get("/api/projets/{projet_id}/artefacts")
def liste_artefacts(projet_id: int, p: securite.Portee = Depends(scope)):
    return {"catalogue": [{"code": c, "libelle": l} for c, l in models.ARTEFACTS],
            "retenus": _artefacts(p.projet)}


@app.get("/api/projets/{projet_id}/export/tableau-de-bord.html")
def export_tableau(projet_id: int, personne_id: int = Query(default=None),
                   artefacts: str = Query(default=None),
                   p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    if p.restreint:
        personne_id = p.personne_id
    personne = None
    if personne_id:
        personne = verifier_projet(p, db.get(models.Personne, personne_id), "Cette personne")
    donnees = _donnees_tableau(p, db, personne_id)
    alertes = controles(donnees["activites"], donnees["depenses"], donnees["personnes"],
                        p.projet, p.restreint)
    html = tableau_bord.construire(p.projet, donnees, personne, alertes, p.restreint,
                                   _artefacts(p.projet, artefacts))
    nom = f"{p.projet.code}-tableau-de-bord"
    if personne:
        nom += "-" + personne.nom.lower().replace(" ", "-")
    return HTMLResponse(html, headers={"Content-Disposition": f'attachment; filename="{nom}.html"'})


@app.get("/api/projets/{projet_id}/export/tableaux-de-bord.zip")
def export_liasse(projet_id: int, artefacts: str = Query(default=None),
                  p: securite.Portee = Depends(scope), db: Session = Depends(get_db)):
    """Liasse destinée au financeur : un tableau par acteur, plus le consolidé."""
    p.exiger_pilotage()
    retenus = _artefacts(p.projet, artefacts)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        donnees = _donnees_tableau(p, db)
        alertes = controles(donnees["activites"], donnees["depenses"], donnees["personnes"],
                            p.projet, False)
        archive.writestr(f"{p.projet.code}-consolide.html",
                         tableau_bord.construire(p.projet, donnees, None, alertes, False, retenus))
        actifs = {a.personne_id for a in donnees["activites"]}
        for personne in donnees["personnes"]:
            if personne.id not in actifs:
                continue
            d = _donnees_tableau(p, db, personne.id)
            al = controles(d["activites"], d["depenses"], d["personnes"], p.projet, False)
            nom = personne.nom.lower().replace(" ", "-").replace("/", "-")
            archive.writestr(f"individuels/{nom}.html",
                             tableau_bord.construire(p.projet, d, personne, al, False, retenus))
    tampon.seek(0)
    return Response(tampon.read(), media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="{p.projet.code}-tableaux-de-bord.zip"'})


# --------------------------------------------------------------------------
# administration
# --------------------------------------------------------------------------

@app.get("/api/admin/etat")
def admin_etat(u: models.Utilisateur = Depends(securite.administrateur),
               db: Session = Depends(get_db)):
    utilisateurs = []
    for x in db.query(models.Utilisateur).order_by(models.Utilisateur.email).all():
        acces = [{"id": a.id, "projet_id": a.projet_id,
                  "projet": a.projet.intitule if a.projet else "",
                  "role": a.role, "personne_id": a.personne_id,
                  "personne": a.personne.nom if a.personne else None}
                 for a in x.acces]
        utilisateurs.append(s_utilisateur(x, acces))

    projets = []
    for pr in db.query(models.Projet).order_by(models.Projet.intitule).all():
        activites = db.query(models.Activite).options(joinedload(models.Activite.personne)) \
            .filter_by(projet_id=pr.id).all()
        depenses = db.query(models.Depense).filter_by(projet_id=pr.id).all()
        hi = sum(a.heures_imputees for a in activites)
        cout = sum(a.cout for a in activites)
        montant = sum(d.montant for d in depenses)
        projets.append({
            **s_projet(pr),
            "personnes": [s_personne(x) for x in db.query(models.Personne)
                          .filter_by(projet_id=pr.id).order_by(models.Personne.nom).all()],
            "synthese": {
                "lignes": len(activites), "imputees": round(hi, 2),
                "jours_homme": round(hi / (pr.heures_jour or 7.0), 2),
                "cout": round(cout, 2), "depenses": round(montant, 2),
                "total": round(cout + montant, 2),
                "acteurs": len({a.personne_id for a in activites}),
                "comptes": len(pr.acces),
            },
        })
    return {"utilisateurs": utilisateurs, "projets": projets, "roles": list(models.ROLES_PROJET)}


@app.post("/api/admin/utilisateurs")
def creer_utilisateur(corps: schemas.UtilisateurIn,
                      u: models.Utilisateur = Depends(securite.administrateur),
                      db: Session = Depends(get_db)):
    email = corps.email.strip().lower()
    if db.query(models.Utilisateur).filter_by(email=email).first():
        raise HTTPException(409, "Un compte existe déjà avec cette adresse.")
    provisoire = securite.mot_de_passe_provisoire()
    x = models.Utilisateur(email=email, nom=corps.nom, mot_de_passe=securite.hacher(provisoire),
                           role_global=corps.role_global, actif=corps.actif, doit_changer=True)
    db.add(x)
    db.commit()
    return {"utilisateur": s_utilisateur(x), "mot_de_passe_provisoire": provisoire}


@app.put("/api/admin/utilisateurs/{uid}")
def maj_utilisateur(uid: int, corps: schemas.UtilisateurIn,
                    u: models.Utilisateur = Depends(securite.administrateur),
                    db: Session = Depends(get_db)):
    x = db.get(models.Utilisateur, uid)
    if not x:
        raise HTTPException(404, "Compte introuvable.")
    email = corps.email.strip().lower()
    doublon = db.query(models.Utilisateur).filter(models.Utilisateur.email == email,
                                                  models.Utilisateur.id != uid).first()
    if doublon:
        raise HTTPException(409, "Un autre compte utilise déjà cette adresse.")
    if x.id == u.id and (corps.role_global != models.ADMIN or not corps.actif):
        raise HTTPException(409, "Vous ne pouvez pas retirer vos propres droits d'administration.")
    x.email, x.nom, x.role_global, x.actif = email, corps.nom, corps.role_global, corps.actif
    db.commit()
    return s_utilisateur(x)


@app.post("/api/admin/utilisateurs/{uid}/mot-de-passe")
def reinitialiser_mot_de_passe(uid: int, u: models.Utilisateur = Depends(securite.administrateur),
                               db: Session = Depends(get_db)):
    x = db.get(models.Utilisateur, uid)
    if not x:
        raise HTTPException(404, "Compte introuvable.")
    provisoire = securite.mot_de_passe_provisoire()
    x.mot_de_passe = securite.hacher(provisoire)
    x.doit_changer = True
    db.commit()
    return {"mot_de_passe_provisoire": provisoire}


@app.delete("/api/admin/utilisateurs/{uid}")
def suppr_utilisateur(uid: int, u: models.Utilisateur = Depends(securite.administrateur),
                      db: Session = Depends(get_db)):
    if uid == u.id:
        raise HTTPException(409, "Vous ne pouvez pas supprimer votre propre compte.")
    x = db.get(models.Utilisateur, uid)
    if not x:
        raise HTTPException(404, "Compte introuvable.")
    db.delete(x)
    db.commit()
    return {"supprime": True}


@app.post("/api/admin/projets")
def creer_projet(corps: schemas.ProjetIn, u: models.Utilisateur = Depends(securite.administrateur),
                 db: Session = Depends(get_db)):
    if db.query(models.Projet).filter_by(code=corps.code).first():
        raise HTTPException(409, "Un projet porte déjà ce code.")
    pr = models.Projet(**corps.model_dump())
    db.add(pr)
    db.commit()
    seed_data.referentiel_vierge(db, pr)
    db.add(models.Acces(utilisateur_id=u.id, projet_id=pr.id, role=models.GESTIONNAIRE))
    db.commit()
    return s_projet(pr)


@app.delete("/api/admin/projets/{pid}")
def suppr_projet(pid: int, u: models.Utilisateur = Depends(securite.administrateur),
                 db: Session = Depends(get_db)):
    pr = db.get(models.Projet, pid)
    if not pr:
        raise HTTPException(404, "Projet introuvable.")
    db.delete(pr)
    db.commit()
    return {"supprime": True}


@app.post("/api/admin/acces")
def accorder_acces(corps: schemas.AccesIn, u: models.Utilisateur = Depends(securite.administrateur),
                   db: Session = Depends(get_db)):
    if corps.role not in models.ROLES_PROJET:
        raise HTTPException(422, "Rôle inconnu.")
    if not db.get(models.Utilisateur, corps.utilisateur_id):
        raise HTTPException(404, "Compte introuvable.")
    if not db.get(models.Projet, corps.projet_id):
        raise HTTPException(404, "Projet introuvable.")
    if corps.personne_id:
        personne = db.get(models.Personne, corps.personne_id)
        if not personne or personne.projet_id != corps.projet_id:
            raise HTTPException(409, "Cette personne n'appartient pas au projet visé.")
    if corps.role == models.CONTRIBUTEUR and not corps.personne_id:
        raise HTTPException(409, "Un contributeur doit être rattaché à une personne du projet, "
                                 "sans quoi il ne verrait aucune ligne.")
    a = db.query(models.Acces).filter_by(utilisateur_id=corps.utilisateur_id,
                                         projet_id=corps.projet_id).first()
    if a:
        a.role, a.personne_id = corps.role, corps.personne_id
    else:
        a = models.Acces(**corps.model_dump())
        db.add(a)
    db.commit()
    return {"id": a.id, "role": a.role, "personne_id": a.personne_id}


@app.delete("/api/admin/acces/{aid}")
def retirer_acces(aid: int, u: models.Utilisateur = Depends(securite.administrateur),
                  db: Session = Depends(get_db)):
    a = db.get(models.Acces, aid)
    if not a:
        raise HTTPException(404, "Accès introuvable.")
    db.delete(a)
    db.commit()
    return {"supprime": True}


@app.post("/api/admin/projets/{pid}/reinitialiser")
def reinitialiser_projet(pid: int, u: models.Utilisateur = Depends(securite.administrateur),
                         db: Session = Depends(get_db)):
    if os.getenv("AUTORISER_REINIT", "1") != "1":
        raise HTTPException(403, "Réinitialisation désactivée sur cet environnement.")
    pr = db.get(models.Projet, pid)
    if not pr:
        raise HTTPException(404, "Projet introuvable.")
    seed_data.reinitialiser_projet(db, pr)
    return {"reinitialise": True}


@app.get("/api/sante")
def sante():
    return {"statut": "ok"}


# --------------------------------------------------------------------------
# interface
# --------------------------------------------------------------------------

@app.get("/")
def racine():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
