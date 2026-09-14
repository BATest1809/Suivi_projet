"""Schémas d'entrée de l'API. Les sorties sont sérialisées à la main dans main.py."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class Connexion(BaseModel):
    email: str
    mot_de_passe: str


class ChangementMotDePasse(BaseModel):
    ancien: str = ""
    nouveau: str = Field(min_length=8, max_length=200)


class UtilisateurIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    nom: str = ""
    role_global: str = "utilisateur"
    actif: bool = True


class MotDePasseAdmin(BaseModel):
    nouveau: str = Field(min_length=8, max_length=200)


class ProjetIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    intitule: str = Field(min_length=1, max_length=240)
    financeur: str = ""
    date_debut: date
    date_fin: date
    devise: str = "EUR"
    heures_jour: float = 7.0
    taux_defaut: float = 0.0
    actif: bool = True
    artefacts_tableau: Optional[str] = None


class ValidationEnMasse(BaseModel):
    """Sélection de lignes à valider. Les identifiants priment sur les filtres."""
    ids: List[int] = []
    type_tache_id: Optional[int] = None
    personne_id: Optional[int] = None
    recurrence_id: Optional[int] = None
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    note: str = ""


class AccesIn(BaseModel):
    utilisateur_id: int
    projet_id: int
    role: str = "contributeur"
    personne_id: Optional[int] = None


class PersonneIn(BaseModel):
    nom: str = Field(min_length=1, max_length=160)
    organisation: str = ""
    role: str = ""
    taux_horaire: float = 0.0
    imputable: bool = True
    note: str = ""


class TypeTacheIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=160)
    couleur: str = "#6C7C85"


class CategorieIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=160)
    couleur: str = "#6C7C85"


class ActiviteIn(BaseModel):
    date: date
    heure_debut: str = ""
    heure_fin: str = ""
    duree_h: Optional[float] = None
    libelle: str = Field(min_length=1, max_length=300)
    livrable: str = ""
    part_imputable: float = 100.0
    source: str = "agenda"
    statut: str = "mesure"
    mixte: bool = False
    note: str = ""
    type_tache_id: int
    personne_id: int


class DepenseIn(BaseModel):
    date: date
    libelle: str = Field(min_length=1, max_length=300)
    quantite: float = 0.0
    unite: str = ""
    cout_unitaire: float = 0.0
    statut: str = "estime"
    reference: str = ""
    note: str = ""
    categorie_id: int
    personne_id: Optional[int] = None


class RecurrenceIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=200)
    jour_semaine: int = 0
    rang: int = 1
    date_debut: date
    date_fin: date
    duree_h: float = 7.0
    part_imputable: float = 100.0
    heure_debut: str = ""
    heure_fin: str = ""
    statut: str = "estime"
    source: str = "declaratif"
    livrable: str = ""
    note: str = ""
    active: bool = True
    reporter: bool = True
    type_tache_id: int
    personne_id: int
