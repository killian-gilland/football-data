// Compteurs : les chiffres marqués data-compteur défilent de 0 à leur valeur à l'affichage.
const nf = (d) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const animer = (el) => {
    const texte = el.textContent.trim();
    // Nombre au format fran\u00e7ais : s\u00e9parateur de milliers = espace ins\u00e9cable, d\u00e9cimales apr\u00e8s la virgule
    const m = texte.match(/-?\d+(?:[\u202f\u00a0]\d{3})*(?:,\d+)?/);
    if (!m) return;
    const brut = m[0];
    const dec = (brut.split(",")[1] ?? "").length;
    const cible = parseFloat(brut.replace(/[\s\u202f\u00a0]/g, "").replace(",", "."));
    if (!Number.isFinite(cible)) return;
    const debut = performance.now(), duree = 900;
    const pas = (t) => {
      const k = Math.min(1, (t - debut) / duree);
      const v = cible * (1 - Math.pow(1 - k, 3));
      el.textContent = texte.replace(brut, nf(dec).format(v));
      if (k < 1) requestAnimationFrame(pas); else el.textContent = texte;
    };
    requestAnimationFrame(pas);
  };
  const obs = new IntersectionObserver((entrees) => {
    for (const e of entrees) if (e.isIntersecting) { animer(e.target); obs.unobserve(e.target); }
  });
  document.querySelectorAll("[data-compteur]").forEach((el) => obs.observe(el));
}
