"""Jeu de données initial, moteur de récurrence et amorçage multi-projet.

Le contenu métier reconstitue le projet DEXTER4LLM à partir de l'agenda et des
fils Teams. Les quantités et tarifs des dépenses restent nuls : ils doivent venir
des relevés réels et ne sont pas estimés ici.
"""

import calendar
import os
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import models, securite

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
RANGS = {1: "premier", 2: "deuxième", 3: "troisième", 4: "quatrième", -1: "dernier"}

TYPES = [
    ("gouv", "Comité de pilotage et de coordination", "#0073EA"),
    ("revue", "Revue de dataset géologique", "#00C875"),
    ("bilat", "Réunion bilatérale et point d'équipe", "#A25DDC"),
    ("travail", "Session de travail et de recherche", "#FDAB3D"),
    ("test", "Tests et expérimentation de modèles", "#E2445C"),
    ("livrable", "Production de livrables", "#00C4C4"),
    ("redaction", "Rédaction scientifique", "#5559DF"),
    ("admin", "Coordination et montage", "#7E8DA3"),
]

CATEGORIES = [
    ("calcul", "Calcul GPU", "#E2445C"),
    ("api", "Appels d'API", "#0073EA"),
    ("stockage", "Stockage", "#00C875"),
    ("licence", "Licences et abonnements", "#FDAB3D"),
    ("soustraitance", "Sous-traitance", "#A25DDC"),
    ("materiel", "Matériel", "#7E8DA3"),
]

PERSONNES = [
    ("GANS COMBE Caroline", "ECE Paris / Omnes Education", "Lead Lot 3", True, "Titulaire du suivi"),
    ("BHUYAN Bikram Pratim", "ECE Paris / Omnes Education", "Chercheur", True, ""),
    ("MEDEIROS MACHADO Guilherme", "ECE Paris / Omnes Education", "Enseignant-chercheur", True, "gmedeirosmachado@ece.fr"),
    ("MAITY S.", "ECE Paris / Omnes Education", "À confirmer", False, "smaity@ece.fr"),
    ("MUSHTAQ U.", "ECE Paris / Omnes Education", "À confirmer", False, "umushtaq@ece.fr"),
    ("LAIFA Bilal", "Orano", "Organisateur des revues dataset", False, ""),
    ("RIGAL Bruno", "Orano", "Participant revues dataset", False, ""),
    ("HEMON Venceslas", "Orano", "Participant revues dataset", False, ""),
    ("DUGUEY Emmanuel", "Orano", "Participant revues dataset", False, ""),
    ("LASHERME Aurélie", "Probayes", "Participante coordination", False, ""),
    ("CABLE Axel", "Dynergie", "Organisateur des comités", False, ""),
    ("STEPHAN François", "À confirmer", "Participant", False, ""),
    ("ABDELJEBAR Yasmina", "À confirmer", "Coordination administrative", False, ""),
    ("TAOUDI Kévin", "À confirmer", "Participant comité", False, ""),
    ("REUS Gérard", "À confirmer", "Participant", False, ""),
    ("KUSZLA Catherine", "À confirmer", "Participante montage", False, ""),
    ("SANJIVY Juliette", "À confirmer", "Participante comité", False, ""),
]

# date, début, fin, libellé, code type, mixte, note
ACTIVITES = [
    ("2026-09-11", "11:00", "12:00", "Échange Projet DEXTERLLM", "bilat", False,
     "Invitation G. Medeiros Machado, avec O. et un autre participant. Fil Teams associé sur LightOnOCR-2 et sur les modèles Gemma 3 4B et Phi-4 Mini 3.8B pour les données sémantiques."),
    ("2026-06-10", "08:30", "12:45", "Comité de pilotage LLM DEXTER", "gouv", True,
     "Invitation Y. Abdeljebar et J. Sanjivy. Recouvrement horaire avec les deux autres entrées du 10 juin, à dédoublonner."),
    ("2026-06-10", "09:00", "12:00", "DEXTER4LLM, comité de coordination n°3", "gouv", True,
     "Invitation Dynergie et F. Stephan, sept autres participants."),
    ("2026-06-10", "09:00", "12:00", "Copil Dexter, entrée personnelle", "gouv", True,
     "Entrée créée par vous, recouvre les deux précédentes."),
    ("2026-06-05", "10:30", "12:30", "Préparation du meeting DexterLLM et de la présentation", "livrable", False,
     "Avec B. P. Bhuyan."),
    ("2026-05-28", "10:30", "12:30", "Meeting point Dexter LLM", "bilat", False,
     "Avec B. P. Bhuyan. Partage de la référence IGRF 13e génération et du produit NOAA associé."),
    ("2026-05-25", "09:00", "17:00", "DEXTER LLM, working paper", "redaction", False,
     "Journée de rédaction du working paper."),
    ("2026-05-20", "11:00", "12:30", "DEXTER", "travail", False, "Objet à préciser."),
    ("2026-05-14", "13:00", "16:00", "Dexter, model testing 2", "test", False, ""),
    ("2026-05-13", "09:00", "16:00", "Dexter, model testing supervised reruns", "test", False, ""),
    ("2026-04-23", "14:00", "15:30", "SDP DEXTER4LLM, revue dataset géologique n°5", "revue", False,
     "Invitation B. Laifa, B. Rigal et dix autres participants."),
    ("2026-04-23", "09:00", "14:00", "Préparation de la réunion data DEXTER et des publications", "travail", False, ""),
    ("2026-04-22", "09:00", "17:00", "DEXTER DB, double model test, SOTA, préparation CEIMIA et SRAIS", "test", True,
     "Journée mixte, part imputable à DEXTER à arbitrer."),
    ("2026-04-16", "09:00", "18:00", "Dexter LLM, modèles état de l'art et modèles fusionnés, plus projet REVEALCOST", "test", True,
     "Journée mixte, part imputable à DEXTER à arbitrer."),
    ("2026-04-14", "09:00", "12:00", "DEXTER4LLM, comité de pilotage n°1 et comité de coordination n°2", "gouv", False,
     "Invitation Dynergie et F. Stephan, cinq autres participants. Compte rendu automatique Leexi mentionné dans le fil."),
    ("2026-04-10", "09:00", "18:00", "Dexter, article Axios, outils IA de formation pour enseignants", "redaction", True,
     "Journée mixte, part imputable à DEXTER à arbitrer."),
    ("2026-04-09", "14:00", "15:30", "CR DEXTER4LLM, revue dataset géologique n°4", "revue", False,
     "Invitation B. Laifa, B. Rigal et dix autres participants."),
    ("2026-04-03", "09:00", "18:00", "Préparation Erasmus+ et article DEXTER", "redaction", True,
     "Journée mixte, part imputable à DEXTER à arbitrer. Coïncide avec le premier vendredi du mois."),
    ("2026-03-25", "14:30", "16:00", "CR DEXTER4LLM, revue dataset géologique n°3", "revue", False,
     "Invitation B. Laifa, B. Rigal et neuf autres participants."),
    ("2026-03-12", "11:00", "13:00", "Meeting Dexter LLM", "bilat", False,
     "Avec B. P. Bhuyan. Travail sur les signatures géologiques de l'uranium et de l'or."),
    ("2026-02-25", "10:30", "12:30", "DexterLLM", "bilat", False, "Invitation B. P. Bhuyan."),
    ("2026-02-19", "14:00", "16:00", "DEXTER4LLM, comité de coordination n°1", "gouv", False,
     "Invitation Dynergie et Probayes, cinq autres participants."),
    ("2026-02-11", "15:00", "16:00", "DEXTER4LLM, revue dataset géologique n°2", "revue", False,
     "Invitation B. Laifa, V. Hemon et neuf autres participants."),
    ("2026-02-04", "14:00", "14:30", "Point DexterLLM", "bilat", False,
     "Avec G. Reus, F. Stephan et un autre participant."),
    ("2026-01-22", "15:00", "16:00", "DEXTER4LLM, revue dataset géologique n°1", "revue", False,
     "Invitation B. Laifa, E. Duguey et six autres participants."),
]

ACTIVITE_MONTAGE = (
    "2025-11-14", "", "", "Rédaction et diffusion de DexterCOMUN, montage du consortium", "admin",
    "Trace Teams du 14 novembre 2025 : envoi de DexterCOMUN 1.pdf à 12h19 et de DexterCOMUN.docx "
    "à 12h28, avec l'arbitrage écartant TW3 comme sous-traitant potentiel. Durée à saisir.",
)

# date, code catégorie, libellé, unité, note
DEPENSES = [
    ("2026-05-13", "calcul", "Colab GPU L4, bras A, fusion TIES et LoRA", "heure-GPU",
     "Bras A, Idefics2-8B et Mistral-7B, calibration par couche."),
    ("2026-05-14", "calcul", "Colab GPU A100 40 Go, bras B, QLoRA Gemma 4 26B-A4B", "heure-GPU",
     "Bras B, configuration confirmée nécessaire, échec mémoire sur L4 même en 4 bits."),
    ("2026-04-22", "calcul", "Entraînement ResNet18, classifieur frugal hiérarchique", "heure-GPU",
     "Corpus uranium Probayes, environ 973 images."),
    ("2026-03-25", "api", "gemini-3.5-flash, benchmark 50 cartes BRGM", "1000 appels API",
     "Modèle de référence du benchmark phase 1."),
    ("2026-03-25", "api", "gpt-4o, benchmark 50 cartes BRGM", "1000 appels API", ""),
    ("2026-03-25", "api", "gemini-2.5-flash, benchmark 50 cartes BRGM", "1000 appels API", ""),
    ("2026-02-11", "stockage", "Google Drive, arborescence Data_Dexter", "Go-mois",
     "Artefacts, points de reprise, CSV d'audit, résultats JSONL."),
]

RECURRENCES = [
    dict(
        libelle="Journée de recherche DEXTER, tests de notebooks et d'hypothèses",
        jour_semaine=0, rang=1,
        date_debut="2025-06-01", date_fin="2026-02-28",
        duree_h=7.0, type_code="travail",
        note="Premier lundi de chaque mois, régime déclaré jusqu'à la bascule de mars 2026.",
    ),
    dict(
        libelle="Journée de recherche DEXTER, tests de notebooks et d'hypothèses",
        jour_semaine=4, rang=1,
        date_debut="2026-03-01", date_fin="2026-09-30",
        duree_h=7.0, type_code="travail",
        note="Premier vendredi de chaque mois, régime déclaré à partir de mars 2026.",
    ),
]


def libelle_regle(jour_semaine: int, rang: int) -> str:
    return f"{RANGS.get(rang, 'premier')} {JOURS[jour_semaine]} du mois"


def occurrences(jour_semaine: int, rang: int, debut: date, fin: date):
    """Dates correspondant à la règle, bornes incluses."""
    resultat = []
    annee, mois = debut.year, debut.month
    while date(annee, mois, 1) <= fin:
        jours = [
            date(annee, mois, j)
            for j in range(1, calendar.monthrange(annee, mois)[1] + 1)
            if date(annee, mois, j).weekday() == jour_semaine
        ]
        if jours:
            cible = jours[-1] if rang == -1 else (jours[rang - 1] if len(jours) >= rang else None)
            if cible and debut <= cible <= fin:
                resultat.append(cible)
        mois += 1
        if mois == 13:
            mois, annee = 1, annee + 1
    return resultat


def paques(annee: int) -> date:
    """Dimanche de Pâques, algorithme grégorien dit anonyme."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(annee, mois, jour + 1)


def feries(annee: int) -> dict:
    """Les onze jours fériés légaux français, fêtes mobiles comprises."""
    p = paques(annee)
    return {
        date(annee, 1, 1): "jour de l'an",
        p + timedelta(days=1): "lundi de Pâques",
        date(annee, 5, 1): "fête du travail",
        date(annee, 5, 8): "victoire 1945",
        p + timedelta(days=39): "ascension",
        p + timedelta(days=50): "lundi de Pentecôte",
        date(annee, 7, 14): "fête nationale",
        date(annee, 8, 15): "assomption",
        date(annee, 11, 1): "toussaint",
        date(annee, 11, 11): "armistice 1918",
        date(annee, 12, 25): "noël",
    }


def nom_ferie(jour: date):
    return feries(jour.year).get(jour)


def _obstacle(jour: date, cible_semaine: int, occupes: dict):
    """Retourne le motif d'indisponibilité du jour, ou None s'il est libre.

    cible_semaine est le jour de semaine visé par la règle : si la règle vise
    elle-même un samedi ou un dimanche, le week-end n'est pas un obstacle.
    """
    if jour.weekday() >= 5 and cible_semaine < 5:
        return "week-end"
    ferie = nom_ferie(jour)
    if ferie:
        return f"jour férié, {ferie}"
    if jour in occupes:
        return f"journée déjà occupée par « {occupes[jour]} »"
    return None


def _jour_suivant(jour: date) -> date:
    """Jour ouvrable suivant : le lendemain, mais un samedi renvoie au lundi."""
    suivant = jour + timedelta(days=1)
    if suivant.weekday() == 5:       # samedi, on passe au premier jour ouvrable
        return suivant + timedelta(days=2)
    if suivant.weekday() == 6:       # dimanche
        return suivant + timedelta(days=1)
    return suivant


def resoudre_date(jour_theorique: date, cible_semaine: int, occupes: dict, reporter: bool):
    """Place la séance au premier jour ouvrable libre à partir de sa date théorique.

    Renvoie la date retenue et le motif du report, vide si la date théorique convient.
    """
    if not reporter:
        return jour_theorique, ""
    jour = jour_theorique
    motif_initial = None
    for _ in range(21):
        motif = _obstacle(jour, cible_semaine, occupes)
        if motif is None:
            if jour == jour_theorique:
                return jour, ""
            return jour, (
                f"Séance du {jour_theorique.strftime('%d/%m/%Y')} reportée au "
                f"{jour.strftime('%d/%m/%Y')} : {motif_initial}."
            )
        if motif_initial is None:
            motif_initial = motif
        jour = _jour_suivant(jour)
    return jour_theorique, (
        f"Aucun jour ouvrable libre dans les trois semaines suivant le "
        f"{jour_theorique.strftime('%d/%m/%Y')} : {motif_initial}. Séance laissée à sa date "
        "théorique, à arbitrer manuellement."
    )


def generer_recurrence(db: Session, recurrence: models.Recurrence) -> int:
    """Matérialise les occurrences manquantes, en reportant les dates indisponibles.

    L'idempotence repose sur date_theorique : une séance déjà reportée n'est pas
    recréée à sa date d'origine lors d'une nouvelle génération.
    """
    if not recurrence.active:
        return 0

    siennes = db.query(models.Activite).filter(
        models.Activite.recurrence_id == recurrence.id
    ).all()
    deja = {a.date_theorique or a.date for a in siennes}

    # toutes les autres lignes de la même personne, qui rendent un jour indisponible
    occupes = {
        a.date: a.libelle
        for a in db.query(models.Activite).filter(
            models.Activite.personne_id == recurrence.personne_id
        ).all()
        if a.recurrence_id != recurrence.id
    }
    for a in siennes:
        occupes.setdefault(a.date, a.libelle)

    cree = 0
    for jour_theorique in occurrences(
        recurrence.jour_semaine, recurrence.rang, recurrence.date_debut, recurrence.date_fin
    ):
        if jour_theorique in deja:
            continue
        jour, motif = resoudre_date(
            jour_theorique, recurrence.jour_semaine, occupes, bool(recurrence.reporter)
        )
        note = recurrence.note or ""
        if motif:
            note = f"{note} {motif}".strip()
        db.add(
            models.Activite(
                projet_id=recurrence.projet_id,
                date=jour,
                date_theorique=jour_theorique,
                heure_debut=recurrence.heure_debut or "",
                heure_fin=recurrence.heure_fin or "",
                duree_h=recurrence.duree_h,
                libelle=recurrence.libelle,
                livrable=recurrence.livrable or "",
                part_imputable=recurrence.part_imputable,
                source=recurrence.source,
                statut=recurrence.statut,
                mixte=False,
                note=note,
                type_tache_id=recurrence.type_tache_id,
                personne_id=recurrence.personne_id,
                recurrence_id=recurrence.id,
            )
        )
        occupes[jour] = recurrence.libelle
        cree += 1
    db.commit()
    return cree



# --------------------------------------------------------------------------
# amorçage
# --------------------------------------------------------------------------

def creer_projet_dexter(db: Session) -> models.Projet:
    """Crée le projet DEXTER4LLM et son contenu reconstitué."""
    projet = models.Projet(
        code="DEXTER4LLM",
        intitule="DEXTER4LLM Lot 3, LLM Engineering",
        financeur="BPI France, France 2030",
        date_debut=date(2025, 6, 1),
        date_fin=date(2026, 9, 30),
        devise="EUR",
        heures_jour=7.0,
        taux_defaut=0.0,
    )
    db.add(projet)
    db.flush()

    types = {}
    for i, (code, libelle, couleur) in enumerate(TYPES):
        t = models.TypeTache(projet_id=projet.id, code=code, libelle=libelle, couleur=couleur, ordre=i)
        db.add(t)
        types[code] = t

    cats = {}
    for i, (code, libelle, couleur) in enumerate(CATEGORIES):
        c = models.CategorieDepense(projet_id=projet.id, code=code, libelle=libelle,
                                    couleur=couleur, ordre=i)
        db.add(c)
        cats[code] = c

    personnes = {}
    for nom, org, role, imputable, note in PERSONNES:
        p = models.Personne(projet_id=projet.id, nom=nom, organisation=org, role=role,
                            taux_horaire=0.0, imputable=imputable, note=note)
        db.add(p)
        personnes[nom] = p

    db.flush()
    caroline = personnes["GANS COMBE Caroline"]

    for d, deb, fin, lib, code, mixte, note in ACTIVITES:
        db.add(models.Activite(
            projet_id=projet.id, date=date.fromisoformat(d), heure_debut=deb, heure_fin=fin,
            duree_h=None, libelle=lib, part_imputable=100.0, source="agenda", statut="mesure",
            mixte=mixte, note=note, type_tache_id=types[code].id, personne_id=caroline.id))

    d, deb, fin, lib, code, note = ACTIVITE_MONTAGE
    db.add(models.Activite(
        projet_id=projet.id, date=date.fromisoformat(d), heure_debut=deb, heure_fin=fin,
        duree_h=0.0, libelle=lib, livrable="Note de montage consortium", part_imputable=100.0,
        source="teams", statut="estime", mixte=False, note=note,
        type_tache_id=types[code].id, personne_id=caroline.id))

    for d, code, lib, unite, note in DEPENSES:
        db.add(models.Depense(
            projet_id=projet.id, date=date.fromisoformat(d), libelle=lib, quantite=0.0,
            unite=unite, cout_unitaire=0.0, statut="estime", reference="", note=note,
            categorie_id=cats[code].id, personne_id=caroline.id))

    regles = []
    for r in RECURRENCES:
        rec = models.Recurrence(
            projet_id=projet.id, libelle=r["libelle"], jour_semaine=r["jour_semaine"],
            rang=r["rang"], date_debut=date.fromisoformat(r["date_debut"]),
            date_fin=date.fromisoformat(r["date_fin"]), duree_h=r["duree_h"],
            part_imputable=100.0, statut="estime", source="declaratif", note=r["note"],
            active=True, reporter=True,
            type_tache_id=types[r["type_code"]].id, personne_id=caroline.id)
        db.add(rec)
        regles.append(rec)

    db.commit()
    for rec in regles:
        generer_recurrence(db, rec)
    return projet


def referentiel_vierge(db: Session, projet: models.Projet) -> None:
    """Types et catégories par défaut pour un projet créé depuis l'administration."""
    for i, (code, libelle, couleur) in enumerate(TYPES):
        db.add(models.TypeTache(projet_id=projet.id, code=code, libelle=libelle,
                                couleur=couleur, ordre=i))
    for i, (code, libelle, couleur) in enumerate(CATEGORIES):
        db.add(models.CategorieDepense(projet_id=projet.id, code=code, libelle=libelle,
                                       couleur=couleur, ordre=i))
    db.commit()


def amorcer(db: Session) -> None:
    """Crée l'administrateur puis, sur une base vierge, le projet DEXTER4LLM.

    Le mot de passe administrateur n'est jamais réécrit sur un redéploiement.
    """
    email = os.getenv("ADMIN_EMAIL", "admin@local").strip().lower()
    admin = db.query(models.Utilisateur).filter_by(email=email).first()
    if not admin:
        brut = os.getenv("ADMIN_MOTDEPASSE", "") or securite.mot_de_passe_provisoire()
        admin = models.Utilisateur(
            email=email, nom=os.getenv("ADMIN_NOM", "Administration"),
            mot_de_passe=securite.hacher(brut), role_global=models.ADMIN,
            actif=True, doit_changer=not os.getenv("ADMIN_MOTDEPASSE"))
        db.add(admin)
        db.commit()
        if not os.getenv("ADMIN_MOTDEPASSE"):
            print("=" * 68)
            print(f"Compte administrateur créé : {email}")
            print(f"Mot de passe provisoire    : {brut}")
            print("À changer à la première connexion. Définissez ADMIN_MOTDEPASSE")
            print("pour fixer ce mot de passe vous-même.")
            print("=" * 68)

    if db.query(models.Projet).first():
        return

    projet = creer_projet_dexter(db)
    caroline = db.query(models.Personne).filter_by(
        projet_id=projet.id, nom="GANS COMBE Caroline").first()
    db.add(models.Acces(utilisateur_id=admin.id, projet_id=projet.id,
                        role=models.GESTIONNAIRE, personne_id=caroline.id if caroline else None))
    db.commit()


def reinitialiser_projet(db: Session, projet: models.Projet) -> None:
    """Vide le contenu métier d'un projet sans toucher aux comptes ni aux accès."""
    for modele in (models.Activite, models.Depense, models.Recurrence):
        db.query(modele).filter_by(projet_id=projet.id).delete()
    db.commit()
    db.query(models.Acces).filter_by(projet_id=projet.id).update({"personne_id": None})
    db.query(models.Personne).filter_by(projet_id=projet.id).delete()
    db.query(models.TypeTache).filter_by(projet_id=projet.id).delete()
    db.query(models.CategorieDepense).filter_by(projet_id=projet.id).delete()
    db.commit()
    referentiel_vierge(db, projet)
