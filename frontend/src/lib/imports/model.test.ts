import { describe, expect, it } from "vitest";

import { addFiles, datasetLabel, isReconciled, issueLocation, MAX_FILE_BYTES, MAX_FILES, sortDatasets } from "./model";

function file(name: string, size = 10): File {
  return new File([new Uint8Array(size)], name, { lastModified: 1 });
}

describe("datasetLabel", () => {
  it.each([
    ["policies", "Policies"],
    ["policy_rules", "Policy rules"],
    ["line_items", "Line items"],
    ["unrecognised", "Unrecognised"],
    ["provider_notes", "Provider notes"],
    [null, "File"],
  ])("%s -> %s", (dataset, expected) => {
    expect(datasetLabel(dataset)).toBe(expected);
  });
});

describe("sortDatasets", () => {
  it("puts datasets in load order, unknown ones after, unrecognised last", () => {
    expect(sortDatasets(["unrecognised", "settlements", "extra", "claims", "policies", "claims"])).toEqual([
      "policies",
      "claims",
      "settlements",
      "extra",
      "unrecognised",
    ]);
  });
});

describe("isReconciled", () => {
  it("holds when received equals the three outcomes", () => {
    expect(isReconciled({ received: 312, accepted: 301, warnings: 4, rejected: 7 })).toBe(true);
    expect(isReconciled({ received: 312, accepted: 300, warnings: 4, rejected: 7 })).toBe(false);
  });
});

describe("addFiles", () => {
  it("accepts CSV, Excel and JSON files regardless of extension case", () => {
    const { files, problems } = addFiles([], [file("claims.csv"), file("Pack.XLSX"), file("rules.json")]);
    expect(files.map((f) => f.file.name)).toEqual(["claims.csv", "Pack.XLSX", "rules.json"]);
    expect(problems).toEqual([]);
  });

  it("explains each file it leaves out", () => {
    const big = file("huge.csv");
    Object.defineProperty(big, "size", { value: MAX_FILE_BYTES * 1.25 });
    const { files, problems } = addFiles(
      [],
      [file("notes.txt"), file("blank.csv", 0), big, file("a.csv"), file("A.csv")],
    );
    expect(files.map((f) => f.file.name)).toEqual(["a.csv"]);
    expect(problems).toEqual([
      "notes.txt is not a CSV, Excel (.xlsx) or JSON file.",
      "blank.csv is empty.",
      "huge.csv is larger than 20\u00a0MB (25\u00a0MB).",
      "A.csv is already in the list.",
    ]);
  });

  it("stops at the file limit", () => {
    const many = Array.from({ length: MAX_FILES + 2 }, (_, i) => file(`f${i}.csv`));
    const { files, problems } = addFiles([], many);
    expect(files).toHaveLength(MAX_FILES);
    expect(problems).toHaveLength(2);
    expect(problems[0]).toContain("at most 10 files");
  });
});

describe("issueLocation", () => {
  it("shows the sheet when there is one, and File for file-level issues", () => {
    expect(issueLocation({ file_name: "pack.xlsx", sheet: "Claims", row_number: 1204 })).toEqual({
      file: "pack.xlsx",
      detail: "Claims · Row 1,204",
    });
    expect(issueLocation({ file_name: "pack.xlsx", sheet: "Claims", row_number: null })).toEqual({
      file: "pack.xlsx",
      detail: "Claims · File",
    });
    expect(issueLocation({ file_name: "claims.csv", sheet: null, row_number: null })).toEqual({
      file: "claims.csv",
      detail: "File",
    });
  });
});
