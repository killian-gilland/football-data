// robots.txt : tout est bloqué tant que le site n'est pas lancé (PUBLIC_INDEXABLE="true" pour l'ouvrir).
export function GET({ site }) {
  const indexable = import.meta.env.PUBLIC_INDEXABLE === "true";
  const lignes = indexable
    ? ["User-agent: *", "Allow: /", "", `Sitemap: ${new URL("/sitemap.xml", site).href}`]
    : ["User-agent: *", "Disallow: /"];
  return new Response(lignes.join("\n") + "\n", { headers: { "Content-Type": "text/plain" } });
}
