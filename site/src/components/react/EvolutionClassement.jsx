// Évolution du classement journée par journée : on choisit les équipes (8 au plus) et la mesure (rang ou points).
// La couleur suit l'équipe : une équipe garde sa couleur tant qu'elle reste sélectionnée.
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCouleurs } from "./theme.js";

const MAX = 8;

function Infobulle({ active, payload, label, mode, noms }) {
  if (!active || !payload?.length) return null;
  const lignes = [...payload].sort((a, b) => (mode === "rang" ? a.value - b.value : b.value - a.value));
  return (
    <div className="infobulle">
      <b>Après la {label.slice(1)}e journée</b>
      <ul>
        {lignes.map((l) => (
          <li key={l.dataKey}>
            <span><i style={{ background: l.color }} />{noms[l.dataKey]}</span>
            <b>{mode === "rang" ? `${l.value}e` : `${l.value} pts`}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function EvolutionClassement({ journees, equipes, nbEquipes, finEurope, debutRelegation, parDefaut }) {
  const couleurs = useCouleurs();
  const [mode, setMode] = useState("rang");
  // id -> numéro de couleur (0..7), attribué à la sélection et conservé
  const [slots, setSlots] = useState(() => Object.fromEntries(parDefaut.slice(0, MAX).map((id, i) => [id, i])));
  const noms = useMemo(() => Object.fromEntries(equipes.map((e) => [e.id, e.court])), [equipes]);
  const ordre = useMemo(() => [...equipes].sort((a, b) => a.rangs.at(-1) - b.rangs.at(-1)), [equipes]);
  const choisies = Object.keys(slots);

  const basculer = (id) => {
    setSlots((s) => {
      if (id in s) {
        const { [id]: _, ...reste } = s;
        return reste;
      }
      if (Object.keys(s).length >= MAX) return s;
      const pris = new Set(Object.values(s));
      const libre = [...Array(MAX).keys()].find((k) => !pris.has(k));
      return { ...s, [id]: libre };
    });
  };
  const preselection = (ids) => setSlots(Object.fromEntries(ids.slice(0, MAX).map((id, i) => [id, i])));

  const donnees = useMemo(
    () =>
      journees.map((j, k) => {
        const ligne = { j: `J${j}` };
        for (const e of equipes) ligne[e.id] = mode === "rang" ? e.rangs[k] : e.points[k];
        return ligne;
      }),
    [journees, equipes, mode],
  );
  const dernier = journees.length - 1;
  const ticksRang = [1, 5, 10, 15, nbEquipes].filter((v, i, a) => v <= nbEquipes && a.indexOf(v) === i);
  const c = couleurs;

  return (
    <div className="outil">
      <div className="outil-barre">
        <div className="bascule" role="group" aria-label="Mesure affichée">
          <button type="button" aria-pressed={mode === "rang"} onClick={() => setMode("rang")}>Rang</button>
          <button type="button" aria-pressed={mode === "points"} onClick={() => setMode("points")}>Points</button>
        </div>
        <div className="bascule" role="group" aria-label="Sélections rapides">
          <button type="button" onClick={() => preselection(ordre.slice(0, 6).map((e) => e.id))}>Haut de tableau</button>
          <button type="button" onClick={() => preselection(ordre.slice(-6).map((e) => e.id))}>Bas de tableau</button>
          <button type="button" onClick={() => setSlots({})}>Effacer</button>
        </div>
      </div>

      <div className="choix-equipes" role="group" aria-label="Équipes affichées (8 au plus)">
        {ordre.map((e) => {
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
          <ResponsiveContainer width="100%" height={380}>
            <LineChart data={donnees} margin={{ top: 8, right: 96, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={c.trait} vertical={false} />
              {mode === "rang" && finEurope > 0 && (
                <ReferenceArea y1={0.5} y2={finEurope + 0.5} fill={c["zone-c1"]} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
              )}
              {mode === "rang" && debutRelegation <= nbEquipes && (
                <ReferenceArea y1={debutRelegation - 0.5} y2={nbEquipes + 0.5} fill={c["zone-relegation"]} fillOpacity={0.1} stroke="none" ifOverflow="hidden" />
              )}
              <XAxis dataKey="j" tick={{ fill: c["encre-3"], fontSize: 12 }} tickLine={false} axisLine={{ stroke: c["trait-fort"] }} />
              <YAxis
                reversed={mode === "rang"}
                domain={mode === "rang" ? [0.5, nbEquipes + 0.5] : [0, "dataMax"]}
                ticks={mode === "rang" ? ticksRang : undefined}
                allowDecimals={false}
                tickFormatter={(v) => (mode === "rang" ? `${v}e` : v)}
                tick={{ fill: c["encre-3"], fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={44}
              />
              <Tooltip content={<Infobulle mode={mode} noms={noms} />} cursor={{ stroke: c["trait-fort"] }} />
              {choisies.map((id) => {
                const coul = c.categories[slots[id]];
                return (
                  <Line
                    key={id}
                    type="linear"
                    dataKey={id}
                    stroke={coul}
                    strokeWidth={2.2}
                    dot={{ r: 3, fill: coul, stroke: c.papier, strokeWidth: 1.5 }}
                    activeDot={{ r: 5, stroke: c.papier, strokeWidth: 2 }}
                    isAnimationActive={false}
                    label={(p) =>
                      p.index === dernier ? (
                        <text key={`l-${id}`} x={p.x + 8} y={p.y + 4} fill={c.encre} fontSize={12} fontWeight={600}>{noms[id]}</text>
                      ) : null
                    }
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <p className="tres-discret">
        {mode === "rang"
          ? "Bande bleue : places européennes. Bande rouge : barrage et relégation. Un match reporté compte dans sa journée d'origine une fois joué."
          : "Points cumulés après chaque journée."}
        {" "}{choisies.length}/{MAX} équipes affichées.
      </p>
    </div>
  );
}
