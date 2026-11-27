// Comparateur de deux équipes : radar des profils (rang centile dans le championnat) + duel ligne par ligne.
// La comparaison choisie est reprise dans l'adresse (#psg-marseille) pour pouvoir la partager.
import { useEffect, useMemo, useState } from "react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import { num, pct, useCouleurs } from "./theme.js";

// [clé, libellé, accès, format, plus grand = meilleur]
const MESURES = [
  ["rang", "Classement", (x) => x.rang, (v) => `${v}e`, false],
  ["ppm", "Points par match", (x) => x.ppm, (v) => num(v, 2), true],
  ["bp", "Buts marqués / match", (x) => x.bp_pm, (v) => num(v, 2), true],
  ["bc", "Buts encaissés / match", (x) => x.bc_pm, (v) => num(v, 2), false],
  ["dom", "Points à domicile", (x) => x.dom?.pts, (v) => num(v, 0), true],
  ["ext", "Points à l'extérieur", (x) => x.ext?.pts, (v) => num(v, 0), true],
  ["cs", "Matchs sans encaisser", (x) => x.clean_sheets, (v) => num(v, 0), true],
  ["forme", "Points sur les 5 derniers", (x) => x.forme5, (v) => num(v, 0), true],
  ["elo", "Note Elo", (x) => x.elo, (v) => num(v, 0), true],
  ["iop", "Occasions créées / match", (x) => x.io?.pour_par_match, (v) => num(v, 2), true],
  ["ioc", "Occasions concédées / match", (x) => x.io?.contre_par_match, (v) => num(v, 2), false],
  ["tirs", "Tirs / match", (x) => x.tirs?.tirs_par_match, (v) => num(v), true],
  ["cadres", "Tirs cadrés / match", (x) => x.tirs?.cadres_par_match, (v) => num(v), true],
  ["tirsc", "Tirs concédés / match", (x) => x.tirs?.tirs_concedes_par_match, (v) => num(v), false],
  ["precision", "Précision des tirs", (x) => x.tirs?.precision, (v) => pct(v), true],
  ["conversion", "Buts par tir cadré", (x) => x.tirs?.conversion, (v) => pct(v), true],
  ["corners", "Corners obtenus / match", (x) => x.corners?.pour_par_match, (v) => num(v), true],
  ["fautes", "Fautes / match", (x) => x.discipline?.fautes_par_match, (v) => num(v), false],
  ["jaunes", "Cartons jaunes", (x) => x.discipline?.jaunes, (v) => num(v, 0), false],
  ["remontee", "Points repris après avoir été mené à la pause", (x) => x.mi_temps?.points_gagnes_apres_avoir_ete_mene, (v) => num(v, 0), true],
  ["perdus", "Points perdus en menant à la pause", (x) => x.mi_temps?.points_perdus_en_menant, (v) => num(v, 0), false],
  ["titre", "Chances de titre", (x) => x.titre, (v) => pct(v), true],
];
// Axes du radar : chacun exprimé en rang centile (100 = meilleure équipe du championnat sur ce critère)
const AXES = [
  ["bp", "Attaque"], ["bc", "Défense"], ["iop", "Occ. créées"], ["ioc", "Occ. évitées"],
  ["precision", "Précision"], ["forme", "Forme"], ["dom", "Domicile"], ["ext", "Extérieur"],
];

function centiles(equipes) {
  const res = {};
  for (const [cle, , acces, , grand] of MESURES) {
    const vals = equipes.map((e) => ({ id: e.equipe, v: acces(e) })).filter((x) => x.v != null);
    vals.sort((a, b) => (grand ? a.v - b.v : b.v - a.v)); // du pire au meilleur
    vals.forEach((x, i) => {
      res[x.id] ??= {};
      res[x.id][cle] = vals.length > 1 ? Math.round((i / (vals.length - 1)) * 100) : 50;
    });
  }
  return res;
}

function InfobulleRadar({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="infobulle">
      <b>{p.axe}</b>
      <ul>
        {payload.map((l) => (
          <li key={l.dataKey}><span><i style={{ background: l.color }} />{l.name}</span><b>{p[`brut_${l.dataKey}`]}</b></li>
        ))}
      </ul>
      <div style={{ marginTop: 4, opacity: 0.7 }}>Échelle : rang centile dans le championnat</div>
    </div>
  );
}

export default function Comparateur({ equipes }) {
  const c = useCouleurs();
  const tri = useMemo(() => [...equipes].sort((a, b) => a.rang - b.rang), [equipes]);
  const par = useMemo(() => Object.fromEntries(equipes.map((e) => [e.equipe, e])), [equipes]);
  const cent = useMemo(() => centiles(equipes), [equipes]);
  const [a, setA] = useState(tri[0].equipe);
  const [b, setB] = useState(tri[1].equipe);

  // Lecture de l'adresse (#a-b) puis du dernier choix mémorisé
  useEffect(() => {
    const ids = equipes.map((e) => e.equipe);
    const h = decodeURIComponent(location.hash.slice(1));
    const trouve = ids.flatMap((x) => ids.filter((y) => y !== x && h === `${x}-${y}`).map((y) => [x, y]))[0];
    if (trouve) { setA(trouve[0]); setB(trouve[1]); return; }
    try {
      const m = JSON.parse(localStorage.getItem("comparateur") || "null");
      if (m && par[m[0]] && par[m[1]]) { setA(m[0]); setB(m[1]); }
    } catch (e) { /* stockage indisponible : on garde le choix par défaut */ }
  }, []);
  useEffect(() => {
    history.replaceState(null, "", `#${a}-${b}`);
    try { localStorage.setItem("comparateur", JSON.stringify([a, b])); } catch (e) { /* rien */ }
  }, [a, b]);

  const A = par[a], B = par[b];
  const coulA = c?.categories[0], coulB = c?.categories[1];
  const radar = AXES.map(([cle, axe]) => {
    const m = MESURES.find((x) => x[0] === cle);
    return { axe, A: cent[a]?.[cle] ?? 0, B: cent[b]?.[cle] ?? 0, brut_A: m[3](m[2](A)), brut_B: m[3](m[2](B)) };
  });

  return (
    <div className="outil">
      <div className="duel">
        <label className="duel-equipe"><i style={{ background: coulA }} />{A.logo && <img className="logo-club" src={A.logo} alt="" width={28} height={28} />}
          <select id="comparateur-a" value={a} onChange={(e) => setA(e.target.value)} aria-label="Première équipe">
            {tri.map((e) => <option key={e.equipe} value={e.equipe} disabled={e.equipe === b}>{e.nom}</option>)}
          </select>
        </label>
        <span className="contre">contre</span>
        <label className="duel-equipe"><i style={{ background: coulB }} />{B.logo && <img className="logo-club" src={B.logo} alt="" width={28} height={28} />}
          <select id="comparateur-b" value={b} onChange={(e) => setB(e.target.value)} aria-label="Seconde équipe">
            {tri.map((e) => <option key={e.equipe} value={e.equipe} disabled={e.equipe === a}>{e.nom}</option>)}
          </select>
        </label>
      </div>

      <div className="grille-2">
        <div className="zone-graph" style={{ padding: 8 }}>
          {c && (
            <ResponsiveContainer width="100%" height={360}>
              <RadarChart data={radar} outerRadius="62%">
                <PolarGrid stroke={c.trait} />
                <PolarAngleAxis dataKey="axe" tick={{ fill: c["encre-2"], fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                <Radar name={A.nom} dataKey="A" stroke={coulA} fill={coulA} fillOpacity={0.22} strokeWidth={2} isAnimationActive={false} />
                <Radar name={B.nom} dataKey="B" stroke={coulB} fill={coulB} fillOpacity={0.22} strokeWidth={2} isAnimationActive={false} />
                <Tooltip content={<InfobulleRadar />} />
              </RadarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="colonne" style={{ gap: 10 }}>
          <h3>Lire le radar</h3>
          <p className="discret">
            Chaque axe classe l'équipe parmi les {equipes.length} du championnat : au bord, elle est la meilleure sur ce
            critère, au centre la moins bonne. « Défense » et « Occ. évitées » (occasions concédées) sont inversés (moins on encaisse,
            plus on est au bord). Survolez un axe pour voir les valeurs réelles.
          </p>
          <div className="legende">
            <span><i className="pastille" style={{ background: coulA }} />{A.nom}</span>
            <span><i className="pastille" style={{ background: coulB }} />{B.nom}</span>
          </div>
        </div>
      </div>

      <div className="tableau" role="table" aria-label="Comparaison détaillée">
        {MESURES.map(([cle, lib, acces, fmt, grand]) => {
          const va = acces(A), vb = acces(B);
          if (va == null && vb == null) return null;
          const max = Math.max(Math.abs(va ?? 0), Math.abs(vb ?? 0)) || 1;
          const mieuxA = va != null && vb != null && va !== vb && (grand ? va > vb : va < vb);
          const mieuxB = va != null && vb != null && va !== vb && !mieuxA;
          return (
            <div className="ligne-duel" role="row" key={cle}>
              <div className={`val a ${mieuxA ? "mieux" : ""}`} role="cell">
                <b>{fmt(va)}</b>
                {cle !== "rang" && <div className="piste"><span className="b3" style={{ width: `${(Math.abs(va ?? 0) / max) * 100}%`, "--c": coulA, height: 8 }} data-tip={`${A.nom}|${fmt(va)}|${lib}`} /></div>}
              </div>
              <div className="lib" role="cell">{lib}</div>
              <div className={`val ${mieuxB ? "mieux" : ""}`} role="cell">
                <b>{fmt(vb)}</b>
                {cle !== "rang" && <div className="piste"><span className="b3" style={{ width: `${(Math.abs(vb ?? 0) / max) * 100}%`, "--c": coulB, height: 8 }} data-tip={`${B.nom}|${fmt(vb)}|${lib}`} /></div>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="tres-discret">En gras : la meilleure des deux valeurs. Pour les statistiques « contre » (buts encaissés, tirs concédés, cartons…), la plus petite est la meilleure.</p>
    </div>
  );
}
