// robots.txt avec l'adresse absolue du sitemap (exigée par la norme).
export function GET({ site }) {
  return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${new URL("/sitemap.xml", site).href}\n`, {
    headers: { "Content-Type": "text/plain" },
  });
}
