"""Authentification et contrôle d'accès.

Aucune dépendance externe : le hachage repose sur scrypt de la bibliothèque
standard, et la session sur un jeton signé HMAC déposé dans un cookie httpOnly.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models
from .database import get_db

COOKIE = "suivi_session"
DUREE_SESSION = int(os.getenv("DUREE_SESSION_HEURES", "12")) * 3600

_SECRET = os.getenv("SECRET_KEY", "")
if not _SECRET:
    # Sans clé fournie, les sessions ne survivent pas à un redémarrage.
    _SECRET = secrets.token_urlsafe(48)
    print("ATTENTION : SECRET_KEY absente, clé éphémère générée. "
          "Définissez SECRET_KEY pour que les sessions survivent aux redéploiements.")
SECRET = _SECRET.encode()


# --------------------------------------------------------------------------
# mots de passe
# --------------------------------------------------------------------------

def hacher(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    empreinte = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(sel).decode()}${base64.b64encode(empreinte).decode()}"


def verifier(mot_de_passe: str, stocke: str) -> bool:
    try:
        algo, sel_b64, empreinte_b64 = stocke.split("$")
        if algo != "scrypt":
            return False
        sel = base64.b64decode(sel_b64)
        attendu = base64.b64decode(empreinte_b64)
        calcule = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(attendu, calcule)
    except Exception:
        return False


def mot_de_passe_provisoire() -> str:
    """Mot de passe lisible, à communiquer puis à changer à la première connexion."""
    return secrets.token_urlsafe(9)


# --------------------------------------------------------------------------
# jetons de session
# --------------------------------------------------------------------------

def _signer(charge: bytes) -> str:
    signature = hmac.new(SECRET, charge, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(charge).decode().rstrip("=") + "." + \
        base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _completer(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def creer_jeton(utilisateur_id: int) -> str:
    charge = json.dumps({"uid": utilisateur_id, "exp": int(time.time()) + DUREE_SESSION}).encode()
    return _signer(charge)


def lire_jeton(jeton: str):
    try:
        charge_b64, signature_b64 = jeton.split(".")
        charge = _completer(charge_b64)
        attendue = hmac.new(SECRET, charge, hashlib.sha256).digest()
        if not hmac.compare_digest(attendue, _completer(signature_b64)):
            return None
        donnees = json.loads(charge)
        if donnees.get("exp", 0) < time.time():
            return None
        return donnees
    except Exception:
        return None


# --------------------------------------------------------------------------
# dépendances FastAPI
# --------------------------------------------------------------------------

def utilisateur_courant(suivi_session: str = Cookie(default=None), db: Session = Depends(get_db)):
    if not suivi_session:
        raise HTTPException(401, "Session absente ou expirée.")
    donnees = lire_jeton(suivi_session)
    if not donnees:
        raise HTTPException(401, "Session invalide ou expirée.")
    u = db.get(models.Utilisateur, donnees["uid"])
    if not u or not u.actif:
        raise HTTPException(401, "Compte introuvable ou désactivé.")
    return u


def administrateur(u: models.Utilisateur = Depends(utilisateur_courant)):
    if not u.est_admin:
        raise HTTPException(403, "Cette action est réservée à l'administration.")
    return u


class Portee:
    """Droits effectifs d'un utilisateur sur un projet donné."""

    def __init__(self, utilisateur, projet, role, personne_id):
        self.utilisateur = utilisateur
        self.projet = projet
        self.role = role
        self.personne_id = personne_id

    @property
    def est_admin(self) -> bool:
        return self.utilisateur.est_admin

    @property
    def pilote(self) -> bool:
        """Voit et modifie l'ensemble du projet."""
        return self.est_admin or self.role == models.GESTIONNAIRE

    @property
    def lecture_seule(self) -> bool:
        return self.role == models.LECTEUR and not self.est_admin

    @property
    def restreint(self) -> bool:
        """Ne voit que ses propres lignes."""
        return self.role == models.CONTRIBUTEUR and not self.est_admin

    def exiger_ecriture(self):
        if self.lecture_seule:
            raise HTTPException(403, "Votre accès à ce projet est en lecture seule.")

    def exiger_pilotage(self):
        if not self.pilote:
            raise HTTPException(403, "Cette action est réservée au pilotage du projet.")

    def exiger_personne(self, personne_id: int):
        """Un contributeur ne peut agir que sur les lignes de sa propre personne."""
        if self.restreint and personne_id != self.personne_id:
            raise HTTPException(403, "Vous ne pouvez déclarer que votre propre temps sur ce projet.")


def portee(projet_id: int, db: Session, utilisateur: models.Utilisateur) -> Portee:
    projet = db.get(models.Projet, projet_id)
    if not projet:
        raise HTTPException(404, "Projet introuvable.")
    if utilisateur.est_admin:
        acces = db.query(models.Acces).filter_by(
            utilisateur_id=utilisateur.id, projet_id=projet_id).first()
        return Portee(utilisateur, projet, models.GESTIONNAIRE,
                      acces.personne_id if acces else None)
    acces = db.query(models.Acces).filter_by(
        utilisateur_id=utilisateur.id, projet_id=projet_id).first()
    if not acces:
        raise HTTPException(403, "Vous n'avez pas accès à ce projet.")
    return Portee(utilisateur, projet, acces.role, acces.personne_id)
