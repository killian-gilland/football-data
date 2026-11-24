import { defineConfig } from "astro/config";

// URL publique du site (utilisée pour les liens canoniques et le sitemap).
// À définir dans GitHub Actions (variable SITE_URL) une fois le domaine connu.
export default defineConfig({
  site: process.env.SITE_URL || "https://ligue1-data.pages.dev",
  trailingSlash: "ignore",
  build: { format: "directory" },
});
