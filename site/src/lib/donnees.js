// Lecture des JSON produits par le pipeline Python (au moment du build uniquement).
import fs from "node:fs";
import path from "node:path";

const RACINE = path.join(process.cwd(), "src", "donnees");
const cache = new Map();

export function lire(cid, fichier) {
  const cle = `${cid}/${fichier}`;
  if (!cache.has(cle)) {
    const chemin = path.join(RACINE, cid, fichier);
    cache.set(cle, fs.existsSync(chemin) ? JSON.parse(fs.readFileSync(chemin, "utf-8")) : null);
  }
  return cache.get(cle);
}

/** Compétitions disponibles (un dossier par compétition dans src/donnees). */
export function competitions() {
  if (!fs.existsSync(RACINE)) return [];
  return fs
    .readdirSync(RACINE, { withFileTypes: true })
    .filter((d) => d.isDirectory() && !d.name.startsWith("."))
    .map((d) => lire(d.name, "meta.json"))
    .filter(Boolean);
}

export function parSlug(slug) {
  const meta = competitions().find((m) => m.competition.slug === slug);
  if (!meta) throw new Error(`Compétition inconnue : ${slug}`);
  return meta;
}

/** Contexte commun à toutes les pages d'une compétition. */
export function contexte(slug) {
  const meta = parSlug(slug);
  const cid = meta.competition.id;
  const matchs = lire(cid, "matchs.json") || [];
  const parId = Object.fromEntries(matchs.map((m) => [m.id, m]));
  const enjeux = lire(cid, "simulation.json")?.enjeux ?? {};
  // « Gros enjeu » : les 3 matchs les plus décisifs de chaque journée (importance d'au moins 10 points)
  const grosEnjeux = new Set();
  const parJournee = {};
  for (const m of matchs) if (enjeux[m.id]) (parJournee[m.journee] ??= []).push(m.id);
  for (const ids of Object.values(parJournee)) {
    ids.sort((a, b) => enjeux[b].importance - enjeux[a].importance);
    ids.slice(0, 3).filter((id) => enjeux[id].importance >= 0.1).forEach((id) => grosEnjeux.add(id));
  }
  return {
    meta,
    cid,
    enjeux,
    grosEnjeux,
    slug,
    matchs,
    parId,
    nom: (id) => meta.equipes[id]?.nom ?? id,
    court: (id) => meta.equipes[id]?.court ?? id,
    lienEquipe: (id) => `/${slug}/equipes/${id}/`,
    lienMatch: (id) => (parId[id] ? `/${slug}/matchs/${id}/` : null),
    lire: (f) => lire(cid, f),
  };
}

export function chemins() {
  return competitions().map((m) => ({ params: { competition: m.competition.slug } }));
}

// ---------- Formatage (français) ----------
const nf = (d) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmt = {
  num: (x, d = 1) => (x == null ? "—" : nf(d).format(x)),
  ent: (x) => (x == null ? "—" : nf(0).format(x)),
  pct: (x, d = 0) => {
    if (x == null) return "—";
    if (x > 0 && x < 0.005 && d === 0) return "< 1 %";
    if (x < 1 && x > 0.995 && d === 0) return "> 99 %";
    return `${nf(d).format(x * 100)} %`;
  },
  signe: (x, d = 1) => (x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${nf(d).format(Math.abs(x))}`),
  date: (iso) =>
    iso ? new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "—",
  dateLongue: (iso) =>
    iso
      ? new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })
      : "—",
  majuscule: (s) => (s ? s[0].toUpperCase() + s.slice(1) : s),
};

export const LIBELLES_ZONES = {
  c1: "Ligue des champions",
  c1q: "Ligue des champions (qualif.)",
  c3: "Ligue Europa",
  c4: "Ligue Conférence",
  barrage: "Barrage",
  relegation: "Relégation",
};

export const LIBELLES_MODELES = {
  elo: "Elo",
  dixon_coles: "Dixon-Coles",
  ensemble: "Ensemble Elo + Dixon-Coles",
  naif: "Référence naïve",
  marche: "Bookmakers (avant-match)",
  cloture: "Bookmakers (clôture)",
};

// ---------- « Ce qui se joue » ----------
export const LIBELLES_GROUPES = {
  titre: "chances de titre",
  c1: "chances de Ligue des champions",
  europe: "chances de coupe d'Europe",
  danger: "risque de zone rouge (barrage ou relégation)",
  relegation: "risque de relégation directe",
};
export const LIBELLES_GROUPES_COURTS = {
  titre: "Titre", c1: "Ligue des champions", europe: "Coupe d'Europe", danger: "Zone rouge", relegation: "Relégation directe",
};

/** Le plus gros écart en jeu pour un match : quelle équipe, quel objectif, entre victoire et défaite. */
export function principalEnjeu(e, m) {
  if (!e) return null;
  let meilleur = null;
  for (const cote of ["dom", "ext"]) {
    for (const [g, vals] of Object.entries(e[cote])) {
      if (g === "points" || !vals) continue;
      const [v, n, d] = cote === "dom" ? vals : [vals[2], vals[1], vals[0]];
      if (v == null || d == null) continue;
      const ecart = Math.abs(v - d);
      if (!meilleur || ecart > meilleur.ecart) meilleur = { cote, equipe: m[cote], groupe: g, victoire: v, nul: n, defaite: d, ecart };
    }
  }
  return meilleur;
}

export function phraseEnjeu(p, court) {
  if (!p) return "";
  const lib = LIBELLES_GROUPES[p.groupe];
  return `${court(p.equipe)} : ${lib} de ${fmt.pct(p.victoire)} en cas de victoire, ${fmt.pct(p.defaite)} en cas de défaite.`;
}
