/**
 * Pure helpers for the Imports pages: dataset names and load order, client-side upload
 * checks and the reconciliation equation. No React or network code here, so it is unit
 * tested directly.
 */
import type { Schemas } from "@/lib/api/client";

import { formatBytes, formatNumber } from "../format";

export type ImportBatch = Schemas["ImportBatchOut"];
export type ImportIssue = Schemas["ImportIssueOut"];
export type DatasetCounts = Schemas["DatasetCounts"];
export type DatasetHint = Schemas["Dataset"];
export type IssueSeverity = Schemas["IssueSeverity"];

/** Datasets in the order the backend loads them (parents before children). */
export const DATASET_ORDER = ["policies", "policy_rules", "claims", "line_items", "settlements"] as const;

/** Rows the backend could not match to any dataset. */
export const UNRECOGNISED = "unrecognised";

const DATASET_LABELS: Record<string, string> = {
  policies: "Policies",
  policy_rules: "Policy rules",
  claims: "Claims",
  line_items: "Line items",
  settlements: "Settlements",
  [UNRECOGNISED]: "Unrecognised",
};

/** "line_items" -> "Line items". Unknown keys are made readable rather than hidden. */
export function datasetLabel(dataset: string | null | undefined): string {
  if (!dataset) return "File";
  const known = DATASET_LABELS[dataset];
  if (known) return known;
  const words = dataset.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function datasetRank(dataset: string): number {
  const index = (DATASET_ORDER as readonly string[]).indexOf(dataset);
  if (index >= 0) return index;
  return dataset === UNRECOGNISED ? DATASET_ORDER.length + 1 : DATASET_ORDER.length;
}

/** Dataset keys in load order; unknown datasets follow, and "unrecognised" comes last. */
export function sortDatasets(datasets: Iterable<string>): string[] {
  return [...new Set(datasets)].sort((a, b) => datasetRank(a) - datasetRank(b) || a.localeCompare(b));
}

/** True when received = accepted + accepted with warnings + rejected. */
export function isReconciled(counts: DatasetCounts): boolean {
  return counts.received === counts.accepted + counts.warnings + counts.rejected;
}

export const SEVERITY_LABELS: Record<IssueSeverity, string> = {
  error: "Error",
  warning: "Warning",
};

export function isSeverity(value: string): value is IssueSeverity {
  return value === "error" || value === "warning";
}

// Upload limits, matching backend/app/api/imports.py.
export const MAX_FILE_BYTES = 20 * 1024 * 1024;
export const MAX_FILES = 10;
export const ACCEPTED_EXTENSIONS = [".csv", ".xlsx", ".json"] as const;
/** For the file input's `accept`: extensions plus their usual media types. */
export const ACCEPT_ATTRIBUTE = [
  ...ACCEPTED_EXTENSIONS,
  "text/csv",
  "application/json",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
].join(",");

export interface PendingFile {
  /** Stable key for lists: name, size and last-modified time. */
  key: string;
  file: File;
}

export interface FileSelection {
  files: PendingFile[];
  /** One message per file that was not added, in the order they were offered. */
  problems: string[];
}

function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

/**
 * Adds newly chosen files to the current selection, keeping only files the backend will
 * accept: a supported extension, not empty, at most 20 MB, at most 10 files in all, and no
 * second file with the same name.
 */
export function addFiles(current: PendingFile[], incoming: Iterable<File>): FileSelection {
  const files = [...current];
  const problems: string[] = [];
  const names = new Set(current.map((p) => p.file.name.toLowerCase()));

  for (const file of incoming) {
    const ext = extensionOf(file.name);
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) {
      problems.push(`${file.name} is not a CSV, Excel (.xlsx) or JSON file.`);
    } else if (file.size === 0) {
      problems.push(`${file.name} is empty.`);
    } else if (file.size > MAX_FILE_BYTES) {
      problems.push(`${file.name} is larger than ${formatBytes(MAX_FILE_BYTES)} (${formatBytes(file.size)}).`);
    } else if (names.has(file.name.toLowerCase())) {
      problems.push(`${file.name} is already in the list.`);
    } else if (files.length >= MAX_FILES) {
      problems.push(`${file.name} was not added: upload at most ${MAX_FILES} files at once.`);
    } else {
      files.push({ key: fileKey(file), file });
      names.add(file.name.toLowerCase());
    }
  }
  return { files, problems };
}

/**
 * Where an issue was found: the file, then the sheet (for workbooks) and the row. Issues about
 * a whole file or sheet have no row and read "File".
 */
export function issueLocation(issue: Pick<ImportIssue, "file_name" | "sheet" | "row_number">): {
  file: string;
  detail: string;
} {
  const row = issue.row_number === null ? "File" : `Row ${formatNumber(issue.row_number)}`;
  return { file: issue.file_name, detail: issue.sheet ? `${issue.sheet} · ${row}` : row };
}
