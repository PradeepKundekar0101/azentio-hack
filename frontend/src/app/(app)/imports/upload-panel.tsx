"use client";

import { CircleAlert, FileBraces, FileSpreadsheet, FileText, LoaderCircle, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";

import { IndeterminateBar } from "@/components/indeterminate-bar";
import { Panel, PanelHeader } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getErrorMessage } from "@/lib/api/errors";
import { formatBytes, formatNumber } from "@/lib/format";
import { useUploadImport } from "@/lib/imports/hooks";
import {
  ACCEPT_ATTRIBUTE,
  addFiles,
  DATASET_ORDER,
  type DatasetHint,
  datasetLabel,
  MAX_FILE_BYTES,
  MAX_FILES,
  type PendingFile,
} from "@/lib/imports/model";
import { cn } from "@/lib/utils";

const DETECT = "__detect";

const PHASE_LABELS = {
  working: "Uploading and checking every row",
  uploading: "Uploading files",
  checking: "Checking every row",
} as const;

function FileIcon({ name, className }: { name: string; className?: string }) {
  const lower = name.toLowerCase();
  const Icon = lower.endsWith(".xlsx") ? FileSpreadsheet : lower.endsWith(".json") ? FileBraces : FileText;
  return <Icon className={className} aria-hidden="true" />;
}

/** Drag-and-drop (or click) upload of CSV, Excel and JSON files into a new import batch. */
export function UploadPanel() {
  const router = useRouter();
  const upload = useUploadImport();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const hintId = useId();
  const datasetId = useId();

  const [files, setFiles] = useState<PendingFile[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [dataset, setDataset] = useState<string>(DETECT);
  const [dragDepth, setDragDepth] = useState(0);
  // Fraction of bytes sent, or null until the browser reports upload progress (it may never
  // for small files), in which case one indeterminate phase covers upload and processing.
  const [progress, setProgress] = useState<number | null>(null);

  const busy = upload.isPending;
  const dragging = dragDepth > 0 && !busy;
  const needsDatasetHint = files.some((f) => !f.file.name.toLowerCase().endsWith(".xlsx"));
  const totalBytes = files.reduce((sum, f) => sum + f.file.size, 0);

  const offer = (incoming: FileList | null) => {
    if (!incoming || incoming.length === 0) return;
    const next = addFiles(files, Array.from(incoming));
    setFiles(next.files);
    setProblems(next.problems);
    upload.reset();
  };

  const openPicker = () => {
    if (!busy) inputRef.current?.click();
  };

  const remove = (key: string) => {
    setFiles((current) => current.filter((f) => f.key !== key));
    setProblems([]);
  };

  const clear = () => {
    setFiles([]);
    setProblems([]);
    setDataset(DETECT);
    upload.reset();
  };

  const start = () => {
    if (files.length === 0 || busy) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setProgress(null);
    setProblems([]);
    upload.mutate(
      {
        files: files.map((f) => f.file),
        dataset: dataset === DETECT || !needsDatasetHint ? undefined : (dataset as DatasetHint),
        onProgress: setProgress,
        signal: controller.signal,
      },
      {
        onSuccess: (batch) => {
          const rows = formatNumber(batch.totals.received);
          if (batch.status === "failed") toast.error(`Import #${batch.id} failed. See the details for the reason.`);
          else toast.success(`Import #${batch.id} processed: ${rows} rows received.`);
          router.push(`/imports/${batch.id}`);
        },
        onError: (error) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            toast("Upload cancelled.");
            upload.reset();
          }
          // Other errors are shown inline next to the files, where they can be fixed.
        },
        onSettled: () => {
          abortRef.current = null;
        },
      },
    );
  };

  const phase = !busy ? null : progress === null ? "working" : progress < 1 ? "uploading" : "checking";
  const uploadError = upload.isError && !(upload.error instanceof DOMException) ? getErrorMessage(upload.error) : null;

  return (
    <Panel aria-labelledby="upload-title">
      <PanelHeader
        title={<span id="upload-title">Upload files</span>}
        description="An Excel workbook can carry every dataset, one per sheet. CSV and JSON files are matched by file name or headers."
      />
      <div className="space-y-3 p-4">
        <div
          role="button"
          aria-label="Choose files to import, or drop them here"
          tabIndex={busy ? -1 : 0}
          aria-disabled={busy || undefined}
          aria-describedby={hintId}
          onClick={openPicker}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openPicker();
            }
          }}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragDepth((d) => d + 1);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragDepth((d) => Math.max(0, d - 1));
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = busy ? "none" : "copy";
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragDepth(0);
            if (!busy) offer(event.dataTransfer.files);
          }}
          className={cn(
            "surface-grid relative flex flex-col items-center justify-center rounded-xl border border-dashed border-input/70 bg-muted/20 px-4 py-8 text-center transition-[border-color,background-color] outline-none hover:border-primary/40 hover:bg-primary/4",
            "hover:border-primary/50 hover:bg-primary/[0.03] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
            dragging && "border-primary bg-primary/5",
            busy && "pointer-events-none opacity-60",
          )}
        >
          <div
            className={cn(
              "flex size-12 items-center justify-center rounded-xl bg-[linear-gradient(to_bottom,color-mix(in_oklch,var(--primary)_14%,var(--card)),color-mix(in_oklch,var(--primary)_6%,var(--card)))] text-primary shadow-raised ring-1 ring-primary/15 ring-inset transition-transform",
              dragging && "scale-110",
            )}
          >
            <Upload className="size-5" aria-hidden="true" />
          </div>
          <p className="mt-3 text-sm font-medium">
            {dragging ? (
              "Drop to add the files"
            ) : (
              <>
                Drag files here, or <span className="text-primary underline-offset-4 hover:underline">choose files</span>
              </>
            )}
          </p>
          <p id={hintId} className="mt-1 text-[13px] text-muted-foreground">
            CSV, Excel (.xlsx) or JSON · up to {MAX_FILES} files, {formatBytes(MAX_FILE_BYTES)} each
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => {
            offer(event.currentTarget.files);
            // Allow choosing the same file again after removing it.
            event.currentTarget.value = "";
          }}
        />

        {problems.length > 0 && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>
              {problems.length === 1 ? "One file was not added" : `${problems.length} files were not added`}
            </AlertTitle>
            <AlertDescription>
              <ul className="space-y-0.5">
                {problems.map((p) => (
                  <li key={p} className="break-words">
                    {p}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {files.length > 0 && (
          <div className="rounded-lg border">
            <div className="flex items-center justify-between gap-3 border-b px-3 py-2 text-[13px] text-muted-foreground">
              <span>
                <span className="num font-medium text-foreground">{formatNumber(files.length)}</span>{" "}
                {files.length === 1 ? "file" : "files"} selected
              </span>
              <span className="num">{formatBytes(totalBytes)}</span>
            </div>
            <ul aria-label="Files to upload" className="divide-y">
              {files.map(({ key, file }) => (
                <li key={key} className="flex min-h-10 items-center gap-2.5 py-1.5 pr-1.5 pl-3">
                  <FileIcon name={file.name} className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-sm" title={file.name}>
                    {file.name}
                  </span>
                  <span className="num shrink-0 text-[13px] text-muted-foreground">{formatBytes(file.size)}</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${file.name}`}
                    disabled={busy}
                    onClick={() => remove(key)}
                  >
                    <X aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {uploadError && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>Upload failed</AlertTitle>
            <AlertDescription>{uploadError}</AlertDescription>
          </Alert>
        )}

        {phase && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-3 text-[13px]" aria-live="polite">
              <span className="font-medium">{PHASE_LABELS[phase]}</span>
              <span className="num text-muted-foreground">
                {phase === "uploading" ? `${Math.round((progress ?? 0) * 100)}%` : "This can take a few seconds"}
              </span>
            </div>
            {phase === "uploading" ? (
              <Progress value={(progress ?? 0) * 100} aria-label="Upload progress" />
            ) : (
              <IndeterminateBar label={PHASE_LABELS[phase]} />
            )}
          </div>
        )}

        {files.length > 0 && (
          <div className="flex flex-wrap items-end justify-between gap-3 pt-1">
            {needsDatasetHint ? (
              <div className="flex min-w-0 flex-col gap-1.5">
                <label htmlFor={datasetId} className="text-[13px] font-medium">
                  Dataset for CSV and JSON files
                </label>
                <Select value={dataset} onValueChange={setDataset} disabled={busy}>
                  <SelectTrigger id={datasetId} className="w-64 max-w-full bg-card">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper" align="start">
                    <SelectItem value={DETECT}>Detect from name or headers</SelectItem>
                    {DATASET_ORDER.map((d) => (
                      <SelectItem key={d} value={d}>
                        {datasetLabel(d)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <span />
            )}
            <div className="ml-auto flex items-center gap-2">
              {busy ? (
                phase === "uploading" && (
                  <Button variant="outline" onClick={() => abortRef.current?.abort()}>
                    Cancel
                  </Button>
                )
              ) : (
                <Button variant="outline" onClick={clear}>
                  Clear
                </Button>
              )}
              <Button onClick={start} disabled={busy}>
                {busy ? (
                  <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />
                ) : (
                  <Upload data-icon="inline-start" aria-hidden="true" />
                )}
                {busy ? "Importing" : files.length === 1 ? "Import 1 file" : `Import ${formatNumber(files.length)} files`}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
