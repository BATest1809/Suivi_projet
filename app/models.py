"""Schéma relationnel du suivi des temps et dépenses, version multi-projet.

Toute donnée métier est rattachée à un projet. Les droits sont portés par la table
acces, qui relie un utilisateur à un projet avec un rôle et, le cas échéant, la
personne dont il déclare le temps.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base

# Rôles globaux
ADMIN = "admin"
UTILISATEUR = "utilisateur"

# Rôles par projet
GESTIONNAIRE = "gestionnaire"   # pilote le projet, voit et modifie tout
CONTRIBUTEUR = "contributeur"   # ne voit et ne modifie que ses propres lignes
LECTEUR = "lecteur"             # lecture seule sur l'ensemble du projet

ROLES_PROJET = (GESTIONNAIRE, CONTRIBUTEUR, LECTEUR)


class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    nom = Column(String(160), nullable=False, default="")
    mot_de_passe = Column(String(300), nullable=False)
    role_global = Column(String(20), nullable=False, default=UTILISATEUR)
    actif = Column(Boolean, nullable=False, default=True)
    doit_changer = Column(Boolean, nullable=False, default=False)
    cree_le = Column(DateTime, default=datetime.utcnow)
    derniere_connexion = Column(DateTime, nullable=True)

    acces = relationship("Acces", back_populates="utilisateur", cascade="all, delete-orphan")

    @property
    def est_admin(self) -> bool:
        return self.role_global == ADMIN


class Projet(Base):
    __tablename__ = "projets"

    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True, nullable=False)
    intitule = Column(String(240), nullable=False)
    financeur = Column(String(160), default="")
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date, nullable=False)
    devise = Column(String(3), nullable=False, default="EUR")
    heures_jour = Column(Float, nullable=False, default=7.0)
    taux_defaut = Column(Float, nullable=False, default=0.0)
    actif = Column(Boolean, nullable=False, default=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    # artefacts retenus pour le tableau de bord, codes séparés par des virgules
    artefacts_tableau = Column(String(400), nullable=False, default="")

    acces = relationship("Acces", back_populates="projet", cascade="all, delete-orphan")
    personnes = relationship("Personne", back_populates="projet", cascade="all, delete-orphan")


class Acces(Base):
    __tablename__ = "acces"
    __table_args__ = (UniqueConstraint("utilisateur_id", "projet_id", name="uq_acces"),)

    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default=CONTRIBUTEUR)
    # personne dont l'utilisateur déclare le temps dans ce projet
    personne_id = Column(Integer, ForeignKey("personnes.id", ondelete="SET NULL"), nullable=True)

    utilisateur = relationship("Utilisateur", back_populates="acces")
    projet = relationship("Projet", back_populates="acces")
    personne = relationship("Personne", foreign_keys=[personne_id])


class TypeTache(Base):
    __tablename__ = "types_tache"
    __table_args__ = (UniqueConstraint("projet_id", "code", name="uq_type_projet"),)

    id = Column(Integer, primary_key=True)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    libelle = Column(String(160), nullable=False)
    couleur = Column(String(9), nullable=False, default="#6C7C85")
    ordre = Column(Integer, nullable=False, default=0)

    activites = relationship("Activite", back_populates="type_tache")


class CategorieDepense(Base):
    __tablename__ = "categories_depense"
    __table_args__ = (UniqueConstraint("projet_id", "code", name="uq_categorie_projet"),)

    id = Column(Integer, primary_key=True)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    libelle = Column(String(160), nullable=False)
    couleur = Column(String(9), nullable=False, default="#6C7C85")
    ordre = Column(Integer, nullable=False, default=0)

    depenses = relationship("Depense", back_populates="categorie")


class Personne(Base):
    __tablename__ = "personnes"
    __table_args__ = (UniqueConstraint("projet_id", "nom", name="uq_personne_projet"),)

    id = Column(Integer, primary_key=True)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False, index=True)
    nom = Column(String(160), nullable=False)
    organisation = Column(String(160), default="")
    role = Column(String(160), default="")
    taux_horaire = Column(Float, nullable=False, default=0.0)
    imputable = Column(Boolean, nullable=False, default=True)
    note = Column(Text, default="")

    projet = relationship("Projet", back_populates="personnes")
    activites = relationship("Activite", back_populates="personne")
    depenses = relationship("Depense", back_populates="personne")


class Recurrence(Base):
    """Règle mensuelle. jour_semaine suit Python : 0 lundi, 4 vendredi.

    rang vaut 1 pour la première occurrence du mois, -1 pour la dernière.
    """

    __tablename__ = "recurrences"

    id = Column(Integer, primary_key=True)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False, index=True)
    libelle = Column(String(200), nullable=False)
    jour_semaine = Column(Integer, nullable=False, default=0)
    rang = Column(Integer, nullable=False, default=1)
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date, nullable=False)
    duree_h = Column(Float, nullable=False, default=7.0)
    part_imputable = Column(Float, nullable=False, default=100.0)
    heure_debut = Column(String(5), default="")
    heure_fin = Column(String(5), default="")
    statut = Column(String(10), nullable=False, default="estime")
    source = Column(String(20), nullable=False, default="declaratif")
    livrable = Column(String(200), default="")
    note = Column(Text, default="")
    active = Column(Boolean, nullable=False, default=True)
    reporter = Column(Boolean, nullable=False, default=True)

    type_tache_id = Column(Integer, ForeignKey("types_tache.id"), nullable=False)
    personne_id = Column(Integer, ForeignKey("personnes.id"), nullable=False)

    activites = relationship("Activite", back_populates="recurrence")


class Activite(Base):
    __tablename__ = "activites"
    __table_args__ = (
        UniqueConstraint("recurrence_id", "date_theorique", "personne_id", name="uq_recurrence_jour"),
    )

    id = Column(Integer, primary_key=True)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    # date issue de la règle avant report, clé d'idempotence de la génération
    date_theorique = Column(Date, nullable=True)
    heure_debut = Column(String(5), default="")
    heure_fin = Column(String(5), default="")
    duree_h = Column(Float, nullable=True)
    libelle = Column(String(300), nullable=False)
    livrable = Column(String(200), default="")
    part_imputable = Column(Float, nullable=False, default=100.0)
    source = Column(String(20), nullable=False, default="agenda")
    statut = Column(String(10), nullable=False, default="mesure")
    mixte = Column(Boolean, nullable=False, default=False)
    note = Column(Text, default="")

    # Trace de validation : une durée estimée validée par le pilotage devient une durée
    # retenue, mais l'origine de cette bascule reste inscrite et n'est jamais effacée.
    valide_le = Column(DateTime, nullable=True)
    valide_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    origine_estimee = Column(Boolean, nullable=False, default=False)

    type_tache_id = Column(Integer, ForeignKey("types_tache.id"), nullable=False)
    personne_id = Column(Integer, ForeignKey("personnes.id"), nullable=False)
    recurrence_id = Column(Integer, ForeignKey("recurrences.id", ondelete="SET NULL"), nullable=True)

    type_tache = relationship("TypeTache", back_populates="activites")
    personne = relationship("Personne", back_populates="activites")
    recurrence = relationship("Recurrence", back_populates="activites")
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id])

    @property
    def validee(self) -> bool:
        return self.valide_le is not None

    @property
    def mesuree_a_la_source(self) -> bool:
        """Durée mesurée dès la saisie, sans passer par une validation."""
        return self.statut == "mesure" and not bool(self.origine_estimee)

    @property
    def heures(self) -> float:
        if self.duree_h is not None:
            return float(self.duree_h)
        if not self.heure_debut or not self.heure_fin:
            return 0.0
        try:
            h1, m1 = (int(x) for x in self.heure_debut.split(":"))
            h2, m2 = (int(x) for x in self.heure_fin.split(":"))
        except ValueError:
            return 0.0
        delta = (h2 * 60 + m2) - (h1 * 60 + m1)
        if delta < 0:
            delta += 24 * 60
        return delta / 60.0

    @property
    def heures_imputees(self) -> float:
        return self.heures * (float(self.part_imputable or 0) / 100.0)

    @property
    def taux_horaire_applique(self) -> float:
        """Taux retenu : celui de la personne, à défaut celui du projet.

        Le repli sur le taux du projet évite qu'un coût soit calculé à zéro alors
        que les exports et les contrôles annoncent, eux, le taux par défaut.
        """
        if not self.personne:
            return 0.0
        taux = float(self.personne.taux_horaire or 0)
        if taux > 0:
            return taux
        projet = self.personne.projet
        return float(projet.taux_defaut or 0) if projet else 0.0

    @property
    def cout(self) -> float:
        if not self.personne or not self.personne.imputable:
            return 0.0
        return self.heures_imputees * self.taux_horaire_applique


ARTEFACTS = [
    ("indicateurs", "Bandeau d'indicateurs"),
    ("total", "Grand total engagé"),
    ("anneau", "Anneau de répartition par type de tâche"),
    ("barres", "Histogramme mensuel empilé"),
    ("statuts", "Vue d'ensemble par statut de durée"),
    ("chronologie", "Chronologie d'engagement des acteurs"),
    ("types", "Tableau par type de tâche"),
    ("acteurs", "Plan de charge et tableau par acteur"),
    ("depenses", "Tableau des dépenses techniques"),
    ("detail", "Détail des lignes de temps"),
    ("reserves", "Points à arbitrer"),
]

ARTEFACTS_DEFAUT = ",".join(code for code, _ in ARTEFACTS)


class Depense(Base):
    __tablename__ = "depenses"

    id = Column(Integer, primary_key=True)
    projet_id = Column(Integer, ForeignKey("projets.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    libelle = Column(String(300), nullable=False)
    quantite = Column(Float, nullable=False, default=0.0)
    unite = Column(String(60), default="")
    cout_unitaire = Column(Float, nullable=False, default=0.0)
    statut = Column(String(10), nullable=False, default="estime")
    reference = Column(String(200), default="")
    note = Column(Text, default="")

    categorie_id = Column(Integer, ForeignKey("categories_depense.id"), nullable=False)
    personne_id = Column(Integer, ForeignKey("personnes.id"), nullable=True)

    categorie = relationship("CategorieDepense", back_populates="depenses")
    personne = relationship("Personne", back_populates="depenses")

    @property
    def montant(self) -> float:
        return float(self.quantite or 0) * float(self.cout_unitaire or 0)
