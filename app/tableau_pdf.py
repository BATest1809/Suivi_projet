"""Tableaux de bord au format PDF.

Le PDF est composé directement, il n'est pas converti depuis le HTML : aucun moteur
de rendu ni bibliothèque système n'est requis, seulement reportlab, qui est du Python
pur. Les blocs, les chiffres et les règles d'affichage sont ceux du tableau de bord
HTML, y compris le masquage des montants et la sélection des artefacts.
"""

from collections import defaultdict
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import tableau_bord as tb

# La palette est celle de l'interface, reprise à l'identique.
BLEU = colors.HexColor("#0073EA")
VERT = colors.HexColor("#00C875")
JAUNE = colors.HexColor("#FDAB3D")
ROUGE = colors.HexColor("#E2445C")
VIOLET = colors.HexColor("#A25DDC")
ENCRE = colors.HexColor("#323338")
GRIS = colors.HexColor("#676879")
GRIS_CLAIR = colors.HexColor("#9699A6")
BORDURE = colors.HexColor("#E6E9EF")
FOND = colors.HexColor("#F6F7FB")
BANDE = [BLEU, VERT, JAUNE, ROUGE, VIOLET]

LARGEUR_UTILE = A4[0] - 30 * mm


def _couleur(valeur, defaut=GRIS):
    try:
        return colors.HexColor(valeur)
    except Exception:
        return defaut


def _style(nom, taille, couleur=ENCRE, gras=False, interligne=None, espace_apres=0):
    return ParagraphStyle(
        nom, fontName="Helvetica-Bold" if gras else "Helvetica", fontSize=taille,
        leading=interligne or taille * 1.35, textColor=couleur, alignment=TA_LEFT,
        spaceAfter=espace_apres)


TITRE = _style("titre", 20, ENCRE, True, espace_apres=2)
SURTITRE = _style("surtitre", 9, GRIS, True, espace_apres=3)
FILET = _style("filet", 8.5, GRIS, interligne=12, espace_apres=0)
SECTION = _style("section", 12, ENCRE, True, espace_apres=5)
CORPS = _style("corps", 8.5, GRIS, interligne=12, espace_apres=4)
CELLULE = _style("cellule", 7.5, ENCRE, interligne=10)
CELLULE_GRISE = _style("cellule_grise", 7, GRIS, interligne=9)


class Bande(Flowable):
    """Les cinq traits colorés qui ouvrent le document."""

    def __init__(self, largeur=LARGEUR_UTILE):
        super().__init__()
        self.width, self.height = largeur, 4
        self._largeur = largeur

    def draw(self):
        x = 0
        for couleur in BANDE:
            self.canv.setFillColor(couleur)
            self.canv.roundRect(x, 0, 11 * mm, 3, 1.5, stroke=0, fill=1)
            x += 13 * mm


class Anneau(Flowable):
    """Anneau de répartition, dessiné en arcs de cercle."""

    def __init__(self, parts, centre_haut, centre_bas, taille=52 * mm):
        super().__init__()
        self.parts = [p for p in parts if p[1] > 0]
        self.centre_haut, self.centre_bas = centre_haut, centre_bas
        self.width = self.height = taille

    def draw(self):
        total = sum(v for _, v, _ in self.parts)
        if total <= 0:
            return
        rayon = self.width / 2 - 3
        centre = self.width / 2
        epaisseur = rayon * 0.38
        depart = 90.0
        for _, valeur, couleur in self.parts:
            etendue = -valeur / total * 360.0
            self.canv.setStrokeColor(_couleur(couleur))
            self.canv.setLineWidth(epaisseur)
            chemin = self.canv.beginPath()
            chemin.arc(centre - rayon + epaisseur / 2, centre - rayon + epaisseur / 2,
                       centre + rayon - epaisseur / 2, centre + rayon - epaisseur / 2,
                       depart, etendue)
            self.canv.drawPath(chemin, stroke=1, fill=0)
            depart += etendue
        self.canv.setFillColor(ENCRE)
        self.canv.setFont("Helvetica-Bold", 15)
        self.canv.drawCentredString(centre, centre + 1, self.centre_haut)
        self.canv.setFillColor(GRIS)
        self.canv.setFont("Helvetica", 7)
        self.canv.drawCentredString(centre, centre - 9, self.centre_bas)


class BarresEmpilees(Flowable):
    """Histogramme mensuel empilé par type de tâche."""

    def __init__(self, mois, sequences, largeur=LARGEUR_UTILE, hauteur=46 * mm):
        super().__init__()
        self.mois, self.sequences = mois, sequences
        self.width, self.height = largeur, hauteur

    def draw(self):
        if not self.mois or not self.sequences:
            return
        bas, haut = 13, self.height - 4
        maxi = max((sum(s["valeurs"].get(m, 0) for s in self.sequences) for m in self.mois),
                   default=0) or 1
        pas = self.width / len(self.mois)
        barre = min(pas * 0.62, 26)
        self.canv.setStrokeColor(BORDURE)
        self.canv.setLineWidth(0.5)
        for fraction in (0, 0.5, 1):
            y = bas + (haut - bas) * fraction
            self.canv.line(0, y, self.width, y)
            self.canv.setFillColor(GRIS_CLAIR)
            self.canv.setFont("Helvetica", 6)
            self.canv.drawString(0, y + 2, tb._n(maxi * fraction, 0) + " h")
        for i, m in enumerate(self.mois):
            x = i * pas + (pas - barre) / 2
            cumul = 0.0
            for seq in self.sequences:
                valeur = seq["valeurs"].get(m, 0)
                if valeur <= 0:
                    continue
                h = valeur / maxi * (haut - bas)
                self.canv.setFillColor(_couleur(seq["couleur"]))
                self.canv.rect(x, bas + cumul, barre, max(h - 0.8, 0.8), stroke=0, fill=1)
                cumul += h
            self.canv.setFillColor(GRIS)
            self.canv.setFont("Helvetica", 5.6)
            self.canv.drawCentredString(x + barre / 2, 5,
                                        m.split("-")[1] + "/" + m.split("-")[0][2:])


class Frise(Flowable):
    """Période d'activité de chaque acteur, une barre par personne."""

    def __init__(self, lignes, premier, dernier, largeur=LARGEUR_UTILE):
        super().__init__()
        self.lignes, self.premier, self.dernier = lignes, premier, dernier
        self.width = largeur
        self.height = max(len(lignes) * 13 + 12, 20)

    def draw(self):
        if not self.lignes or self.dernier < self.premier:
            return
        marge = 42 * mm
        utile = self.width - marge - 22 * mm
        etendue = (self.dernier - self.premier).days or 1
        self.canv.setStrokeColor(BORDURE)
        self.canv.setLineWidth(0.5)
        annee, mois = self.premier.year, self.premier.month
        while date(annee, mois, 1) <= self.dernier:
            borne = date(annee, mois, 1)
            if borne >= self.premier:
                x = marge + (borne - self.premier).days / etendue * utile
                self.canv.line(x, 0, x, self.height - 10)
                self.canv.setFillColor(GRIS_CLAIR)
                self.canv.setFont("Helvetica", 5.4)
                self.canv.drawCentredString(x, self.height - 7, borne.strftime("%m/%y"))
            mois += 1
            if mois == 13:
                mois, annee = 1, annee + 1
        for i, (nom, debut, fin, valeur) in enumerate(self.lignes):
            y = self.height - 22 - i * 13
            self.canv.setFillColor(ENCRE)
            self.canv.setFont("Helvetica", 7)
            self.canv.drawString(0, y + 2, nom[:26])
            x1 = marge + (debut - self.premier).days / etendue * utile
            x2 = marge + (fin - self.premier).days / etendue * utile
            large = max(x2 - x1, 24)
            self.canv.setFillColor(_couleur(tb.COULEURS_AVATAR[
                sum(ord(c) for c in nom) % len(tb.COULEURS_AVATAR)]))
            self.canv.roundRect(x1, y - 1, large, 9, 4.5, stroke=0, fill=1)
            self.canv.setFillColor(colors.white)
            self.canv.setFont("Helvetica-Bold", 5.6)
            self.canv.drawString(x1 + 4, y + 1.6, tb._h(valeur))


def _indicateurs(blocs):
    """Bandeau d'indicateurs, une cellule colorée par mesure."""
    cellules, styles = [], []
    ligne_valeurs, ligne_libelles = [], []
    for i, (valeur, libelle) in enumerate(blocs):
        ligne_valeurs.append(Paragraph(valeur, _style("v", 13, ENCRE, True)))
        ligne_libelles.append(Paragraph(libelle, CELLULE_GRISE))
        styles.append(("LINEABOVE", (i, 0), (i, 0), 1.6, BANDE[i % len(BANDE)]))
    cellules = [ligne_valeurs, ligne_libelles]
    largeur = LARGEUR_UTILE / max(len(blocs), 1)
    table = Table(cellules, colWidths=[largeur] * len(blocs))
    table.setStyle(TableStyle(styles + [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDURE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDURE),
        ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _tableau(entetes, lignes, largeurs, pied=None, aligne_droite=()):
    """Table de données, en-tête gris, filets fins, pied souligné."""
    donnees = [[Paragraph(f"<b>{tb._e(t)}</b>", _style("th", 6.6, GRIS, True)) for t in entetes]]
    donnees += lignes
    if pied:
        donnees.append(pied)
    table = Table(donnees, colWidths=largeurs, repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, BORDURE),
        ("LINEBELOW", (0, 1), (-1, -2 if pied else -1), 0.4, BORDURE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for colonne in aligne_droite:
        style.append(("ALIGN", (colonne, 0), (colonne, -1), "RIGHT"))
    if pied:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, GRIS_CLAIR))
    table.setStyle(TableStyle(style))
    return table


def _p(texte, style=CELLULE):
    return Paragraph(tb._e(texte), style)


def _d(texte, taille=7.5, gras=False):
    return Paragraph(tb._e(texte), _style("d", taille, ENCRE, gras, interligne=10))


def construire_pdf(projet, donnees, personne=None, alertes=None, confidentiel_couts=False,
                   artefacts=None):
    """Compose le tableau de bord en PDF et renvoie les octets du fichier."""
    retenus = None
    if artefacts is not None:
        retenus = {a.strip() for a in (artefacts.split(",") if isinstance(artefacts, str)
                                       else artefacts) if a and a.strip()}

    def veut(code):
        return retenus is None or code in retenus

    devise = projet.devise
    hj = projet.heures_jour or 7.0
    activites = donnees["activites"]
    depenses = donnees["depenses"]
    types = donnees["types"]
    categories = donnees["categories"]
    noms_pers = donnees["noms_personnes"]
    couleur_type = {t.id: t.couleur or tb.PALETTE_DEFAUT for t in types}
    libelle_type = {t.id: t.libelle for t in types}

    par_type = defaultdict(lambda: {"n": 0, "h": 0.0, "hi": 0.0, "c": 0.0})
    par_personne = defaultdict(lambda: {"n": 0, "hi": 0.0, "c": 0.0})
    par_mois_type = defaultdict(lambda: defaultdict(float))
    mois_vus = set()
    bornes = {}
    for a in activites:
        par_type[a.type_tache_id]["n"] += 1
        par_type[a.type_tache_id]["h"] += a.heures
        par_type[a.type_tache_id]["hi"] += a.heures_imputees
        par_type[a.type_tache_id]["c"] += a.cout
        par_personne[a.personne_id]["n"] += 1
        par_personne[a.personne_id]["hi"] += a.heures_imputees
        par_personne[a.personne_id]["c"] += a.cout
        cle = a.date.strftime("%Y-%m")
        mois_vus.add(cle)
        par_mois_type[a.type_tache_id][cle] += a.heures_imputees
        if a.personne_id in bornes:
            d0, d1 = bornes[a.personne_id]
            bornes[a.personne_id] = (min(d0, a.date), max(d1, a.date))
        else:
            bornes[a.personne_id] = (a.date, a.date)

    par_categorie = defaultdict(lambda: {"n": 0, "m": 0.0, "j": 0.0})
    for d in depenses:
        par_categorie[d.categorie_id]["n"] += 1
        par_categorie[d.categorie_id]["m"] += d.montant
        if d.statut == "mesure":
            par_categorie[d.categorie_id]["j"] += d.montant
        mois_vus.add(d.date.strftime("%Y-%m"))

    total_h = sum(a.heures for a in activites)
    total_hi = sum(a.heures_imputees for a in activites)
    total_cout = sum(a.cout for a in activites)
    total_dep = sum(d.montant for d in depenses)
    total_dep_j = sum(d.montant for d in depenses if d.statut == "mesure")
    h_source = sum(a.heures_imputees for a in activites
                   if getattr(a, "mesuree_a_la_source", a.statut == "mesure"))
    h_validees = sum(a.heures_imputees for a in activites if getattr(a, "validee", False))
    h_attente = sum(a.heures_imputees for a in activites if a.statut == "estime")

    titre = personne.nom if personne else projet.intitule
    sous_titre = ("Relevé individuel des temps et dépenses"
                  if personne else "Récapitulatif consolidé des temps et dépenses")

    histoire = []
    histoire.append(Bande())
    histoire.append(Spacer(1, 7))
    histoire.append(Paragraph(tb._e(projet.intitule), SURTITRE))
    histoire.append(Paragraph(tb._e(titre), TITRE))
    periode = (f"{projet.date_debut.strftime('%d/%m/%Y')} au "
               f"{projet.date_fin.strftime('%d/%m/%Y')}")
    financeur = f" Financement : {tb._e(projet.financeur)}." if projet.financeur else ""
    histoire.append(Paragraph(
        f"{tb._e(sous_titre)}. Période du {periode}.{financeur} "
        f"Document établi le {datetime.now().strftime('%d/%m/%Y à %H:%M')}.", FILET))
    histoire.append(Spacer(1, 10))

    # ---------- indicateurs ----------
    if veut("indicateurs"):
        blocs = [(tb._h(total_hi), f"heures imputées, sur {tb._h(total_h)} enregistrées"),
                 (tb._n(total_hi / hj), f"jours-homme à {tb._n(hj, 1)} h")]
        if not personne:
            blocs.append((str(len(par_personne)), "acteurs déclarés"))
        if not confidentiel_couts:
            blocs.append((tb._m(total_cout, devise), "coût de main d'œuvre"))
            blocs.append((tb._m(total_dep, devise), "dépenses techniques"))
        blocs.append(((tb._n(h_source / total_hi * 100, 0) + " %") if total_hi else "0 %",
                      "heures mesurées à la source"))
        histoire.append(_indicateurs(blocs))
        histoire.append(Spacer(1, 12))

    # ---------- total ----------
    if veut("total") and not confidentiel_couts:
        histoire.append(Paragraph("Total engagé à date", SURTITRE))
        histoire.append(Paragraph(tb._m(total_cout + total_dep, devise),
                                  _style("grand", 26, ENCRE, True, espace_apres=2)))
        histoire.append(Paragraph(
            f"{tb._m(total_cout, devise)} de main d'œuvre et {tb._m(total_dep, devise)} de "
            f"dépenses techniques, dont {tb._m(total_dep_j, devise)} justifiées par une pièce.",
            CORPS))
        histoire.append(Spacer(1, 10))

    # ---------- chronologie ----------
    if veut("chronologie") and activites:
        lignes_frise = [(noms_pers.get(pid, {}).get("nom", ""), d0, d1, par_personne[pid]["hi"])
                        for pid, (d0, d1) in sorted(bornes.items(), key=lambda kv: kv[1][0])]
        dates = [a.date for a in activites]
        histoire.append(KeepTogether([
            Paragraph("Période d'activité par acteur", SECTION),
            Frise(lignes_frise, min(dates), max(dates)),
            Spacer(1, 12)]))

    # ---------- anneau ----------
    parts = [(libelle_type.get(tid, "Non classé"), vals["hi"], couleur_type.get(tid))
             for tid, vals in sorted(par_type.items(), key=lambda kv: -kv[1]["hi"])
             if vals["hi"] > 0]
    if veut("anneau") and parts:
        legende = []
        for libelle, valeur, couleur in parts:
            part = tb._n(valeur / total_hi * 100, 0) if total_hi else "0"
            legende.append([_pastille(couleur), _d(libelle),
                            _d(tb._h(valeur), gras=True), _d(part + " %", 7, False)])
        table_legende = Table(legende, colWidths=[8, None, 60, 34])
        table_legende.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (3, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        cote = Table([[Anneau(parts, tb._n(total_hi / hj, 1), "jours-homme"), table_legende]],
                     colWidths=[58 * mm, LARGEUR_UTILE - 58 * mm])
        cote.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        histoire.append(KeepTogether([Paragraph("Répartition de l'effort", SECTION), cote,
                                      Spacer(1, 12)]))

    # ---------- histogramme ----------
    if veut("barres") and mois_vus:
        sequences = [{"libelle": libelle_type.get(t.id, ""), "couleur": couleur_type.get(t.id),
                      "valeurs": dict(par_mois_type[t.id])}
                     for t in types if t.id in par_mois_type]
        histoire.append(KeepTogether([
            Paragraph("Charge mensuelle par type de tâche", SECTION),
            BarresEmpilees(sorted(mois_vus), sequences),
            Spacer(1, 12)]))

    # ---------- statuts ----------
    if veut("statuts"):
        source = [a for a in activites
                  if getattr(a, "mesuree_a_la_source", a.statut == "mesure")]
        validees = [a for a in activites if getattr(a, "validee", False)]
        attente = [a for a in activites if a.statut == "estime"]
        arbitrer = [a for a in activites
                    if (a.mixte and float(a.part_imputable) >= 100) or a.heures <= 0
                    or (a.date_theorique and a.date_theorique != a.date)]
        colonnes = [("Mesuré à la source", VERT, len(source)),
                    ("Retenu par validation", BLEU, len(validees)),
                    ("En attente de validation", JAUNE, len(attente)),
                    ("À arbitrer", ROUGE, len(arbitrer))]
        cellules = [[Paragraph(f"<b>{tb._e(nom)} / {n}</b>",
                               _style("col", 7.5, colors.white, True))
                     for nom, _, n in colonnes]]
        largeur = LARGEUR_UTILE / len(colonnes)
        table = Table(cellules, colWidths=[largeur] * len(colonnes))
        style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
        for i, (_, couleur, _) in enumerate(colonnes):
            style.append(("BACKGROUND", (i, 0), (i, 0), couleur))
        table.setStyle(TableStyle(style))
        histoire.append(KeepTogether([
            Paragraph("État des lignes de temps", SECTION),
            Paragraph(
                "Une durée mesurée à la source et une durée retenue après validation comptent "
                "toutes deux dans le récapitulatif, mais ne se valent pas : la seconde reste un "
                f"arbitrage. {tb._h(h_source)} relèvent de la première, {tb._h(h_validees)} de "
                f"la seconde, {tb._h(h_attente)} restent en attente.", CORPS),
            table, Spacer(1, 12)]))

    # ---------- tableau par type ----------
    if veut("types"):
        entetes = ["Type de tâche", "Lignes", "Heures", "Imputées"]
        largeurs = [None, 46, 62, 62]
        if not confidentiel_couts:
            entetes.append("Coût")
            largeurs.append(70)
        lignes = []
        for tid, v in sorted(par_type.items(), key=lambda kv: -kv[1]["hi"]):
            ligne = [_pastille_texte(libelle_type.get(tid, "Non classé"), couleur_type.get(tid)),
                     _d(str(v["n"])), _d(tb._h(v["h"])), _d(tb._h(v["hi"]))]
            if not confidentiel_couts:
                ligne.append(_d(tb._m(v["c"], devise)))
            lignes.append(ligne)
        pied = [_d("Total", gras=True), _d(str(len(activites)), gras=True),
                _d(tb._h(total_h), gras=True), _d(tb._h(total_hi), gras=True)]
        if not confidentiel_couts:
            pied.append(_d(tb._m(total_cout, devise), gras=True))
        histoire.append(Paragraph("Détail par type de tâche", SECTION))
        histoire.append(_tableau(entetes, lignes, largeurs, pied,
                                 aligne_droite=range(1, len(entetes))))
        histoire.append(Spacer(1, 12))

    # ---------- acteurs ----------
    if not personne and veut("acteurs"):
        entetes = ["Acteur", "Organisation", "Lignes", "Heures imputées", "Jours-homme"]
        largeurs = [None, 110, 40, 74, 62]
        if not confidentiel_couts:
            entetes += ["Taux horaire", "Coût"]
            largeurs += [60, 70]
        lignes = []
        for pid, v in sorted(par_personne.items(), key=lambda kv: -kv[1]["hi"]):
            info = noms_pers.get(pid, {})
            ligne = [_d(info.get("nom", "")), _p(info.get("organisation", ""), CELLULE_GRISE),
                     _d(str(v["n"])), _d(tb._h(v["hi"])), _d(tb._n(v["hi"] / hj))]
            if not confidentiel_couts:
                taux = info.get("taux", 0)
                ligne.append(_d(tb._m(taux, devise) if taux else "à renseigner"))
                ligne.append(_d(tb._m(v["c"], devise)))
            lignes.append(ligne)
        pied = [_d("Total", gras=True), _d(""), _d(str(len(activites)), gras=True),
                _d(tb._h(total_hi), gras=True), _d(tb._n(total_hi / hj), gras=True)]
        if not confidentiel_couts:
            pied += [_d(""), _d(tb._m(total_cout, devise), gras=True)]
        histoire.append(Paragraph("Contribution par acteur", SECTION))
        histoire.append(_tableau(entetes, lignes, largeurs, pied,
                                 aligne_droite=range(2, len(entetes))))
        histoire.append(Spacer(1, 12))

    # ---------- dépenses ----------
    if depenses and not confidentiel_couts and veut("depenses"):
        libelle_cat = {c.id: c.libelle for c in categories}
        couleur_cat = {c.id: c.couleur or tb.PALETTE_DEFAUT for c in categories}
        lignes = [[_pastille_texte(libelle_cat.get(cid, "Non classée"), couleur_cat.get(cid)),
                   _d(str(v["n"])), _d(tb._m(v["m"], devise)), _d(tb._m(v["j"], devise)),
                   _d(tb._m(v["m"] - v["j"], devise))]
                  for cid, v in sorted(par_categorie.items(), key=lambda kv: -kv[1]["m"])]
        pied = [_d("Total", gras=True), _d(str(len(depenses)), gras=True),
                _d(tb._m(total_dep, devise), gras=True), _d(tb._m(total_dep_j, devise), gras=True),
                _d(tb._m(total_dep - total_dep_j, devise), gras=True)]
        histoire.append(Paragraph("Dépenses techniques", SECTION))
        histoire.append(_tableau(["Catégorie", "Lignes", "Montant", "Justifié", "Estimé"],
                                 lignes, [None, 46, 74, 74, 74], pied,
                                 aligne_droite=(1, 2, 3, 4)))
        histoire.append(Spacer(1, 12))

    # ---------- détail ----------
    if veut("detail"):
        entetes = ["Date", "Libellé", "Type"]
        largeurs = [50, None, 84]
        if not personne:
            entetes.append("Acteur")
            largeurs.append(78)
        entetes += ["Durée", "Part", "Imputé"]
        largeurs += [44, 32, 48]
        if not confidentiel_couts:
            entetes.append("Coût")
            largeurs.append(58)
        lignes = []
        for a in sorted(activites, key=lambda x: x.date):
            marques = []
            if a.mixte:
                marques.append("mixte")
            if a.statut == "estime":
                marques.append("en attente de validation")
            if getattr(a, "validee", False):
                signataire = ""
                if getattr(a, "valide_par", None):
                    signataire = a.valide_par.nom or a.valide_par.email
                marques.append("validée le " + a.valide_le.strftime("%d/%m/%Y")
                               + (f", {signataire}" if signataire else ""))
            if a.date_theorique and a.date_theorique != a.date:
                marques.append("reportée du " + a.date_theorique.strftime("%d/%m/%Y"))
            if a.source == "declaratif":
                marques.append("déclaratif")
            corps = tb._e(a.libelle)
            if marques:
                corps += (f'<br/><font size="6" color="#9699A6">'
                          f'{tb._e(" · ".join(marques))}</font>')
            ligne = [_d(a.date.strftime("%d/%m/%Y")),
                     Paragraph(corps, CELLULE),
                     _pastille_texte(libelle_type.get(a.type_tache_id, ""),
                                     couleur_type.get(a.type_tache_id))]
            if not personne:
                ligne.append(_d(noms_pers.get(a.personne_id, {}).get("nom", "")))
            ligne += [_d(tb._h(a.heures)), _d(tb._n(a.part_imputable, 0) + " %"),
                      _d(tb._h(a.heures_imputees))]
            if not confidentiel_couts:
                ligne.append(_d(tb._m(a.cout, devise)))
            lignes.append(ligne)
        histoire.append(Paragraph("Détail des lignes de temps", SECTION))
        histoire.append(_tableau(entetes, lignes, largeurs,
                                 aligne_droite=range(len(entetes) - (3 if confidentiel_couts else 4),
                                                     len(entetes))))
        histoire.append(Spacer(1, 12))

    # ---------- réserves ----------
    if veut("reserves"):
        histoire.append(Paragraph("Points à arbitrer", SECTION))
        if alertes:
            histoire.append(Paragraph(
                "Ces réserves accompagnent le récapitulatif plutôt qu'elles ne le contredisent : "
                "les signaler est la condition pour que le reste soit tenu pour fiable.", CORPS))
            for alerte in alertes:
                cadre = Table([[Paragraph(tb._e(alerte["texte"]), CELLULE)]],
                              colWidths=[LARGEUR_UTILE])
                cadre.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCE9EC")),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.4, ROUGE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
                histoire.append(cadre)
                histoire.append(Spacer(1, 4))
        elif not personne:
            cadre = Table([[Paragraph("Aucune zone grise détectée sur ce périmètre.", CELLULE)]],
                          colWidths=[LARGEUR_UTILE])
            cadre.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E3F7ED")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.4, VERT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            histoire.append(cadre)

    tampon = _Tampon()
    document = SimpleDocTemplate(
        tampon, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title=f"{sous_titre} - {titre}", author="Suivi des temps et dépenses")
    document.build(histoire, onFirstPage=_pied_de_page, onLaterPages=_pied_de_page)
    return tampon.getvalue()


class _Pastille(Flowable):
    def __init__(self, couleur, taille=7):
        super().__init__()
        self.couleur = couleur
        self.width = self.height = taille

    def draw(self):
        self.canv.setFillColor(_couleur(self.couleur))
        self.canv.roundRect(0, 0, self.width, self.height, 2, stroke=0, fill=1)


def _pastille(couleur):
    return _Pastille(couleur)


def _pastille_texte(libelle, couleur):
    """Libellé précédé de sa pastille de couleur, comme dans l'interface."""
    table = Table([[_Pastille(couleur), _d(libelle)]], colWidths=[10, None])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return table


def _pied_de_page(canevas, document):
    canevas.saveState()
    canevas.setFont("Helvetica", 6.5)
    canevas.setFillColor(GRIS_CLAIR)
    canevas.drawString(15 * mm, 9 * mm,
                       "Les heures imputées résultent de la durée déclarée multipliée par la "
                       "part affectée au projet. Document généré sans retraitement manuel.")
    canevas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"page {canevas.getPageNumber()}")
    canevas.restoreState()


class _Tampon:
    """Fichier en mémoire, suffisant pour reportlab."""

    def __init__(self):
        import io
        self._flux = io.BytesIO()

    def write(self, donnees):
        return self._flux.write(donnees)

    def seek(self, *args):
        return self._flux.seek(*args)

    def tell(self):
        return self._flux.tell()

    def getvalue(self):
        return self._flux.getvalue()

    def close(self):
        pass
