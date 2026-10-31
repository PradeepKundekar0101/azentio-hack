"use client";

import "react-pdf/dist/Page/TextLayer.css";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { Skeleton } from "@/components/ui/skeleton";
import type { Target } from "@/lib/documents/comparison";

// The worker must be set in the module that renders react-pdf's components (see its README).
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

function Highlight({ target }: { target: Target | null }) {
  if (!target?.bbox) return null;
  const { l, t, r, b } = target.bbox;
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute rounded-[2px] bg-warning/20 ring-2 ring-warning"
      style={{ left: `${l * 100}%`, top: `${t * 100}%`, width: `${(r - l) * 100}%`, height: `${(b - t) * 100}%` }}
    />
  );
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

/**
 * One page of a supporting document with the selected value's box highlighted. PDFs render with PDF.js; scans are
 * shown as images. Pages and boxes come from the extraction's provenance.
 */
export function DocumentViewer({ url, fileType, target }: { url: string; fileType: string; target: Target | null }) {
  const { ref, width } = useWidth();
  const [pages, setPages] = useState(1);
  const page = Math.min(target?.page ?? 1, pages);
  return (
    <div ref={ref} className="w-full">
      {fileType === "pdf" ? (
        <Document
          file={url}
          options={{ withCredentials: true }}
          onLoadSuccess={({ numPages }) => setPages(numPages)}
          loading={<Skeleton className="aspect-[1/1.414] w-full" />}
          error={<p className="p-4 text-[13px] text-destructive">The document could not be loaded.</p>}
        >
          <div className="relative w-fit shadow-sm">
            {width > 0 && <Page pageNumber={page} width={width} renderAnnotationLayer={false} renderTextLayer={false} />}
            <Highlight target={target?.page === page ? target : null} />
          </div>
        </Document>
      ) : (
        <div className="relative w-full shadow-sm">
          {/* eslint-disable-next-line @next/next/no-img-element -- a private, same-origin scan */}
          <img src={url} alt="Scanned document" className="block w-full" />
          <Highlight target={target} />
        </div>
      )}
      {pages > 1 && (
        <p className="num mt-2 text-center text-[12px] text-muted-foreground">
          Page {page} of {pages}
        </p>
      )}
    </div>
  );
}
