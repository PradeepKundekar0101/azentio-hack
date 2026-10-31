"use client";

import { ScanText } from "lucide-react";
import Link from "next/link";

import { Pagination, parsePage, StateMessage, TableStateRows } from "@/components/data-table";
import { EmptyState } from "@/components/empty-state";
import { FormatList } from "@/components/format-list";
import { Panel, PanelHeader } from "@/components/page";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getErrorMessage } from "@/lib/api/errors";
import { useDocumentList } from "@/lib/documents/hooks";
import type { DocumentRow } from "@/lib/documents/model";
import { EMPTY, formatBytes, formatDateTime } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";

import { DocumentFileIcon, ParseStatusBadge } from "./document-status";

const PAGE_SIZE = 10;
const URL_DEFAULTS = { page: "1" };
const COLUMNS = 5;

const linkClass =
  "rounded-sm font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring";

/** Uploaded documents, newest first, each linking to its review page. */
export function DocumentList() {
  const [url, setUrl] = useUrlState(URL_DEFAULTS);
  const page = parsePage(url.page);
  const list = useDocumentList(page, PAGE_SIZE);
  const total = list.data?.total;

  if (total === 0 && page === 1) {
    return (
      <EmptyState
        icon={ScanText}
        title="No documents yet"
        description="Each uploaded invoice appears here while it is read, then waits for you to review and confirm its claim."
        className="py-10 sm:py-12"
      >
        <FormatList label="Accepted formats" formats={["PDF", "PNG", "JPEG"]} note="Claims are checked against imported policies." />
      </EmptyState>
    );
  }

  return (
    <Panel aria-labelledby="documents-title">
      <PanelHeader
        title={<span id="documents-title">Uploaded documents</span>}
        description="Open a document to compare what was read with the original and confirm its claim."
      />
      {/* Phones get a stacked list so the status stays in view. */}
      <div className="md:hidden">
        {list.isPending ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading documents">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : list.isError ? (
          <div className="px-4 py-10">
            <StateMessage error={getErrorMessage(list.error)} onRetry={() => list.refetch()} />
          </div>
        ) : (
          <ul aria-labelledby="documents-title" className="divide-y">
            {list.data.items.map((doc) => (
              <DocumentItem key={doc.id} doc={doc} />
            ))}
          </ul>
        )}
      </div>
      <div className="hidden md:block">
        <Table aria-labelledby="documents-title" className="min-w-[680px]">
          <TableHeader>
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead className="text-right">Size</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Claim</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableStateRows
              colSpan={COLUMNS}
              isLoading={list.isPending}
              error={list.isError ? getErrorMessage(list.error) : null}
              onRetry={() => list.refetch()}
              isEmpty={list.data?.items.length === 0}
              emptyTitle="No documents on this page"
              skeletonRows={4}
            />
            {list.data?.items.map((doc) => <DocumentTableRow key={doc.id} doc={doc} />)}
          </TableBody>
        </Table>
      </div>
      {total !== undefined && total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          isFetching={list.isFetching}
          onPage={(p) => setUrl({ page: String(p) })}
        />
      )}
    </Panel>
  );
}

function DocumentTableRow({ doc }: { doc: DocumentRow }) {
  return (
    <TableRow>
      <TableCell className="max-w-80">
        <div className="flex min-w-0 items-center gap-2">
          <DocumentFileIcon fileType={doc.file_type} />
          <Link href={`/documents/${doc.id}`} className={`${linkClass} truncate`} title={doc.file_name}>
            {doc.file_name}
          </Link>
        </div>
      </TableCell>
      <TableCell className="num text-muted-foreground">{formatDateTime(doc.created_at)}</TableCell>
      <TableCell className="num text-right text-muted-foreground">{formatBytes(doc.size_bytes)}</TableCell>
      <TableCell>
        <ParseStatusBadge status={doc.parse_status} />
      </TableCell>
      <TableCell>
        {doc.claim_id ? (
          <Link href={`/claims/${doc.claim_id}`} className={linkClass}>
            <span className="num">{doc.claim_id}</span>
          </Link>
        ) : (
          <span className="text-muted-foreground">{EMPTY}</span>
        )}
      </TableCell>
    </TableRow>
  );
}

function DocumentItem({ doc }: { doc: DocumentRow }) {
  return (
    <li>
      <Link
        href={`/documents/${doc.id}`}
        className="block space-y-1.5 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="flex min-w-0 items-center gap-2">
          <DocumentFileIcon fileType={doc.file_type} />
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-primary">{doc.file_name}</span>
          <ParseStatusBadge status={doc.parse_status} />
        </div>
        <p className="num pl-6 text-xs text-muted-foreground">
          {formatDateTime(doc.created_at)} · {formatBytes(doc.size_bytes)}
          {doc.claim_id && (
            <>
              {" "}
              · Claim <span className="font-medium text-foreground">{doc.claim_id}</span>
            </>
          )}
        </p>
      </Link>
    </li>
  );
}
