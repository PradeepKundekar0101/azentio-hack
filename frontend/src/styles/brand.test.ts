import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { brand } from "./brand";

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
