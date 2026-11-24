// Lit les couleurs du thème (variables CSS) et se met à jour quand le visiteur bascule clair/sombre.
// Recharts écrit les couleurs dans des attributs SVG, qui n'acceptent pas var(--x) : on passe donc des valeurs.
import { useEffect, useState } from "react";

const NOMS = ["encre", "encre-2", "encre-3", "trait", "trait-fort", "papier", "papier-2", "projecteur",
  "zone-c1", "zone-c3", "zone-relegation", "zone-barrage",
  "cat-1", "cat-2", "cat-3", "cat-4", "cat-5", "cat-6", "cat-7", "cat-8"];

function lireCouleurs() {
  if (typeof window === "undefined") return null;
  const st = getComputedStyle(document.documentElement);
  const c = {};
  for (const n of NOMS) c[n] = st.getPropertyValue(`--${n}`).trim();
  c.categories = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => c[`cat-${i}`]);
  return c;
}

export function useCouleurs() {
  const [couleurs, setCouleurs] = useState(null);
  useEffect(() => {
    setCouleurs(lireCouleurs());
    const obs = new MutationObserver(() => setCouleurs(lireCouleurs()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return couleurs;
}

export const pct = (x, d = 0) =>
  x == null ? "—" : `${(x * 100).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })} %`;
export const num = (x, d = 1) =>
  x == null ? "—" : x.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
