import { defineConfig } from "astro/config";
import react from "@astrojs/react";

// URL publique du site (utilisée pour les liens canoniques et le sitemap).
// À définir dans GitHub Actions (variable SITE_URL) une fois le domaine connu.
// React n'est chargé que sur les « îlots » interactifs (comparateur, évolution du classement).
export default defineConfig({
  site: process.env.SITE_URL || "https://ligue1-data.pages.dev",
  trailingSlash: "ignore",
  build: { format: "directory" },
  integrations: [react()],
});
