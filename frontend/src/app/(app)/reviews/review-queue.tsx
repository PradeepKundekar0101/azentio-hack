"use client";

import { ArrowUpRight, Inbox, Send } from "lucide-react";
import Link from "next/link";

import { LoadError } from "@/components/app-shell/states";
import { PageHeader, Panel } from "@/components/page";
import { SeverityBadge } from "@/components/review/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { useEscalations } from "@/lib/alerts/hooks";
import { type AlertOut, categoryLabel, escalationTargetLabel } from "@/lib/alerts/model";
import { getErrorMessage } from "@/lib/api/errors";
import { useMe } from "@/lib/auth/hooks";
import { roleLabel } from "@/lib/auth/permissions";
import { formatDateTime, formatINR } from "@/lib/format";

/** Escalated alerts waiting for the signed-in user's level, and the ones they escalated themselves. */
export function ReviewQueue() {
  const query = useEscalations();
  const { data: me } = useMe();

  return (
    <>
      <PageHeader
        title="Review queue"
        description={
          me
            ? `Alerts escalated to you as ${roleLabel(me.role).toLowerCase()}, and the ones you sent up for a decision.`
            : "Alerts escalated to you, and the ones you sent up for a decision."
        }
      />
      {query.isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : query.isError ? (
        <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : (
        <div className="grid gap-6">
          <Section
            icon={Inbox}
            title="Waiting for your decision"
            empty="Nothing is escalated to your level right now."
            alerts={query.data.to_review}
            highlight
          />
          <Section
            icon={Send}
            title="You escalated"
            empty="You have no alerts waiting on someone else."
            alerts={query.data.sent}
          />
        </div>
      )}
    </>
  );
}

function Section({
  icon: Icon,
  title,
  empty,
  alerts,
  highlight = false,
}: {
  icon: typeof Inbox;
  title: string;
  empty: string;
  alerts: AlertOut[];
  highlight?: boolean;
}) {
  return (
    <Panel className="overflow-hidden">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-sm font-semibold">{title}</h2>
        <span
          className={
            highlight && alerts.length > 0
              ? "num rounded-full bg-destructive px-2 text-xs leading-5 font-semibold text-white"
              : "num text-xs text-muted-foreground"
          }
        >
          {alerts.length}
        </span>
      </div>
      {alerts.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="divide-y">
          {alerts.map((alert) => (
            <li key={alert.id}>
              <Link
                href={`/alerts/${alert.id}`}
                className="grid gap-x-6 gap-y-1 px-4 py-3.5 outline-none hover:bg-muted/50 focus-visible:bg-muted/60 sm:grid-cols-[minmax(12rem,1fr)_2fr_auto]"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold">
                    <span className="num text-primary">#{alert.id}</span> {categoryLabel(alert.category)}
                  </p>
                  <p className="num text-[13px] text-muted-foreground">
                    {alert.claim_id} · {formatINR(alert.amount)}
                  </p>
                </div>
                <div className="min-w-0 text-[13px]">
                  <p>
                    <span className="text-muted-foreground">To</span>{" "}
                    <span className="font-medium">{escalationTargetLabel(alert.escalated_to ?? "")}</span>
                    <span className="text-muted-foreground"> · by </span>
                    <span className="font-medium">{alert.escalated_by}</span>
                    <span className="text-muted-foreground"> · {formatDateTime(alert.escalated_at)}</span>
                  </p>
                  {alert.escalation_reason && (
                    <p className="truncate text-muted-foreground">“{alert.escalation_reason}”</p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <SeverityBadge severity={alert.severity} />
                  <ArrowUpRight className="size-4 text-muted-foreground" aria-hidden="true" />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
