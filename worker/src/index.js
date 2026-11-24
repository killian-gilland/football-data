// Worker Cloudflare « direct » : GET /direct -> scores du jour (veille, jour, lendemain) de la compétition.
// Cache à deux niveaux pour respecter la limite de 10 appels/minute de l'offre gratuite :
// 1) mémoire de l'instance (60 s) ; 2) Cache API de Cloudflare (60 s + copie de secours 24 h).
// En cas d'échec de l'API, on sert la dernière réponse valide plutôt qu'une erreur.
import alias from "./alias.json";
import { fenetre, normaliserMatchs } from "./direct.js";

const DUREE = 60 * 1000;
let memoire = null; // { t, corps }

function entetesCors(request, env) {
  const origine = request.headers.get("Origin") ?? "";
  const autorisees = (env.ORIGINES ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return {
    "Access-Control-Allow-Origin": autorisees.includes(origine) ? origine : autorisees[0] ?? "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    Vary: "Origin",
  };
}

function reponse(corps, statut, cors, age = 30) {
  return new Response(corps, {
    status: statut,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": `public, max-age=${age}`, ...cors },
  });
}

async function interrogerApi(env) {
  const { dateFrom, dateTo } = fenetre();
  const url = `https://api.football-data.org/v4/competitions/${env.COMPETITION}/matches?dateFrom=${dateFrom}&dateTo=${dateTo}`;
  const r = await fetch(url, { headers: { "X-Auth-Token": env.FOOTBALL_DATA_ORG_TOKEN ?? "" } });
  if (!r.ok) throw new Error(`football-data.org a répondu ${r.status}`);
  return JSON.stringify(normaliserMatchs(await r.json(), alias));
}

export default {
  async fetch(request, env, ctx) {
    const cors = entetesCors(request, env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const url = new URL(request.url);
    if (url.pathname !== "/direct") return reponse(JSON.stringify({ erreur: "Adresse inconnue. Utilisez /direct." }), 404, cors);

    if (memoire && Date.now() - memoire.t < DUREE) return reponse(memoire.corps, 200, cors);

    const cache = caches.default;
    const cleFrais = new Request(`https://direct.cache/${env.COMPETITION}/frais`);
    const cleSecours = new Request(`https://direct.cache/${env.COMPETITION}/secours`);
    const frais = await cache.match(cleFrais);
    if (frais) {
      const corps = await frais.text();
      memoire = { t: Date.now(), corps };
      return reponse(corps, 200, cors);
    }
    try {
      const corps = await interrogerApi(env);
      memoire = { t: Date.now(), corps };
      const entetes = (age) => ({ headers: { "Content-Type": "application/json", "Cache-Control": `public, max-age=${age}` } });
      ctx.waitUntil(cache.put(cleFrais, new Response(corps, entetes(60))));
      ctx.waitUntil(cache.put(cleSecours, new Response(corps, entetes(86400))));
      return reponse(corps, 200, cors);
    } catch (e) {
      const secours = memoire?.corps ?? (await (await cache.match(cleSecours))?.text());
      if (secours) return reponse(secours, 200, cors, 15);
      return reponse(JSON.stringify({ erreur: "Scores indisponibles pour le moment.", matchs: [] }), 503, cors, 15);
    }
  },
};
