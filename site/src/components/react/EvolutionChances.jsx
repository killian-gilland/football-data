// Chances de titre, d'Europe ou de zone rouge recalculées après chaque journée (J0 = avant la saison).
// Même logique de sélection que l'évolution du classement : 8 équipes au plus, couleur fixe par équipe.
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { pct, useCouleurs } from "./theme.js";

const MAX = 8;
const MESURES = {
  titre: "Titre",
  c1: "Ligue des champions",
  europe: "Europe",
  danger: "Zone rouge",
};

function Infobulle({ active, payload, label, noms, mesure }) {
  if (!active || !payload?.length) return null;
  const lignes = [...payload].sort((a, b) => b.value - a.value);
  return (
    <div className="infobulle">
      <b>{label === "J0" ? "Avant la saison" : `Après la ${label.slice(1)}e journée`} · {MESURES[mesure]}</b>
      <ul>
        {lignes.map((l) => (
          <li key={l.dataKey}><span><i style={{ background: l.color }} />{noms[l.dataKey]}</span><b>{pct(l.value, 1)}</b></li>
        ))}
      </ul>
    </div>
  );
}

export default function EvolutionChances({ journees, equipes, groupes }) {
  const c = useCouleurs();
  const mesures = Object.keys(MESURES).filter((m) => groupes.includes(m));
  const [mesure, setMesure] = useState(mesures[0]);
  const noms = useMemo(() => Object.fromEntries(equipes.map((e) => [e.id, e.court])), [equipes]);
  const parMesure = (m) => [...equipes].sort((a, b) => (b[m]?.at(-1) ?? 0) - (a[m]?.at(-1) ?? 0));
  const initiales = (m) => parMesure(m).filter((e) => (e[m]?.at(-1) ?? 0) > 0.02 || Math.max(...(e[m] ?? [0])) > 0.1).slice(0, 6).map((e) => e.id);
  const [slots, setSlots] = useState(() => Object.fromEntries(initiales(mesures[0]).map((id, i) => [id, i])));
  const choisies = Object.keys(slots);

  const changerMesure = (m) => {
    setMesure(m);
    setSlots(Object.fromEntries(initiales(m).map((id, i) => [id, i])));
  };
  const basculer = (id) =>
    setSlots((s) => {
      if (id in s) { const { [id]: _, ...r } = s; return r; }
      if (Object.keys(s).length >= MAX) return s;
      const pris = new Set(Object.values(s));
      return { ...s, [id]: [...Array(MAX).keys()].find((k) => !pris.has(k)) };
    });

  const donnees = journees.map((j, k) => {
    const ligne = { j: `J${j}` };
    for (const e of equipes) ligne[e.id] = e[mesure]?.[k] ?? null;
    return ligne;
  });
  const dernier = journees.length - 1;

  return (
    <div className="outil">
      <div className="bascule" role="group" aria-label="Objectif affiché">
        {mesures.map((m) => (
          <button key={m} type="button" aria-pressed={mesure === m} onClick={() => changerMesure(m)}>{MESURES[m]}</button>
        ))}
      </div>
      <div className="choix-equipes" role="group" aria-label="Équipes affichées (8 au plus)">
        {parMesure(mesure).map((e) => {
          const actif = e.id in slots;
          return (
            <button key={e.id} type="button" aria-pressed={actif} disabled={!actif && choisies.length >= MAX} onClick={() => basculer(e.id)}>
              <i style={actif && c ? { background: c.categories[slots[e.id]] } : undefined} />
              {e.court}
            </button>
          );
        })}
      </div>
      <div className="zone-graph">
        {c && (
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={donnees} margin={{ top: 8, right: 96, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={c.trait} vertical={false} />
              <XAxis dataKey="j" tick={{ fill: c["encre-3"], fontSize: 12 }} tickLine={false} axisLine={{ stroke: c["trait-fort"] }} />
              <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => `${Math.round(v * 100)} %`}
                tick={{ fill: c["encre-3"], fontSize: 12 }} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<Infobulle noms={noms} mesure={mesure} />} cursor={{ stroke: c["trait-fort"] }} />
              {choisies.map((id) => {
                const coul = c.categories[slots[id]];
                return (
                  <Line key={id} type="linear" dataKey={id} stroke={coul} strokeWidth={2.2} isAnimationActive={false}
                    dot={{ r: 3, fill: coul, stroke: c.papier, strokeWidth: 1.5 }} activeDot={{ r: 5, stroke: c.papier, strokeWidth: 2 }}
                    label={(p) => (p.index === dernier ? <text key={`l-${id}`} x={p.x + 8} y={p.y + 4} fill={c.encre} fontSize={12} fontWeight={600}>{noms[id]}</text> : null)} />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <p className="tres-discret">
        J0 : pronostic d'avant-saison. Chaque point est recalculé avec les seules informations disponibles à cette date
        (modèle réajusté, matchs suivants simulés). {choisies.length}/{MAX} équipes affichées.
      </p>
    </div>
  );
}
