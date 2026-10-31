"use client";

import { CircleAlert, LoaderCircle, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";

import { Panel, PanelHeader } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { getErrorMessage } from "@/lib/api/errors";
import { useUploadDocument } from "@/lib/documents/hooks";
import { ACCEPT_ATTRIBUTE, checkDocumentFile, MAX_DOCUMENT_BYTES } from "@/lib/documents/model";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

import { DocumentFileIcon } from "./document-status";

function typeOf(file: File): string {
  return file.name.toLowerCase().endsWith(".pdf") ? "pdf" : "image";
}

/** Drag-and-drop (or click) upload of one invoice PDF or image, then on to its review page. */
export function UploadPanel() {
  const router = useRouter();
  const upload = useUploadDocument();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const hintId = useId();

  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragDepth, setDragDepth] = useState(0);
  const [progress, setProgress] = useState<number | null>(null);

  const busy = upload.isPending;
  const dragging = dragDepth > 0 && !busy;

  const offer = (incoming: FileList | null) => {
    if (!incoming || incoming.length === 0) return;
    const [first] = Array.from(incoming);
    const reason =
      incoming.length > 1 ? "Upload one document at a time." : checkDocumentFile(first);
    upload.reset();
    if (reason) {
      setProblem(reason);
      return;
    }
    setProblem(null);
    setFile(first);
  };

  const openPicker = () => {
    if (!busy) inputRef.current?.click();
  };

  const clear = () => {
    setFile(null);
    setProblem(null);
    upload.reset();
  };

  const start = () => {
    if (!file || busy) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setProgress(null);
    upload.mutate(
      { file, onProgress: setProgress, signal: controller.signal },
      {
        onSuccess: (doc) => {
          toast.success(`${doc.file_name} uploaded. Reading the invoice now.`);
          router.push(`/documents/${doc.id}`);
        },
        onError: (error) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            toast("Upload cancelled.");
            upload.reset();
          }
        },
        onSettled: () => {
          abortRef.current = null;
        },
      },
    );
  };

  const uploadError = upload.isError && !(upload.error instanceof DOMException) ? getErrorMessage(upload.error) : null;
  const uploading = busy && progress !== null && progress < 1;

  return (
    <Panel aria-labelledby="upload-title">
      <PanelHeader
        title={<span id="upload-title">Upload an invoice</span>}
        description="The claim and its line items are read from the document for you to check, correct and confirm."
      />
      <div className="space-y-3 p-4">
        <div
          role="button"
          aria-label="Choose an invoice to upload, or drop it here"
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
            "flex flex-col items-center justify-center rounded-lg border border-dashed border-input bg-muted/30 px-4 py-8 text-center transition-colors outline-none",
            "hover:border-primary/50 hover:bg-primary/[0.03] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
            dragging && "border-primary bg-primary/5",
            busy && "pointer-events-none opacity-60",
          )}
        >
          <div
            className={cn(
              "flex size-10 items-center justify-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15 ring-inset transition-transform",
              dragging && "scale-110",
            )}
          >
            <Upload className="size-5" aria-hidden="true" />
          </div>
          <p className="mt-3 text-sm font-medium">
            {dragging ? (
              "Drop to add the invoice"
            ) : (
              <>
                Drag an invoice here, or{" "}
                <span className="text-primary underline-offset-4 hover:underline">choose a file</span>
              </>
            )}
          </p>
          <p id={hintId} className="mt-1 text-[13px] text-muted-foreground">
            PDF, PNG or JPEG · one at a time, up to {formatBytes(MAX_DOCUMENT_BYTES)}
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => {
            offer(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
        />

        {problem && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>This file was not added</AlertTitle>
            <AlertDescription className="break-words">{problem}</AlertDescription>
          </Alert>
        )}

        {file && (
          <div className="flex min-h-10 items-center gap-2.5 rounded-lg border py-1.5 pr-1.5 pl-3">
            <DocumentFileIcon fileType={typeOf(file)} />
            <span className="min-w-0 flex-1 truncate text-sm" title={file.name}>
              {file.name}
            </span>
            <span className="num shrink-0 text-[13px] text-muted-foreground">{formatBytes(file.size)}</span>
            <Button variant="ghost" size="icon-sm" aria-label={`Remove ${file.name}`} disabled={busy} onClick={clear}>
              <X aria-hidden="true" />
            </Button>
          </div>
        )}

        {uploadError && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>Upload failed</AlertTitle>
            <AlertDescription className="break-words">{uploadError}</AlertDescription>
          </Alert>
        )}

        {busy && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-3 text-[13px]" aria-live="polite">
              <span className="font-medium">{uploading ? "Uploading" : "Storing the document"}</span>
              <span className="num text-muted-foreground">
                {uploading ? `${Math.round((progress ?? 0) * 100)}%` : "A moment"}
              </span>
            </div>
            {uploading ? (
              <Progress value={(progress ?? 0) * 100} aria-label="Upload progress" />
            ) : (
              <IndeterminateBar label="Storing the document" />
            )}
          </div>
        )}

        {file && (
          <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
            {busy ? (
              uploading && (
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
              {busy ? "Uploading" : "Upload and read"}
            </Button>
          </div>
        )}
      </div>
    </Panel>
  );
}

function IndeterminateBar({ label }: { label: string }) {
  return (
    <div role="progressbar" aria-label={label} className="relative h-1 w-full overflow-hidden rounded-full bg-muted">
      <div className="absolute inset-y-0 left-0 w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-primary motion-reduce:w-full motion-reduce:animate-pulse" />
    </div>
  );
}
