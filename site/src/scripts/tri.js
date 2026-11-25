// Tri des tableaux marqués data-triable : clic sur un en-tête (sauf .sans-tri), second clic = ordre inverse.
// Les nombres au format français (« 1 730 », « −5 », « 93 % », « < 1 % ») sont reconnus.
function valeur(cellule) {
  const brut = cellule.dataset.v ?? cellule.textContent.trim();
  const t = brut.replace(/−/g, "-").replace(/[\s  ]/g, "").replace(",", ".").replace(/[<>%e]|pts?/g, "");
  const n = parseFloat(t);
  return Number.isFinite(n) && /^[-+]?\d/.test(t) ? n : brut.toLowerCase();
}

for (const table of document.querySelectorAll("table[data-triable]")) {
  const entetes = [...table.tHead.rows[0].cells];
  entetes.forEach((th, col) => {
    if (th.classList.contains("sans-tri")) return;
    th.classList.add("triable");
    th.tabIndex = 0;
    const trier = () => {
      const desc = th.getAttribute("aria-sort") !== "descending";
      entetes.forEach((x) => x.removeAttribute("aria-sort"));
      th.setAttribute("aria-sort", desc ? "descending" : "ascending");
      const lignes = [...table.tBodies[0].rows];
      lignes.sort((a, b) => {
        const va = valeur(a.cells[col]), vb = valeur(b.cells[col]);
        const r = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), "fr");
        return desc ? -r : r;
      });
      table.tBodies[0].append(...lignes);
    };
    th.addEventListener("click", trier);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); trier(); } });
  });
}
