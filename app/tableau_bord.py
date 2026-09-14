"""Tableaux de bord exportables.

Produit un fichier HTML autonome, sans dépendance ni appel réseau, imprimable en PDF.
Deux formes : individuelle, centrée sur une personne, et consolidée, destinée au
financeur, qui expose tous les acteurs.

Tous les graphiques sont du SVG écrit à la main. La couleur ne porte jamais seule une
information : chaque graphique est doublé d'un tableau chiffré et chaque segment porte
une infobulle.
"""

from collections import defaultdict
from datetime import date, datetime

PALETTE_DEFAUT = "#7E8DA3"
COULEURS_AVATAR = ["#0073EA", "#00C875", "#FDAB3D", "#E2445C",
                   "#A25DDC", "#00C4C4", "#5559DF", "#7E8DA3"]


# --------------------------------------------------------------------------
# formats
# --------------------------------------------------------------------------

def _e(v) -> str:
    return (str(v if v is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _h(v: float) -> str:
    return f"{v or 0:,.2f}".replace(",", " ").replace(".", ",") + " h"


def _n(v: float, d: int = 2) -> str:
    return f"{v or 0:,.{d}f}".replace(",", " ").replace(".", ",")


def _m(v: float, devise: str) -> str:
    symbole = {"EUR": "€", "USD": "$", "CAD": "$", "CHF": "CHF"}.get(devise, devise)
    return f"{_n(v)} {symbole}"


def _mois_fr(cle: str) -> str:
    noms = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    annee, mois = cle.split("-")
    return f"{noms[int(mois) - 1]} {annee}"


# --------------------------------------------------------------------------
# feuille de style
# --------------------------------------------------------------------------

CSS = """
:root{
  --fond:#F6F7FB; --carte:#FFFFFF; --bordure:#E6E9EF; --bordure-forte:#D0D4E4;
  --encre:#323338; --gris:#676879; --gris-clair:#9699A6;
  --bleu:#0073EA; --bleu-voile:#E5F1FE; --vert:#00C875; --vert-voile:#E3F7ED;
  --jaune:#FDAB3D; --jaune-voile:#FFF3E2; --rouge:#E2445C; --rouge-voile:#FCE9EC;
  --violet:#A25DDC;
  --ombre:0 1px 2px rgba(0,0,0,.04), 0 4px 14px -6px rgba(50,53,56,.14);
}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--encre);
  font:14px/1.5 "Figtree",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.page{max-width:1080px;margin:0 auto;padding:36px 26px 70px}
h1,h2,h3{margin:0;font-weight:600;letter-spacing:-.02em}
h1{font-size:30px;line-height:1.15}
h2{font-size:17px;margin-bottom:14px}
h3{font-size:13px;color:var(--gris);font-weight:600}
p{margin:0 0 11px;max-width:80ch;color:var(--gris)}
header.une{margin-bottom:22px}
.marque{display:flex;gap:5px;margin-bottom:14px}
.marque span{height:5px;width:34px;border-radius:3px}
.filet{color:var(--gris);font-size:13px;margin-top:7px;max-width:80ch}
.bandeau{display:grid;grid-template-columns:repeat(auto-fit,minmax(176px,1fr));gap:14px;margin:22px 0}
.bloc{background:var(--carte);border-radius:8px;box-shadow:var(--ombre);padding:16px 18px;
  border-top:3px solid var(--bleu)}
.bloc:nth-child(2){border-top-color:var(--violet)}
.bloc:nth-child(3){border-top-color:#00C4C4}
.bloc:nth-child(4){border-top-color:var(--vert)}
.bloc:nth-child(5){border-top-color:var(--jaune)}
.bloc:nth-child(6){border-top-color:#5559DF}
.bloc .v{font-size:27px;font-weight:700;line-height:1.1;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.bloc .l{font-size:12.5px;color:var(--gris);margin-top:5px}
section{background:var(--carte);border-radius:8px;box-shadow:var(--ombre);padding:20px 22px;margin-bottom:18px}
.duo{display:grid;grid-template-columns:300px 1fr;gap:18px;margin-bottom:18px}
.duo-haut{display:grid;grid-template-columns:1fr 296px;gap:18px;margin-bottom:18px}
.duo>section,.duo-haut>section{margin-bottom:0}
.grand{font-size:40px;font-weight:700;letter-spacing:-.035em;line-height:1.05;margin:10px 0 6px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11.5px;font-weight:600;color:var(--gris);
  border-bottom:1px solid var(--bordure);padding:9px 10px;white-space:nowrap}
td{border-bottom:1px solid var(--bordure);padding:9px 10px;vertical-align:middle}
tfoot th{border-top:1px solid var(--bordure-forte);border-bottom:none;color:var(--encre);font-size:13px}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pilule{display:inline-block;padding:4px 11px;border-radius:14px;font-size:12px;font-weight:600;
  color:#fff;white-space:nowrap;line-height:1.35}
.etiq{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:11px;
  background:var(--bordure);color:var(--gris);margin:0 4px 3px 0;white-space:nowrap}
.etiq.att{background:var(--rouge-voile);color:var(--rouge)}
.etiq.ok{background:var(--vert-voile);color:#00875A}
.etiq.bleu{background:var(--bleu-voile);color:#0060B9}
.avatar{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;
  border-radius:50%;color:#fff;font-size:10.5px;font-weight:700;flex:none}
.acteur{display:inline-flex;align-items:center;gap:9px;white-space:nowrap}
.avert{background:var(--rouge-voile);border-left:4px solid var(--rouge);border-radius:4px;
  padding:11px 14px;margin-bottom:9px;font-size:13.5px;color:var(--encre)}
.avert.sereine{background:var(--vert-voile);border-left-color:var(--vert)}
.legende{display:flex;flex-wrap:wrap;gap:7px 18px;margin-top:14px;font-size:12.5px;color:var(--gris)}
.pastille{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px}
.legende b{color:var(--encre);font-weight:600;font-variant-numeric:tabular-nums}
.colonnes{display:grid;grid-template-columns:repeat(auto-fit,minmax(208px,1fr));gap:14px}
.colonne{border:1px solid;border-radius:8px;overflow:hidden}
.colonne-t{color:#fff;font-size:12.5px;font-weight:700;padding:7px 12px}
.colonne-c{padding:10px;display:flex;flex-direction:column;gap:8px}
.fiche{background:#fff;border-radius:6px;padding:9px 11px;box-shadow:0 1px 2px rgba(0,0,0,.06)}
.fiche-t{font-size:12.5px;font-weight:600;line-height:1.3}
.fiche-s{font-size:11.5px;color:var(--gris);margin-top:3px}
.fiche-plus{font-size:11.5px;color:var(--gris);padding:2px}
.pied{margin-top:26px;font-size:12.5px;color:var(--gris-clair);max-width:84ch}
@media(max-width:880px){.duo,.duo-haut{grid-template-columns:1fr}}
@media print{body{background:#fff}.page{padding:0}
  section,.bloc{box-shadow:none;border:1px solid #E6E9EF;break-inside:avoid}}
"""


# --------------------------------------------------------------------------
# fragments
# --------------------------------------------------------------------------

def _initiales(nom: str) -> str:
    mots = [m for m in str(nom or "").split() if m]
    if not mots:
        return "?"
    return (mots[0][0] + (mots[-1][0] if len(mots) > 1 else "")).upper()


def _couleur_de(nom: str) -> str:
    return COULEURS_AVATAR[sum(ord(c) for c in str(nom or "")) % len(COULEURS_AVATAR)]


def _avatar(nom: str) -> str:
    return (f'<span class="avatar" style="background:{_couleur_de(nom)}" aria-hidden="true">'
            f'{_e(_initiales(nom))}</span>')


def _acteur(nom: str) -> str:
    return f'<span class="acteur">{_avatar(nom)}<span>{_e(nom)}</span></span>'


def _avatar_svg(nom: str, x: float, y: float) -> str:
    return (f'<circle cx="{x + 13}" cy="{y + 11}" r="11" fill="{_couleur_de(nom)}"/>'
            f'<text x="{x + 13}" y="{y + 15}" text-anchor="middle" font-size="9.5" '
            f'font-weight="700" fill="#FFFFFF" font-family="inherit">{_e(_initiales(nom))}</text>')


def _pilule(libelle: str, couleur: str) -> str:
    return f'<span class="pilule" style="background:{couleur or PALETTE_DEFAUT}">{_e(libelle)}</span>'


def _table(entetes, lignes, pied=None) -> str:
    th = "".join('<th{}>{}</th>'.format(' class="num"' if n else "", _e(t)) for t, n in entetes)
    corps = "".join(lignes) or (
        f'<tr><td colspan="{len(entetes)}" style="color:#9699A6;padding:24px 10px;'
        'text-align:center">Aucune ligne sur ce périmètre.</td></tr>')
    return (f"<table><thead><tr>{th}</tr></thead><tbody>{corps}</tbody>"
            + (f"<tfoot>{pied}</tfoot>" if pied else "") + "</table>")


# --------------------------------------------------------------------------
# graphiques
# --------------------------------------------------------------------------

def _camembert(parts, centre_haut: str, centre_bas: str) -> str:
    """Anneau proportionnel. parts : liste de (libellé, valeur, couleur)."""
    total = sum(v for _, v, _ in parts)
    if total <= 0:
        return ('<div style="height:190px;display:flex;align-items:center;justify-content:center;'
                'color:#9699A6;font-size:13px">Aucune heure imputée.</div>')
    rayon, epaisseur = 70, 26
    circonference = 2 * 3.141592653589793 * rayon
    arcs, offset = [], 0.0
    for libelle, valeur, couleur in parts:
        portion = valeur / total * circonference
        arcs.append(
            f'<circle cx="100" cy="100" r="{rayon}" fill="none" '
            f'stroke="{couleur or PALETTE_DEFAUT}" stroke-width="{epaisseur}" '
            f'stroke-dasharray="{max(portion - 1.5, 0):.2f} {circonference - portion + 1.5:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 100 100)">'
            f'<title>{_e(libelle)} : {_h(valeur)}</title></circle>')
        offset += portion
    return (
        '<svg viewBox="0 0 200 200" width="100%" height="190" role="img" '
        'aria-label="Répartition des heures par type de tâche">' + "".join(arcs) +
        f'<text x="100" y="95" text-anchor="middle" font-size="25" font-weight="700" '
        f'fill="#323338" font-family="inherit">{_e(centre_haut)}</text>'
        f'<text x="100" y="116" text-anchor="middle" font-size="11" fill="#676879" '
        f'font-family="inherit">{_e(centre_bas)}</text></svg>')


def _barres_empilees(mois, sequences) -> str:
    """Histogramme mensuel empilé. sequences : [{libelle, couleur, valeurs:{mois: heures}}]."""
    if not mois or not sequences:
        return ""
    largeur, hauteur, bas, haut = 940, 220, 194, 16
    maxi = max((sum(s["valeurs"].get(m, 0) for s in sequences) for m in mois), default=0) or 1
    pas = largeur / len(mois)
    barre = min(pas * 0.6, 46)
    reperes, rects, socles = [], [], []
    for fraction in (0, 0.5, 1):
        y = bas - (bas - haut) * fraction
        reperes.append(
            f'<line x1="0" y1="{y:.1f}" x2="{largeur}" y2="{y:.1f}" stroke="#E6E9EF" '
            f'stroke-width="1"/><text x="0" y="{y - 5:.1f}" font-size="10" fill="#9699A6" '
            f'font-family="inherit">{_n(maxi * fraction, 0)} h</text>')
    for i, m in enumerate(mois):
        x = i * pas + (pas - barre) / 2
        cumul = 0.0
        for seq in sequences:
            valeur = seq["valeurs"].get(m, 0)
            if valeur <= 0:
                continue
            h = valeur / maxi * (bas - haut)
            cumul += h
            rects.append(
                f'<rect x="{x:.1f}" y="{bas - cumul:.1f}" width="{barre:.1f}" '
                f'height="{max(h - 1.5, 1):.1f}" fill="{seq["couleur"] or PALETTE_DEFAUT}" rx="2">'
                f'<title>{_e(_mois_fr(m))}, {_e(seq["libelle"])} : {_h(valeur)}</title></rect>')
        socles.append(
            f'<text x="{x + barre / 2:.1f}" y="{hauteur - 7}" text-anchor="middle" '
            f'font-size="10.5" fill="#676879" font-family="inherit">'
            f'{m.split("-")[1]}/{m.split("-")[0][2:]}</text>')
    return (f'<svg viewBox="0 0 {largeur} {hauteur}" width="100%" height="{hauteur}" role="img" '
            f'aria-label="Heures imputées par mois et par type de tâche">'
            + "".join(reperes) + "".join(rects) + "".join(socles) + "</svg>")


def _frise(lignes, premier, dernier) -> str:
    """Frise : une barre par acteur, de sa première à sa dernière journée déclarée.

    lignes : [(nom, date_debut, date_fin, heures)].
    """
    if not lignes or dernier < premier:
        return ""
    hauteur_ligne, largeur, marge, droite = 38, 940, 186, 24
    utile = largeur - marge - droite
    hauteur = hauteur_ligne * len(lignes) + 36
    etendue = (dernier - premier).days or 1

    reperes = []
    annee, mois = premier.year, premier.month
    while date(annee, mois, 1) <= dernier:
        borne = date(annee, mois, 1)
        if borne >= premier:
            x = marge + (borne - premier).days / etendue * utile
            reperes.append(
                f'<line x1="{x:.1f}" y1="26" x2="{x:.1f}" y2="{hauteur - 8}" stroke="#E6E9EF" '
                f'stroke-width="1"/><text x="{x:.1f}" y="18" text-anchor="middle" font-size="10" '
                f'fill="#9699A6" font-family="inherit">{borne.strftime("%m/%y")}</text>')
        mois += 1
        if mois == 13:
            mois, annee = 1, annee + 1

    barres = []
    for i, (nom, debut, fin, valeur) in enumerate(lignes):
        y = 34 + i * hauteur_ligne
        x1 = marge + (debut - premier).days / etendue * utile
        x2 = marge + (fin - premier).days / etendue * utile
        large = max(x2 - x1, 56)
        barres.append(
            f'<g>{_avatar_svg(nom, 2, y + 1)}'
            f'<text x="32" y="{y + 17}" font-size="12.5" fill="#323338" font-family="inherit">'
            f'{_e(nom[:20])}</text>'
            f'<rect x="{x1:.1f}" y="{y + 2}" width="{large:.1f}" height="20" rx="10" '
            f'fill="{_couleur_de(nom)}"><title>{_e(nom)} : {_h(valeur)}, du '
            f'{debut.strftime("%d/%m/%Y")} au {fin.strftime("%d/%m/%Y")}</title></rect>'
            f'<text x="{x1 + 11:.1f}" y="{y + 16}" font-size="11" fill="#FFFFFF" '
            f'font-weight="600" font-family="inherit">{_h(valeur)}</text></g>')
    return (f'<svg viewBox="0 0 {largeur} {hauteur}" width="100%" height="{hauteur}" role="img" '
            f"aria-label=\"Période d'activité de chaque acteur\">"
            + "".join(reperes) + "".join(barres) + "</svg>")


def _rubans(lignes, maxi) -> str:
    """Barres horizontales comparant les acteurs. lignes : [(nom, valeur)]."""
    if not lignes:
        return ""
    hauteur_ligne, largeur, marge = 32, 940, 240
    hauteur = hauteur_ligne * len(lignes) + 8
    elements = []
    for i, (nom, valeur) in enumerate(lignes):
        y = i * hauteur_ligne + 6
        w = (valeur / (maxi or 1)) * (largeur - marge - 100)
        elements.append(
            f'<text x="0" y="{y + 15}" font-size="12.5" fill="#323338" font-family="inherit">'
            f'{_e(nom[:36])}</text>'
            f'<rect x="{marge}" y="{y + 3}" width="{max(w, 2):.1f}" height="16" rx="8" '
            f'fill="{_couleur_de(nom)}"><title>{_e(nom)} : {_h(valeur)}</title></rect>'
            f'<text x="{marge + max(w, 2) + 9:.1f}" y="{y + 16}" font-size="11.5" fill="#676879" '
            f'font-family="inherit">{_h(valeur)}</text>')
    return (f'<svg viewBox="0 0 {largeur} {hauteur}" width="100%" height="{hauteur}" role="img" '
            f'aria-label="Heures imputées par acteur">' + "".join(elements) + "</svg>")


def _colonnes_etat(colonnes) -> str:
    """Colonnes colorées, une par état de validation.

    colonnes : [(titre, couleur, voile, [(titre_fiche, sous_titre)], total)].
    """
    blocs = []
    for titre, couleur, voile, fiches, total in colonnes:
        cartes = "".join(
            f'<div class="fiche"><div class="fiche-t">{_e(t)}</div>'
            f'<div class="fiche-s">{_e(sous)}</div></div>' for t, sous in fiches[:4])
        if not cartes:
            cartes = '<div class="fiche-plus">Rien dans cet état.</div>'
        reste = ""
        if total > 4:
            reste = (f'<div class="fiche-plus">et {total - 4} autre'
                     f'{"s" if total - 4 > 1 else ""}</div>')
        blocs.append(
            f'<div class="colonne" style="background:{voile};border-color:{couleur}">'
            f'<div class="colonne-t" style="background:{couleur}">{_e(titre)} / {total}</div>'
            f'<div class="colonne-c">{cartes}{reste}</div></div>')
    return f'<div class="colonnes">{"".join(blocs)}</div>'


# --------------------------------------------------------------------------
# composition
# --------------------------------------------------------------------------

def construire(projet, donnees, personne=None, alertes=None, confidentiel_couts=False):
    """Assemble le tableau de bord.

    personne None produit la version consolidée destinée au financeur.
    confidentiel_couts masque les montants, cas d'un contributeur.
    """
    devise = projet.devise
    hj = projet.heures_jour or 7.0
    activites = donnees["activites"]
    depenses = donnees["depenses"]
    types = donnees["types"]
    categories = donnees["categories"]
    noms_pers = donnees["noms_personnes"]

    couleur_type = {t.id: t.couleur or PALETTE_DEFAUT for t in types}
    libelle_type = {t.id: t.libelle for t in types}

    par_type = defaultdict(lambda: {"n": 0, "h": 0.0, "hi": 0.0, "c": 0.0})
    par_personne = defaultdict(lambda: {"n": 0, "hi": 0.0, "c": 0.0})
    par_mois = defaultdict(lambda: {"hi": 0.0, "c": 0.0, "d": 0.0})
    par_mois_type = defaultdict(lambda: defaultdict(float))
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
        par_mois[cle]["hi"] += a.heures_imputees
        par_mois[cle]["c"] += a.cout
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
        par_mois[d.date.strftime("%Y-%m")]["d"] += d.montant

    total_h = sum(a.heures for a in activites)
    total_hi = sum(a.heures_imputees for a in activites)
    total_cout = sum(a.cout for a in activites)
    total_dep = sum(d.montant for d in depenses)
    total_dep_j = sum(d.montant for d in depenses if d.statut == "mesure")

    source = [a for a in activites if getattr(a, "mesuree_a_la_source", a.statut == "mesure")]
    validees = [a for a in activites if getattr(a, "validee", False)]
    attente = [a for a in activites if a.statut == "estime"]
    arbitrer = [a for a in activites
                if (a.mixte and float(a.part_imputable) >= 100) or a.heures <= 0
                or (a.date_theorique and a.date_theorique != a.date)]
    h_source = sum(a.heures_imputees for a in source)
    h_validees = sum(a.heures_imputees for a in validees)
    h_attente = sum(a.heures_imputees for a in attente)

    titre = personne.nom if personne else projet.intitule
    sous_titre = ("Relevé individuel des temps et dépenses"
                  if personne else "Récapitulatif consolidé des temps et dépenses")

    # ---------- bandeau ----------
    blocs = [
        (_h(total_hi), f"heures imputées, sur {_h(total_h)} enregistrées"),
        (_n(total_hi / hj), f"jours-homme à {_n(hj, 1)} h"),
    ]
    if not personne:
        blocs.append((str(len(par_personne)), "acteurs déclarés"))
    if not confidentiel_couts:
        blocs.append((_m(total_cout, devise), "coût de main d'œuvre"))
        blocs.append((_m(total_dep, devise), "dépenses techniques"))
    blocs.append(((_n(h_source / total_hi * 100, 0) + " %") if total_hi else "0 %",
                  "des heures mesurées à la source, hors validation"))
    bandeau = "".join(f'<div class="bloc"><div class="v">{v}</div><div class="l">{l}</div></div>'
                      for v, l in blocs)

    sections = []

    # ---------- frise et total ----------
    if activites:
        lignes_frise = [(noms_pers.get(pid, {}).get("nom", ""), d0, d1, par_personne[pid]["hi"])
                        for pid, (d0, d1) in sorted(bornes.items(), key=lambda kv: kv[1][0])]
        dates = [a.date for a in activites]
        frise = _frise(lignes_frise, min(dates), max(dates))
        if confidentiel_couts:
            encadre = (f'<section><h3>Effort déclaré</h3>'
                       f'<div class="grand">{_n(total_hi / hj)}</div>'
                       f'<div style="font-size:12.5px;color:#676879">jours-homme à {_n(hj, 1)} h, '
                       f'soit {_h(total_hi)} imputées.</div></section>')
        else:
            encadre = (f'<section><h3>Total engagé à date</h3>'
                       f'<div class="grand">{_m(total_cout + total_dep, devise)}</div>'
                       f'<div style="font-size:12.5px;color:#676879">'
                       f"{_m(total_cout, devise)} de main d'œuvre et {_m(total_dep, devise)} de "
                       f'dépenses techniques, dont {_m(total_dep_j, devise)} justifiées par une '
                       f'pièce.</div></section>')
        if frise:
            sections.append(f'<div class="duo-haut">'
                            f"<section><h2>Période d'activité par acteur</h2>{frise}</section>"
                            f'{encadre}</div>')
        else:
            sections.append(encadre)

    # ---------- colonnes d'état ----------
    def fiche(a):
        sous = f'{a.date.strftime("%d/%m/%Y")} · {_h(a.heures_imputees)}'
        if not personne:
            sous += " · " + noms_pers.get(a.personne_id, {}).get("nom", "")
        return (a.libelle[:58], sous)

    colonnes = [
        ("Mesuré à la source", "#00C875", "#E3F7ED",
         [fiche(a) for a in sorted(source, key=lambda x: x.date)], len(source)),
        ("Retenu par validation", "#0073EA", "#E5F1FE",
         [fiche(a) for a in sorted(validees, key=lambda x: x.date)], len(validees)),
        ("En attente de validation", "#FDAB3D", "#FFF3E2",
         [fiche(a) for a in sorted(attente, key=lambda x: x.date)], len(attente)),
        ("À arbitrer", "#E2445C", "#FCE9EC",
         [fiche(a) for a in sorted(arbitrer, key=lambda x: x.date)], len(arbitrer)),
    ]
    sections.append(
        "<section><h2>État des lignes de temps</h2>"
        "<p>Une durée mesurée à la source et une durée retenue après validation comptent toutes "
        "deux dans le récapitulatif, mais ne se valent pas : la seconde reste un arbitrage, et "
        f"son origine estimée demeure inscrite sur chaque ligne. {_h(h_source)} relèvent de la "
        f"première, {_h(h_validees)} de la seconde, {_h(h_attente)} restent en attente.</p>"
        f"{_colonnes_etat(colonnes)}</section>")

    # ---------- anneau et histogramme ----------
    parts = [(libelle_type.get(tid, "Non classé"), vals["hi"], couleur_type.get(tid, PALETTE_DEFAUT))
             for tid, vals in sorted(par_type.items(), key=lambda kv: -kv[1]["hi"]) if vals["hi"] > 0]
    legende = "".join(
        f'<span><span class="pastille" style="background:{c}"></span>{_e(l)} '
        f'<b>{_h(v)}</b> <span style="color:#9699A6">'
        f'{_n(v / total_hi * 100, 0) if total_hi else 0} %</span></span>'
        for l, v, c in parts)
    mois = sorted(k for k in par_mois if k)
    sequences = [{"libelle": libelle_type.get(t.id, ""), "couleur": couleur_type.get(t.id),
                  "valeurs": dict(par_mois_type[t.id])}
                 for t in types if t.id in par_mois_type]
    histogramme = _barres_empilees(mois, sequences) or \
        '<p style="margin:0">Aucune donnée mensuelle sur ce périmètre.</p>'
    sections.append(
        f'<div class="duo"><section><h2>Répartition de l\'effort</h2>'
        f'{_camembert(parts, _n(total_hi / hj, 1), "jours-homme")}'
        f'<div class="legende">{legende}</div></section>'
        f'<section><h2>Charge mensuelle par type de tâche</h2>{histogramme}</section></div>')

    # ---------- tableau par type ----------
    entetes_type = [("Type de tâche", False), ("Lignes", True), ("Heures", True),
                    ("Imputées", True)] + ([] if confidentiel_couts else [("Coût", True)])
    lignes_type = []
    for tid, v in sorted(par_type.items(), key=lambda kv: -kv[1]["hi"]):
        cellule = "" if confidentiel_couts else f'<td class="num">{_m(v["c"], devise)}</td>'
        lignes_type.append(
            f'<tr><td>{_pilule(libelle_type.get(tid, "Non classé"), couleur_type.get(tid))}</td>'
            f'<td class="num">{v["n"]}</td><td class="num">{_h(v["h"])}</td>'
            f'<td class="num">{_h(v["hi"])}</td>{cellule}</tr>')
    pied_type = (f'<tr><th>Total</th><th class="num">{len(activites)}</th>'
                 f'<th class="num">{_h(total_h)}</th><th class="num">{_h(total_hi)}</th>'
                 + ("" if confidentiel_couts else f'<th class="num">{_m(total_cout, devise)}</th>')
                 + "</tr>")
    sections.append("<section><h2>Détail par type de tâche</h2>"
                    f"{_table(entetes_type, lignes_type, pied_type)}</section>")

    # ---------- acteurs ----------
    if not personne:
        classement = sorted(par_personne.items(), key=lambda kv: -kv[1]["hi"])
        maxi = classement[0][1]["hi"] if classement else 0
        rubans = _rubans([(noms_pers.get(pid, {}).get("nom", ""), v["hi"])
                          for pid, v in classement], maxi)
        entetes_p = [("Acteur", False), ("Organisation", False), ("Lignes", True),
                     ("Heures imputées", True), ("Jours-homme", True)] + \
                    ([] if confidentiel_couts else [("Taux horaire", True), ("Coût", True)])
        lignes_p = []
        for pid, v in classement:
            info = noms_pers.get(pid, {})
            sup = ""
            if not confidentiel_couts:
                taux = info.get("taux", 0)
                sup = (f'<td class="num">{_m(taux, devise) if taux else "à renseigner"}</td>'
                       f'<td class="num">{_m(v["c"], devise)}</td>')
            marque = "" if info.get("imputable", True) else ' <span class="etiq">non imputable</span>'
            lignes_p.append(
                f'<tr><td>{_acteur(info.get("nom", ""))}{marque}</td>'
                f'<td style="color:#676879">{_e(info.get("organisation", ""))}</td>'
                f'<td class="num">{v["n"]}</td><td class="num">{_h(v["hi"])}</td>'
                f'<td class="num">{_n(v["hi"] / hj)}</td>{sup}</tr>')
        pied_p = (f'<tr><th>Total</th><th></th><th class="num">{len(activites)}</th>'
                  f'<th class="num">{_h(total_hi)}</th><th class="num">{_n(total_hi / hj)}</th>'
                  + ("" if confidentiel_couts else
                     f'<th></th><th class="num">{_m(total_cout, devise)}</th>') + "</tr>")
        sections.append(f"<section><h2>Contribution par acteur</h2>{rubans}"
                        f'<div style="margin-top:18px">{_table(entetes_p, lignes_p, pied_p)}'
                        f"</div></section>")

    # ---------- dépenses ----------
    if depenses and not confidentiel_couts:
        libelle_cat = {c.id: c.libelle for c in categories}
        couleur_cat = {c.id: c.couleur or PALETTE_DEFAUT for c in categories}
        lignes_c = [
            f'<tr><td>{_pilule(libelle_cat.get(cid, "Non classée"), couleur_cat.get(cid))}</td>'
            f'<td class="num">{v["n"]}</td><td class="num">{_m(v["m"], devise)}</td>'
            f'<td class="num">{_m(v["j"], devise)}</td>'
            f'<td class="num">{_m(v["m"] - v["j"], devise)}</td></tr>'
            for cid, v in sorted(par_categorie.items(), key=lambda kv: -kv[1]["m"])]
        pied_c = (f'<tr><th>Total</th><th class="num">{len(depenses)}</th>'
                  f'<th class="num">{_m(total_dep, devise)}</th>'
                  f'<th class="num">{_m(total_dep_j, devise)}</th>'
                  f'<th class="num">{_m(total_dep - total_dep_j, devise)}</th></tr>')
        sections.append(
            "<section><h2>Dépenses techniques</h2>"
            + _table([("Catégorie", False), ("Lignes", True), ("Montant", True),
                      ("Justifié", True), ("Estimé", True)], lignes_c, pied_c)
            + "</section>")

    # ---------- détail ----------
    lignes_d = []
    for a in sorted(activites, key=lambda x: x.date):
        etiquettes = []
        if a.mixte:
            etiquettes.append('<span class="etiq att">mixte</span>')
        if a.statut == "estime":
            etiquettes.append('<span class="etiq">en attente de validation</span>')
        if getattr(a, "validee", False):
            signataire = ""
            if getattr(a, "valide_par", None):
                signataire = a.valide_par.nom or a.valide_par.email
            etiquettes.append(
                '<span class="etiq bleu">validée le ' + a.valide_le.strftime("%d/%m/%Y")
                + (f", {_e(signataire)}" if signataire else "") + "</span>")
        if a.date_theorique and a.date_theorique != a.date:
            etiquettes.append('<span class="etiq att">reportée du '
                              f'{a.date_theorique.strftime("%d/%m/%Y")}</span>')
        if a.source == "declaratif":
            etiquettes.append('<span class="etiq">déclaratif</span>')
        horaire = f"{a.heure_debut} – {a.heure_fin}" if a.heure_debut and a.heure_fin else ""
        colonne_acteur = "" if personne else \
            f'<td>{_acteur(noms_pers.get(a.personne_id, {}).get("nom", ""))}</td>'
        colonne_cout = "" if confidentiel_couts else f'<td class="num">{_m(a.cout, devise)}</td>'
        lignes_d.append(
            f'<tr><td class="num">{a.date.strftime("%d/%m/%Y")}</td>'
            f'<td class="num" style="color:#9699A6">{_e(horaire)}</td>'
            f'<td>{_e(a.libelle)}'
            + (f'<br><span style="font-size:12px;color:#9699A6">{_e(a.note)}</span>' if a.note else "")
            + (f'<br>{"".join(etiquettes)}' if etiquettes else "") + "</td>"
            f'<td>{_pilule(libelle_type.get(a.type_tache_id, ""), couleur_type.get(a.type_tache_id))}</td>'
            + colonne_acteur
            + f'<td class="num">{_h(a.heures)}</td>'
              f'<td class="num">{_n(a.part_imputable, 0)} %</td>'
              f'<td class="num">{_h(a.heures_imputees)}</td>{colonne_cout}</tr>')
    entetes_d = [("Date", True), ("Horaires", True), ("Libellé", False), ("Type", False)] + \
                ([] if personne else [("Acteur", False)]) + \
                [("Durée", True), ("Part", True), ("Imputé", True)] + \
                ([] if confidentiel_couts else [("Coût", True)])
    sections.append("<section><h2>Détail des lignes de temps</h2>"
                    f"{_table(entetes_d, lignes_d)}</section>")

    # ---------- réserves ----------
    if alertes:
        items = "".join(f'<div class="avert">{_e(a["texte"])}</div>' for a in alertes)
        sections.append(
            "<section><h2>Points à arbitrer</h2>"
            "<p>Ces réserves accompagnent le récapitulatif plutôt qu'elles ne le contredisent : "
            "les signaler est la condition pour que le reste soit tenu pour fiable.</p>"
            f"{items}</section>")
    elif not personne:
        sections.append('<section><h2>Points à arbitrer</h2>'
                        '<div class="avert sereine">Aucune zone grise détectée sur ce périmètre.'
                        "</div></section>")

    horodatage = datetime.now().strftime("%d/%m/%Y à %H:%M")
    periode = f"{projet.date_debut.strftime('%d/%m/%Y')} au {projet.date_fin.strftime('%d/%m/%Y')}"
    financeur = f" Financement : {_e(projet.financeur)}." if projet.financeur else ""

    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(sous_titre)} – {_e(titre)}</title>
<style>{CSS}</style></head>
<body><div class="page">
<header class="une">
  <div class="marque">
    <span style="background:#0073EA"></span><span style="background:#00C875"></span>
    <span style="background:#FDAB3D"></span><span style="background:#E2445C"></span>
    <span style="background:#A25DDC"></span>
  </div>
  <h3>{_e(projet.intitule)}</h3>
  <h1>{_e(titre)}</h1>
  <div class="filet">{_e(sous_titre)}. Période du {periode}.{financeur}
  Document établi le {horodatage}.</div>
</header>
<div class="bandeau">{bandeau}</div>
{''.join(sections)}
<div class="pied">
  Les heures imputées résultent de la durée déclarée multipliée par la part affectée au projet.
  Une durée mesurée à la source est distinguée d'une durée retenue par validation, et chaque
  dépense indique si une pièce justificative lui est rattachée. Document généré par l'outil de
  suivi des temps et dépenses, sans retraitement manuel.
</div>
</div></body></html>"""
