// Scores en quasi-direct : interroge le Worker « direct » et met à jour la page sans la recharger.
// Actif seulement si la page contient #config-direct (adresse du Worker définie au build).
// Rythme : toutes les minutes pendant un match, puis on se met en veille jusqu'au prochain coup d'envoi.

const ETATS = { en_cours: "En direct", mi_temps: "Mi-temps", termine: "Terminé", reporte: "Reporté", annule: "Annulé" };

function puce(m) {
  if (m.statut === "en_cours") return `<span class="puce-direct">${m.minute ? `${m.minute}'` : "En direct"}</span>`;
  if (m.statut === "mi_temps") return `<span class="puce-direct pause" title="Mi-temps">MT</span>`;
  return `<span class="puce-etat">${ETATS[m.statut] ?? ""}</span>`;
}

function appliquerMatchs(matchs, joues) {
  for (const m of matchs) {
    const actif = ["en_cours", "mi_temps"].includes(m.statut);
    const affiche = actif || (m.statut === "termine" && !joues.has(m.id)) || ["reporte", "annule"].includes(m.statut);
    if (!affiche) continue;
    for (const ligne of document.querySelectorAll(`[data-match="${m.id}"]`)) {
      const score = ligne.querySelector(".score");
      if (score && m.score) {
        score.textContent = `${m.score[0]} – ${m.score[1]}`;
        score.classList.remove("vide");
        score.classList.toggle("direct", actif);
      }
      const heure = ligne.querySelector(".heure");
      if (heure) heure.innerHTML = puce(m);
    }
    for (const el of document.querySelectorAll(`[data-score-match="${m.id}"]`)) {
      if (m.score) el.textContent = `${m.score[0]}–${m.score[1]}`;
      el.classList.remove("vs");
      el.classList.toggle("direct", actif);
    }
    for (const el of document.querySelectorAll(`[data-etat-match="${m.id}"]`)) {
      el.innerHTML = `${puce(m)}${m.mi_temps && m.statut !== "mi_temps" ? ` · mi-temps ${m.mi_temps[0]}–${m.mi_temps[1]}` : ""}`;
      el.hidden = false;
    }
  }
}

function appliquerClassement(matchs, joues) {
  const base = document.getElementById("classement-base");
  const table = document.querySelector("table[data-classement-direct]");
  if (!base || !table) return;
  const equipes = JSON.parse(base.textContent).map((e) => ({ ...e }));
  const par = Object.fromEntries(equipes.map((e) => [e.equipe, e]));
  let nouveaux = 0;
  for (const m of matchs) {
    if (!m.score || joues.has(m.id) || !["en_cours", "mi_temps", "termine"].includes(m.statut)) continue;
    const [d, e] = [par[m.dom], par[m.ext]];
    if (!d || !e) continue;
    nouveaux++;
    const [bd, be] = m.score;
    for (const [eq, pour, contre] of [[d, bd, be], [e, be, bd]]) {
      eq.j += 1; eq.bp += pour; eq.diff += pour - contre;
      eq.pts += pour > contre ? 3 : pour === contre ? 1 : 0;
      eq.g += pour > contre ? 1 : 0;
      eq.direct = eq.direct || ["en_cours", "mi_temps"].includes(m.statut);
    }
  }
  if (!nouveaux) return;
  equipes.sort((a, b) => b.pts - a.pts || b.diff - a.diff || b.bp - a.bp || b.g - a.g);
  const corps = table.tBodies[0];
  const seps = (table.dataset.sep || "").split(",").map(Number).filter(Boolean);
  const zones = JSON.parse(table.dataset.zones || "{}");
  equipes.forEach((eq, i) => {
    const tr = corps.querySelector(`tr[data-equipe="${eq.equipe}"]`);
    if (!tr) return;
    const rang = i + 1;
    const ecart = eq.rang - rang;
    tr.querySelector(".n").textContent = rang;
    const z = tr.querySelector(".zone");
    if (z) z.className = `zone zone-${zones[rang] ?? ""}`; // les zones suivent la place, pas l'équipe
    tr.querySelector(".pts").textContent = eq.pts;
    const diff = tr.querySelector(".diff");
    if (diff) diff.textContent = eq.diff > 0 ? `+${eq.diff}` : eq.diff < 0 ? `−${-eq.diff}` : "0";
    const j = tr.querySelector(".j");
    if (j) j.textContent = eq.j;
    let mvt = tr.querySelector(".mouvement");
    if (!mvt) { mvt = document.createElement("span"); mvt.className = "mouvement"; tr.querySelector(".equipe")?.append(mvt); }
    mvt.textContent = ecart > 0 ? `▲${ecart}` : ecart < 0 ? `▼${-ecart}` : "";
    mvt.className = `mouvement ${ecart > 0 ? "monte" : ecart < 0 ? "descend" : ""}`;
    tr.classList.toggle("en-jeu", !!eq.direct);
    tr.classList.toggle("separateur", seps.includes(rang));
    corps.append(tr);
  });
  for (const t of document.querySelectorAll("[data-direct-titre]")) t.hidden = false;
}

function demarrer(cfg) {
  const joues = new Set(cfg.joues);
  let minuteur = null;
  const planifier = (ms) => {
    clearTimeout(minuteur);
    minuteur = setTimeout(() => {
      if (document.hidden) document.addEventListener("visibilitychange", tour, { once: true });
      else tour();
    }, ms);
  };
  async function tour() {
    let donnees;
    try {
      const r = await fetch(cfg.url, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      donnees = await r.json();
    } catch (e) {
      planifier(5 * 60 * 1000); // source indisponible : on réessaie dans 5 minutes
      return;
    }
    const matchs = (donnees.matchs ?? []).filter((m) => m.dom && m.ext).map((m) => ({ ...m, id: `${cfg.prefixe}-${m.dom}-${m.ext}` }));
    appliquerMatchs(matchs, joues);
    appliquerClassement(matchs, joues);
    if (matchs.some((m) => ["en_cours", "mi_temps"].includes(m.statut))) return planifier(60 * 1000);
    const avant = matchs
      .filter((m) => m.statut === "a_venir")
      .map((m) => new Date(m.debut).getTime() - Date.now())
      .filter((d) => d > -30 * 60 * 1000 && d < 12 * 3600 * 1000);
    if (avant.length) planifier(Math.max(60 * 1000, Math.min(...avant)));
  }
  tour();
}

const el = document.getElementById("config-direct");
if (el) {
  try { demarrer(JSON.parse(el.textContent)); } catch (e) { /* configuration illisible : pas de direct */ }
}
