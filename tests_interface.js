/* Contrôle de l'interface sans navigateur.
 *
 * Le script de la page est exécuté dans un DOM factice, puis toutes les fonctions
 * de rendu sont appelées sur un état représentatif. Une fonction appelée mais non
 * définie, ou un champ absent de l'état, échoue ici plutôt que dans la page.
 */
const fs = require("fs");
const vm = require("vm");

const page = fs.readFileSync("app/static/index.html", "utf8");
const script = page.split("<script>")[1].split("</script>")[0];

/* ---------- DOM factice ---------- */
function element(id) {
  const el = {
    id, innerHTML: "", value: "", textContent: "", checked: false,
    style: {}, dataset: {}, options: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, setAttribute() {}, getAttribute() { return null; },
    appendChild() {}, removeChild() {}, click() {}, focus() {},
    querySelectorAll() { return []; }, querySelector() { return null; },
  };
  return el;
}
const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  addEventListener() {},
  createElement(t) { return element(t); },
  body: element("body"),
};

const contexte = {
  document,
  window: { scrollTo() {}, print() {}, open() {}, location: { href: "" } },
  console,
  alert() {}, confirm() { return false; },
  fetch() { return Promise.reject(new Error("réseau coupé dans ce contrôle")); },
  setTimeout, clearTimeout, Intl, Date, Math, JSON, Promise, Set, Map, URL,
};
contexte.globalThis = contexte;

/* ---------- état représentatif, calqué sur ce que sert l'API ---------- */
const harnais = `
E = {
  projet: {id:1, code:"DEXTER4LLM", intitule:"DEXTER4LLM Lot 3", financeur:"BPI France",
    date_debut:"2025-06-01", date_fin:"2026-09-30", devise:"EUR", heures_jour:7,
    taux_defaut:0, actif:true, role:"gestionnaire"},
  droits:{pilote:true, restreint:false, lecture_seule:false, admin:true, personne_id:1},
  types:[{id:1,code:"gouv",libelle:"Comité",couleur:"#0073EA",ordre:0},
         {id:2,code:"travail",libelle:"Recherche",couleur:"#FDAB3D",ordre:1}],
  categories:[{id:1,code:"calcul",libelle:"Calcul GPU",couleur:"#E2445C",ordre:0}],
  personnes:[{id:1,nom:"GANS COMBE Caroline",organisation:"ECE",role:"Lead",
              taux_horaire:85,imputable:true,note:""},
             {id:2,nom:"BHUYAN Bikram Pratim",organisation:"ECE",role:"Chercheur",
              taux_horaire:0,imputable:true,note:""}],
  activites:[
    {id:1,date:"2026-06-10",date_theorique:null,reportee:false,heure_debut:"08:30",
     heure_fin:"12:45",duree_h:null,libelle:"Comité de pilotage",livrable:"",
     part_imputable:100,source:"agenda",statut:"mesure",mixte:false,note:"",
     type_tache_id:1,personne_id:1,recurrence_id:null,heures:4.25,heures_imputees:4.25,
     cout:361.25,validee:false,valide_le:null,valide_par:null,origine_estimee:false,
     mesuree_a_la_source:true},
    {id:2,date:"2026-06-10",date_theorique:null,reportee:false,heure_debut:"09:00",
     heure_fin:"12:00",duree_h:null,libelle:"Comité de coordination",livrable:"L3.6",
     part_imputable:100,source:"agenda",statut:"mesure",mixte:false,note:"",
     type_tache_id:1,personne_id:1,recurrence_id:null,heures:3,heures_imputees:3,
     cout:255,validee:false,valide_le:null,valide_par:null,origine_estimee:false,
     mesuree_a_la_source:true},
    {id:3,date:"2026-05-04",date_theorique:"2026-05-01",reportee:true,heure_debut:"",
     heure_fin:"",duree_h:7,libelle:"Journée de recherche",livrable:"",
     part_imputable:0,source:"declaratif",statut:"estime",mixte:false,note:"neutralisée",
     type_tache_id:2,personne_id:2,recurrence_id:1,heures:7,heures_imputees:0,cout:0,
     validee:false,valide_le:null,valide_par:null,origine_estimee:false,
     mesuree_a_la_source:false},
    {id:4,date:"2025-06-02",date_theorique:"2025-06-02",reportee:false,heure_debut:"",
     heure_fin:"",duree_h:7,libelle:"Journée de recherche",livrable:"",
     part_imputable:100,source:"declaratif",statut:"mesure",mixte:false,note:"",
     type_tache_id:2,personne_id:1,recurrence_id:1,heures:7,heures_imputees:7,cout:595,
     validee:true,valide_le:"2026-09-12T10:30",valide_par:"GANS COMBE Caroline",
     origine_estimee:true,mesuree_a_la_source:false}],
  depenses:[{id:1,date:"2026-05-13",libelle:"Colab L4",quantite:4,unite:"heure-GPU",
    cout_unitaire:85,statut:"mesure",reference:"relevé",note:"",categorie_id:1,
    personne_id:1,montant:340}],
  recurrences:[{id:1,libelle:"Journée de recherche",jour_semaine:0,rang:1,
    regle:"premier lundi du mois",date_debut:"2025-06-01",date_fin:"2026-02-28",
    duree_h:7,part_imputable:100,heure_debut:"",heure_fin:"",statut:"estime",
    source:"declaratif",livrable:"",note:"",active:true,reporter:true,
    type_tache_id:2,personne_id:1,occurrences:9}],
  doublons:[{date:"2026-06-10",personne_id:1,ids:[1,2],heures_cumulees:7.25,
    heures_retenues:4.25}],
  recapitulatif:{
    totaux:{heures:21.25,imputees:14.25,jours_homme:2.04,part_mesuree:100,
      heures_validees:7,heures_mesurees_source:7.25,heures_estimees:0,
      heures_a_valider:0,lignes_a_valider:0,cout_main_oeuvre:1211.25,depenses:340,
      depenses_justifiees:340,total:1551.25,acteurs:2},
    par_type:[{id:1,libelle:"Comité",couleur:"#0073EA",n:2,heures:7.25,imputees:7.25,cout:616.25},
              {id:2,libelle:"Recherche",couleur:"#FDAB3D",n:2,heures:14,imputees:7,cout:595}],
    par_personne:[{id:1,nom:"GANS COMBE Caroline",organisation:"ECE",imputable:true,
      n:3,imputees:14.25,cout:1211.25,jours_homme:2.04},
      {id:2,nom:"BHUYAN Bikram Pratim",organisation:"ECE",imputable:true,
      n:1,imputees:0,cout:0,jours_homme:0}],
    par_categorie:[{id:1,libelle:"Calcul GPU",couleur:"#E2445C",n:1,montant:340,justifie:340}],
    par_mois:[{mois:"2025-06",n:1,imputees:7,cout:595,depenses:0},
              {mois:"2026-06",n:2,imputees:7.25,cout:616.25,depenses:0}],
    alertes:[{type:"collision",texte:"Recouvrement le 10/06/2026."}]}
};
PROJET_ID = 1;
MOI = {id:1, email:"c@ece.fr", nom:"Caroline", role_global:"admin", actif:true,
       doit_changer:false};
PROJETS = [E.projet];
ADMIN = {utilisateurs:[{...MOI, acces:[{id:1,projet_id:1,projet:"DEXTER4LLM Lot 3",
           role:"gestionnaire",personne_id:1,personne:"GANS COMBE Caroline"}]}],
         projets:[{...E.projet, personnes:E.personnes, synthese:{lignes:4,imputees:14.25,
           jours_homme:2.04,cout:1211.25,depenses:340,total:1551.25,acteurs:2,comptes:1}}],
         roles:["gestionnaire","contributeur","lecteur"]};

var RESULTATS = [];
function essai(nom, fn){
  try { fn(); RESULTATS.push(["ok", nom]); }
  catch (e) { RESULTATS.push(["ECHEC", nom + " : " + e.message]); }
}
essai("remplirSelects", () => remplirSelects());
essai("rendreEntete", () => rendreEntete());
essai("rendreRecap", () => rendreRecap());
essai("rendreTemps", () => rendreTemps());
essai("rendreDoublons", () => rendreDoublons());
essai("rendreBandeauValidation", () => rendreBandeauValidation(E.activites));
essai("rendreRec", () => rendreRec());
essai("rendreDep", () => rendreDep());
essai("rendrePers", () => rendrePers());
essai("rendreReglages", () => rendreReglages());
essai("rendre (enchaînement complet)", () => rendre());
essai("resetAct", () => resetAct());
essai("resetDep", () => resetDep());
essai("resetPers", () => resetPers());
essai("resetRec", () => resetRec());
essai("rendreAdmin", () => rendreAdmin());
essai("litAct", () => litAct());
essai("litDep", () => litDep());
essai("litRec", () => litRec());

// le rendu de la table doit produire des lignes et signaler le recouvrement
essai("la table contient les lignes et signale le recouvrement", () => {
  rendreTemps();
  const html = document.getElementById("tAct").innerHTML;
  if (!html.includes("Comité de pilotage")) throw new Error("table vide");
  if (!html.includes("recouvrement")) throw new Error("recouvrement non signalé");
  if (!html.includes("col-outils")) throw new Error("colonne d'actions absente");
  if (!html.includes("neutralisée")) throw new Error("ligne neutralisée non marquée");
});
essai("le panneau d'arbitrage propose de retenir une ligne", () => {
  rendreDoublons();
  const html = document.getElementById("panneauDoublons").innerHTML;
  if (!html.includes("data-garder")) throw new Error("aucun bouton de choix");
  if (!html.includes("Recouvrements à trancher")) throw new Error("titre absent");
});
`;

vm.createContext(contexte);
try {
  vm.runInContext(script + "\n" + harnais, contexte, { filename: "index.html" });
} catch (e) {
  console.log("ÉCHEC  chargement du script : " + e.message);
  process.exit(1);
}

const resultats = contexte.RESULTATS || [];
let echecs = 0;
for (const [etat, nom] of resultats) {
  if (etat !== "ok") echecs++;
  console.log((etat === "ok" ? "ok     " : "ÉCHEC  ") + nom);
}
console.log();
console.log(echecs ? echecs + " contrôle(s) en échec." : "Toutes les fonctions de rendu s'exécutent.");
process.exit(echecs ? 1 : 0);
