// Fonctions pures du Worker (testées avec node --test, sans réseau).

// Même normalisation que pipeline/referentiel.py : sans accents, minuscules, tirets -> espaces.
export function cle(nom) {
  return String(nom ?? "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\x00-\x7f]/g, "")
    .toLowerCase()
    .replace(/-/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

export const STATUTS = {
  SCHEDULED: "a_venir", TIMED: "a_venir",
  IN_PLAY: "en_cours", PAUSED: "mi_temps",
  FINISHED: "termine", AWARDED: "termine",
  POSTPONED: "reporte", SUSPENDED: "reporte", CANCELLED: "annule",
};

function identifiant(equipe, alias) {
  for (const n of [equipe?.name, equipe?.shortName, equipe?.tla]) {
    const id = n && alias[cle(n)];
    if (id) return id;
  }
  return null;
}

const PARIS = new Intl.DateTimeFormat("fr-FR", {
  timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function heureParis(iso) {
  const p = Object.fromEntries(PARIS.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, heure: `${p.hour}:${p.minute}` };
}

/** Réponse de l'API v4 -> format compact lu par le site. */
export function normaliserMatchs(reponse, alias, maintenant = new Date()) {
  const matchs = (reponse?.matches ?? []).map((m) => {
    const ft = m.score?.fullTime ?? {};
    const ht = m.score?.halfTime ?? {};
    const statut = STATUTS[m.status] ?? "inconnu";
    const aScore = ft.home != null && ft.away != null && ["en_cours", "mi_temps", "termine"].includes(statut);
    return {
      dom: identifiant(m.homeTeam, alias),
      ext: identifiant(m.awayTeam, alias),
      nom_dom: m.homeTeam?.shortName ?? m.homeTeam?.name ?? null,
      nom_ext: m.awayTeam?.shortName ?? m.awayTeam?.name ?? null,
      statut,
      score: aScore ? [ft.home, ft.away] : null,
      mi_temps: ht.home != null && ht.away != null ? [ht.home, ht.away] : null,
      minute: m.minute ?? null,
      debut: m.utcDate,
      ...heureParis(m.utcDate),
      journee: m.matchday ?? null,
    };
  });
  return { maj: maintenant.toISOString(), source: "football-data.org", matchs };
}

/** Fenêtre de dates interrogée : la veille, le jour et le lendemain (UTC). */
export function fenetre(maintenant = new Date()) {
  const j = (d) => new Date(maintenant.getTime() + d * 86400000).toISOString().slice(0, 10);
  return { dateFrom: j(-1), dateTo: j(1) };
}
