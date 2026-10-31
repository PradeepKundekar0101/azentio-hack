import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { brand, logoMark } from "./brand";

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), "utf8");

const camel = (kebab: string) => kebab.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());

describe("brand tokens", () => {
  it("mirror the brand block of theme.css exactly", () => {
    const declared = Object.fromEntries(
      [...read("./theme.css").matchAll(/--brand-([a-z-]+):\s*(#[0-9a-f]{6})\s*;/gi)].map(([, name, value]) => [
        camel(name),
        value.toLowerCase(),
      ]),
    );
    expect(declared).toEqual(brand);
  });
});

describe("favicon", () => {
  const icon = read("../app/icon.svg");

  it("draws the logo geometry", () => {
    expect(icon).toContain(`viewBox="${logoMark.viewBox}"`);
    expect(icon).toContain(`d="${logoMark.lines}"`);
    expect(icon).toContain(`d="${logoMark.leak}"`);
  });

  it("uses the brand colours", () => {
    expect(icon).toContain(`fill="${brand.ink}"`);
    expect(icon).toContain(`fill="${brand.onInk}"`);
    expect(icon).toContain(`fill="${brand.signal}"`);
  });
});

describe("logo geometry", () => {
  it("keeps the leaked block inside the tile", () => {
    const numbers = (path: string) => [...path.matchAll(/-?\d+(?:\.\d+)?/g)].map(([n]) => Number(n));
    for (const n of [...numbers(logoMark.lines), ...numbers(logoMark.leak)]) {
      expect(Math.abs(n)).toBeLessThanOrEqual(logoMark.size);
    }
  });
});
