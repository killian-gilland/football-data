// Sitemap généré au build : toutes les pages indexables (équipes, matchs, saisons…).
import { competitions, contexte, lire } from "../lib/donnees.js";

export function GET({ site }) {
  const urls = ["/", "/methodologie/"];
  for (const meta of competitions()) {
    const ctx = contexte(meta.competition.slug);
    const s = ctx.slug;
    urls.push(`/${s}/`, `/${s}/matchs/`, `/${s}/equipes/`, `/${s}/historique/`, `/${s}/comparateur/`, `/${s}/predictions/`, `/${s}/forces/`);
    if (ctx.lire("cotes.json")) urls.push(`/${s}/cotes/`);
    for (const id of Object.keys(meta.equipes)) if (lire(meta.competition.id, `equipes/${id}.json`)) urls.push(`/${s}/equipes/${id}/`);
    for (const m of ctx.matchs) urls.push(`/${s}/matchs/${m.id}/`);
    for (const sa of ctx.lire("historique.json").saisons) urls.push(`/${s}/historique/${sa.saison}/`);
  }
  const corps = urls.map((u) => `<url><loc>${new URL(u, site).href}</loc></url>`).join("");
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${corps}</urlset>`, {
    headers: { "Content-Type": "application/xml" },
  });
}
