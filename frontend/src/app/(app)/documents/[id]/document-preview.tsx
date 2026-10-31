"use client";

import { ExternalLink, ImageOff, RefreshCw } from "lucide-react";
import { useState } from "react";

import { Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { fileKind } from "@/lib/documents/model";
import { formatBytes } from "@/lib/format";

import { DocumentFileIcon } from "../document-status";

/** Browser PDF viewer options: no thumbnail pane (the column is narrow), fit the page width. */
const PDF_VIEW = "#navpanes=0&view=FitH";

/**
 * The original document beside the form. The presigned link lasts 5 minutes, so the preview
 * keeps the link it first loaded (a fresh one would reload the frame and lose the reader's
 * place) and only switches to the latest link when asked to reload.
 */
export function DocumentPreview({
  url,
  fileName,
  fileType,
  sizeBytes,
}: {
  url: string;
  fileName: string;
  fileType: string;
  sizeBytes: number;
}) {
  const [src, setSrc] = useState(url);
  const [version, setVersion] = useState(0);
  const [broken, setBroken] = useState(false);
  const kind = fileKind(fileType);

  const reload = () => {
    setSrc(url);
    setBroken(false);
    setVersion((v) => v + 1);
  };

  return (
    <Panel aria-label="Original document" className="flex flex-col overflow-hidden lg:sticky lg:top-16 lg:h-[calc(100dvh-5rem)]">
      <div className="flex min-h-11 items-center gap-2 border-b py-1.5 pr-1.5 pl-4">
        <DocumentFileIcon fileType={fileType} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium" title={fileName}>
          {fileName}
        </span>
        <span className="num shrink-0 text-xs text-muted-foreground">{formatBytes(sizeBytes)}</span>
        <Button variant="ghost" size="icon-sm" aria-label="Reload preview" onClick={reload}>
          <RefreshCw aria-hidden="true" />
        </Button>
        <Button asChild variant="ghost" size="icon-sm">
          <a href={url} target="_blank" rel="noreferrer" aria-label="Open the original in a new tab">
            <ExternalLink aria-hidden="true" />
          </a>
        </Button>
      </div>
      <div className="relative h-[28rem] bg-muted/40 sm:h-[36rem] lg:h-auto lg:min-h-0 lg:flex-1">
        {kind === "pdf" ? (
          <iframe key={version} src={`${src}${PDF_VIEW}`} title={`Preview of ${fileName}`} className="absolute inset-0 size-full border-0" />
        ) : broken ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
            <ImageOff className="size-5 text-muted-foreground" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">The preview link has expired.</p>
            <Button variant="outline" size="sm" onClick={reload}>
              <RefreshCw data-icon="inline-start" aria-hidden="true" />
              Reload preview
            </Button>
          </div>
        ) : (
          <div className="absolute inset-0 overflow-auto">
            {/* A presigned storage URL: next/image would need the bucket host configured and adds nothing here. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={version}
              src={src}
              alt={`Scan of ${fileName}`}
              className="mx-auto block h-auto w-full max-w-3xl bg-white"
              onError={() => setBroken(true)}
            />
          </div>
        )}
      </div>
    </Panel>
  );
}
