import assert from "node:assert/strict";
import test from "node:test";
import { countries, findCountries } from "../src/countries.js";

test("country list has unique two-letter codes and full names", () => {
  assert.ok(countries.length >= 240);
  assert.equal(new Set(countries.map(({ code }) => code)).size, countries.length);
  assert.ok(countries.every(({ code, name }) => /^[A-Z]{2}$/.test(code) && name && name !== code));
});

test("country search accepts names, codes, and common aliases", () => {
  assert.equal(findCountries("germany")[0].code, "DE");
  assert.equal(findCountries("de")[0].code, "DE");
  assert.equal(findCountries("uk")[0].code, "GB");
  assert.equal(findCountries("côte").find(({ code }) => code === "CI").code, "CI");
  assert.deepEqual(findCountries("not-a-country"), []);
});

test("most common workshop markets appear first before a search", () => {
  assert.deepEqual(findCountries("").slice(0, 3).map(({ code }) => code), ["US", "GB", "DE"]);
});
