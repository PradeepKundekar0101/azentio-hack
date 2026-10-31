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

  it("match the app's primary, so the logo tile is the same blue as the buttons", () => {
    const primary = read("./theme.css").match(/^\s*--primary:\s*(#[0-9a-f]{6});/im)?.[1];
    expect(primary?.toLowerCase()).toBe(brand.blue);
  });
});

describe("favicon", () => {
  const icon = read("../app/icon.svg");

  it("draws the logo geometry", () => {
    expect(icon).toContain(`viewBox="${logoMark.viewBox}"`);
    expect(icon).toContain(`rx="${logoMark.radius}"`);
    expect(icon).toContain(`d="${logoMark.form}"`);
    expect(icon).toContain(`d="${logoMark.lines}"`);
    expect(icon).toContain(`d="${logoMark.drop}"`);
    expect(icon).toContain(`stroke-width="${logoMark.strokeWidth}"`);
  });

  it("uses the brand colours", () => {
    expect(icon).toContain(`fill="${brand.blue}"`);
    expect(icon).toContain(`stroke="${brand.onInk}"`);
    expect(icon).toContain(`fill="${brand.onInk}"`);
  });
});
