"use client";

import { CircleCheck, Download, FilterX } from "lucide-react";

import {
  FilterSelect,
  Pagination,
  parsePage,
  parsePageSize,
  StateMessage,
  TableStateRows,
} from "@/components/data-table";
import { Panel, PanelHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getErrorMessage } from "@/lib/api/errors";
import { EMPTY, formatNumber } from "@/lib/format";
import { issuesCsvUrl, useImportIssues } from "@/lib/imports/hooks";
import { datasetLabel, type ImportIssue, isSeverity, issueLocation, SEVERITY_LABELS } from "@/lib/imports/model";
import { useUrlState } from "@/lib/use-url-state";

import { SeverityBadge } from "../import-status";

/** Issue filters live in the URL so a filtered view can be shared and survives reloads. */
export const ISSUE_URL_DEFAULTS = { dataset: "", severity: "", page: "1", size: "25" };

const SEVERITY_OPTIONS = [
  { value: "error", label: SEVERITY_LABELS.error },
  { value: "warning", label: SEVERITY_LABELS.warning },
] as const;

const COLUMNS = 6;

export function IssuesPanel({
  batchId,
  datasets,
  failed = false,
}: {
  batchId: number;
  datasets: string[];
  /** The batch failed as a whole; its reason is shown above the panel. */
  failed?: boolean;
}) {
  const [url, setUrl] = useUrlState(ISSUE_URL_DEFAULTS);
  const severity = isSeverity(url.severity) ? url.severity : "";
  const filters = {
    dataset: url.dataset,
    severity,
    page: parsePage(url.page),
    pageSize: parsePageSize(url.size),
  } as const;
  const issues = useImportIssues(batchId, filters);
  const total = issues.data?.total;
  const filtered = Boolean(filters.dataset || filters.severity);
  const datasetOptions = datasets.map((d) => ({ value: d, label: datasetLabel(d) }));
  // Keep a dataset from the URL selectable even if the batch has no counts for it.
  if (filters.dataset && !datasets.includes(filters.dataset)) {
    datasetOptions.push({ value: filters.dataset, label: datasetLabel(filters.dataset) });
  }

  const stateProps = {
    error: issues.isError ? getErrorMessage(issues.error) : null,
    onRetry: () => issues.refetch(),
    emptyIcon: filtered ? FilterX : CircleCheck,
    emptyTitle: filtered ? "No issues match these filters" : "No issues",
    emptyHint: filtered
      ? "Try another dataset or severity."
      : failed
        ? "No row was checked. The reason the import failed is shown above."
        : "Every row in this import was accepted.",
  };

  return (
    <Panel id="issues" aria-labelledby="issues-title" className="scroll-mt-16">
      <PanelHeader
        className="flex-wrap"
        title={
          <span id="issues-title">
            Issues
            {total !== undefined && (
              <span className="num ml-1.5 font-normal text-muted-foreground">{formatNumber(total)}</span>
            )}
          </span>
        }
        description="Rejected rows and warnings, with the value that caused each one."
        actions={
          total === 0 ? (
            <Button variant="outline" size="sm" disabled>
              <Download data-icon="inline-start" aria-hidden="true" />
              Download error report (CSV)
            </Button>
          ) : (
            <Button variant="outline" size="sm" asChild>
              <a href={issuesCsvUrl(batchId, filters)} download>
                <Download data-icon="inline-start" aria-hidden="true" />
                Download error report (CSV)
              </a>
            </Button>
          )
        }
      />
      <div role="group" aria-label="Filter issues" className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
        <FilterSelect
          label="Dataset"
          value={filters.dataset}
          options={datasetOptions}
          onChange={(dataset) => setUrl({ dataset, page: "1" })}
        />
        <FilterSelect
          label="Severity"
          value={filters.severity}
          options={SEVERITY_OPTIONS}
          onChange={(value) => setUrl({ severity: value, page: "1" })}
        />
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => setUrl({ dataset: "", severity: "", page: "1" })}>
            <FilterX data-icon="inline-start" aria-hidden="true" />
            Clear filters
          </Button>
        )}
      </div>
      {/* Phones get a stacked list so the message is readable without scrolling sideways. */}
      <div className="md:hidden">
        {issues.isPending ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading issues">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ) : issues.isError || issues.data.items.length === 0 ? (
          <div className="px-4 py-10">
            <StateMessage {...stateProps} />
          </div>
        ) : (
          <ul aria-labelledby="issues-title" className="divide-y">
            {issues.data.items.map((issue) => (
              <IssueItem key={issue.id} issue={issue} />
            ))}
          </ul>
        )}
      </div>
      <div className="hidden md:block">
        <Table aria-labelledby="issues-title" className="min-w-[840px] table-fixed">
          <colgroup>
            <col className="w-24" />
            <col className="w-26" />
            <col className="w-48" />
            <col className="w-38" />
            <col className="w-40" />
            <col />
          </colgroup>
          <TableHeader>
            <TableRow>
              <TableHead>Severity</TableHead>
              <TableHead>Dataset</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Field</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Message</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableStateRows
              colSpan={COLUMNS}
              isLoading={issues.isPending}
              isEmpty={issues.data?.items.length === 0}
              {...stateProps}
            />
            {issues.data?.items.map((issue) => <IssueRow key={issue.id} issue={issue} />)}
          </TableBody>
        </Table>
      </div>
      {total !== undefined && total > 0 && (
        <Pagination
          page={filters.page}
          pageSize={filters.pageSize}
          total={total}
          isFetching={issues.isFetching && !issues.isPending}
          onPage={(page) => {
            setUrl({ page: String(page) });
            // Paging from the bottom of a long table: bring the new page's first rows into view.
            const panel = document.getElementById("issues");
            if (panel && panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ block: "start" });
          }}
          onPageSize={(size) => setUrl({ size: String(size), page: "1" })}
        />
      )}
    </Panel>
  );
}

function IssueRow({ issue }: { issue: ImportIssue }) {
  const { file, detail } = issueLocation(issue);
  return (
    <TableRow className="align-top">
      <TableCell className="align-top">
        <SeverityBadge severity={issue.severity} />
      </TableCell>
      <TableCell className="align-top whitespace-normal">{issue.dataset ? datasetLabel(issue.dataset) : EMPTY}</TableCell>
      <TableCell className="align-top whitespace-normal">
        <div className="truncate" title={file}>
          {file}
        </div>
        <div className="num text-xs text-muted-foreground">{detail}</div>
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        {issue.field ? <code className="font-mono text-xs [overflow-wrap:anywhere]">{issue.field}</code> : <Muted />}
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        <IssueValue value={issue.value} />
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        <p className="text-pretty">{issue.message}</p>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{issue.code}</p>
      </TableCell>
    </TableRow>
  );
}

function IssueValue({ value }: { value: string | null }) {
  if (value === null || value === "") return <Muted label={value === "" ? "(blank)" : undefined} />;
  return (
    <code
      title={value}
      className="line-clamp-3 w-fit max-w-full rounded-sm bg-muted px-1 py-0.5 font-mono text-xs [overflow-wrap:anywhere]"
    >
      {value}
    </code>
  );
}

function IssueItem({ issue }: { issue: ImportIssue }) {
  const { file, detail } = issueLocation(issue);
  return (
    <li className="space-y-1.5 px-4 py-3 text-[13px]">
      <div className="flex items-center gap-2">
        <SeverityBadge severity={issue.severity} />
        {issue.dataset && <span className="font-medium">{datasetLabel(issue.dataset)}</span>}
        <span className="num ml-auto shrink-0 text-xs text-muted-foreground">{detail}</span>
      </div>
      <p className="text-sm text-pretty">{issue.message}</p>
      {(issue.field || issue.value) && (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1">
          {issue.field && (
            <>
              <dt className="text-xs text-muted-foreground">Field</dt>
              <dd>
                <code className="font-mono text-xs [overflow-wrap:anywhere]">{issue.field}</code>
              </dd>
            </>
          )}
          <dt className="text-xs text-muted-foreground">Value</dt>
          <dd>
            <IssueValue value={issue.value} />
          </dd>
        </dl>
      )}
      <p className="flex min-w-0 gap-1.5 text-xs text-muted-foreground">
        <span className="truncate" title={file}>
          {file}
        </span>
        <span aria-hidden="true">·</span>
        <span className="shrink-0 font-mono text-[11px]">{issue.code}</span>
      </p>
    </li>
  );
}

function Muted({ label = EMPTY }: { label?: string }) {
  return <span className="text-muted-foreground">{label}</span>;
}
