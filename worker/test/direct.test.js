// Tests du Worker : node --test worker/test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { cle, fenetre, normaliserMatchs } from "../src/direct.js";

const alias = JSON.parse(readFileSync(new URL("../src/alias.json", import.meta.url), "utf-8"));

test("normalisation identique au pipeline Python", () => {
  assert.equal(cle("AS Saint-Étienne"), "as saint etienne");
  assert.equal(cle("  Paris   Saint-Germain FC "), "paris saint germain fc");
});

test("les alias générés reconnaissent les noms courants de l'API", () => {
  for (const [nom, id] of [["Paris Saint-Germain FC", "psg"], ["Racing Club de Lens", "lens"], ["Stade Brestois 29", "brest"], ["PSG", "psg"]]) {
    assert.equal(alias[cle(nom)], id, nom);
  }
});

test("réponse de l'API convertie : statuts, scores, heure de Paris", () => {
  const r = normaliserMatchs({ matches: [
    { utcDate: "2026-11-28T16:15:00Z", status: "IN_PLAY", matchday: 12, minute: 67,
      homeTeam: { name: "Angers SCO", shortName: "Angers" }, awayTeam: { name: "Racing Club de Lens", shortName: "RC Lens" },
      score: { fullTime: { home: 1, away: 2 }, halfTime: { home: 0, away: 1 } } },
    { utcDate: "2026-11-29T19:45:00Z", status: "TIMED", matchday: 12,
      homeTeam: { name: "Olympique Lyonnais" }, awayTeam: { name: "AS Monaco FC" },
      score: { fullTime: { home: null, away: null }, halfTime: { home: null, away: null } } },
    { utcDate: "2026-11-29T14:00:00Z", status: "FINISHED", matchday: 12,
      homeTeam: { name: "Club Inconnu" }, awayTeam: { name: "Olympique de Marseille" },
      score: { fullTime: { home: 0, away: 0 }, halfTime: { home: 0, away: 0 } } },
  ] }, alias, new Date("2026-11-28T17:00:00Z"));
  const [a, b, c] = r.matchs;
  assert.deepEqual([a.dom, a.ext, a.statut, a.score, a.minute, a.heure, a.date], ["angers", "lens", "en_cours", [1, 2], 67, "17:15", "2026-11-28"]);
  assert.equal(b.statut, "a_venir");
  assert.equal(b.score, null);
  assert.equal(b.heure, "20:45");
  assert.equal(c.dom, null);
  assert.equal(c.ext, "marseille");
  assert.equal(r.maj, "2026-11-28T17:00:00.000Z");
});

test("fenêtre de dates : veille, jour, lendemain", () => {
  assert.deepEqual(fenetre(new Date("2026-11-28T10:00:00Z")), { dateFrom: "2026-11-27", dateTo: "2026-11-29" });
});
