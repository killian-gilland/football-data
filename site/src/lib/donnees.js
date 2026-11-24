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
  return {
    meta,
    cid,
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
