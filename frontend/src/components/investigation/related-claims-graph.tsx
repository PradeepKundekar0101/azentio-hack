"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import {
  Building2,
  FileText,
  Files,
  type LucideIcon,
  Network,
  ReceiptText,
  ShieldCheck,
  Siren,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useMemo, useState } from "react";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { Panel, PanelHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { useNodeRecords, useRelated } from "@/lib/graph/hooks";
import {
  describeEvidence,
  edgeHeadline,
  ENTITY_LABELS,
  type EntityType,
  type GraphEdgeData,
  type GraphNodeData,
  type GroupOut,
  layoutRelated,
  linkLabel,
  type RelatedOut,
} from "@/lib/graph/model";
import { cn } from "@/lib/utils";

const ICONS: Record<EntityType, LucideIcon> = {
  claim: FileText,
  policy: ShieldCheck,
  claimant: UserRound,
  provider: Building2,
  invoice: ReceiptText,
  incident: Siren,
  document: Files,
};

const TAG_LABELS: Record<string, string> = {
  INVOICE_REUSED_ACROSS_POLICIES: "Invoice reused across policies",
  INCIDENT_CLAIMED_TWICE: "Incident claimed twice",
  CONCURRENT_STAYS: "Concurrent stays",
  DOCUMENT_REUSED: "Document reused",
  DUPLICATE_CLUSTER: "Duplicate cluster",
  WEAK_PATTERN: "Weak pattern",
};

export function tagLabel(tag: string): string {
  return TAG_LABELS[tag] ?? tag;
}

function HiddenHandles({ sides = false }: { sides?: boolean }) {
  return (
    <>
      <Handle type="target" position={Position.Top} className="opacity-0" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} className="opacity-0" isConnectable={false} />
      {sides && (
        <>
          <Handle id="left" type="target" position={Position.Left} className="opacity-0" isConnectable={false} />
          <Handle id="right" type="source" position={Position.Right} className="opacity-0" isConnectable={false} />
        </>
      )}
    </>
  );
}

function ClaimNode({ data, selected }: NodeProps<Node<GraphNodeData>>) {
  const attributes = (data.node.attributes ?? {}) as Record<string, string>;
  return (
    <div
      className={cn(
        "w-[200px] rounded-md border bg-card px-3 py-2 text-left shadow-xs",
        data.focus && "border-primary ring-2 ring-primary/25",
        selected && "ring-2 ring-ring",
      )}
    >
      <HiddenHandles sides />
      <div className="flex items-center justify-between gap-2">
        <span className="num text-[13px] font-semibold">{data.node.label}</span>
        {data.focus && <span className="text-[11px] font-medium text-primary">This claim</span>}
      </div>
      <div className="num mt-0.5 text-sm">{formatINR(attributes.requested_amount)}</div>
      <div className="num mt-0.5 truncate text-[11px] text-muted-foreground">
        {attributes.policy_number} · {attributes.claimant_id}
      </div>
    </div>
  );
}

function EntityNode({ data, selected }: NodeProps<Node<GraphNodeData>>) {
  const type = data.node.node_type as EntityType;
  const Icon = ICONS[type] ?? FileText;
  const hub = !data.expanded;
  return (
    <div
      className={cn(
        "flex w-[170px] items-center gap-2 rounded-full border bg-card px-3 py-1.5 shadow-xs",
        hub && "border-dashed bg-muted text-muted-foreground",
        selected && "ring-2 ring-ring",
      )}
      title={hub ? `${ENTITY_LABELS[type]}: shown, not used to relate claims` : ENTITY_LABELS[type]}
    >
      <HiddenHandles />
      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <div className="truncate text-[12px] leading-4 font-medium">{data.node.label}</div>
        <div className="text-[10px] leading-3 text-muted-foreground">
          {ENTITY_LABELS[type]}
          {hub && " · not expanded"}
        </div>
      </div>
    </div>
  );
}

const NODE_TYPES = { claim: ClaimNode, entity: EntityNode };

type Selection = { kind: "edge"; edge: Edge<GraphEdgeData> } | { kind: "node"; node: Node<GraphNodeData> } | null;

function LinkEvidence({ link }: { link: GraphEdgeData["edge"] }) {
  const strong = link.strength === "strong";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={strong ? "default" : "outline"}>{strong ? "Strong link" : "Weak link"}</Badge>
        <span className="text-[12px] text-muted-foreground">{linkLabel(link.edge_type)} · rule-based</span>
      </div>
      <p className="text-sm font-medium text-pretty">{edgeHeadline(link)}</p>
      <dl className="space-y-2">
        {describeEvidence(link).map((row) => (
          <div key={row.label}>
            <dt className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{row.label}</dt>
            <dd className="num text-[13px] break-words">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function EdgeDetails({ edge }: { edge: Edge<GraphEdgeData> }) {
  const data = edge.data!;
  if (data.strength === "structural") {
    return (
      <p className="text-[13px] text-muted-foreground">
        A structural edge: {edge.source.split(":")[1]} is {data.edge.edge_type.replaceAll("_", " ")}{" "}
        {edge.target.split(":").slice(1).join(":")}. Structural edges never relate claims on their own.
      </p>
    );
  }
  const weakOnly = data.links.every((link) => link.strength === "weak");
  return (
    <div className="space-y-4">
      {data.links.map((link) => (
        <LinkEvidence key={link.edge_id} link={link} />
      ))}
      {weakOnly && data.links.length < 2 && (
        <p className="text-[12px] text-muted-foreground">
          A single weak signal does not relate two claims; it takes two or more.
        </p>
      )}
    </div>
  );
}

function NodeDetails({ node }: { node: Node<GraphNodeData> }) {
  const query = useNodeRecords(node.id);
  const type = node.data.node.node_type as EntityType;
  if (query.isPending) return <Skeleton className="h-32 w-full" />;
  if (query.isError) return <p className="text-[13px] text-destructive">{getErrorMessage(query.error)}</p>;
  const records = query.data;
  return (
    <div className="space-y-3">
      <div>
        <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{ENTITY_LABELS[type]}</div>
        <div className="num text-sm font-medium break-words">{node.data.node.label}</div>
        {!node.data.expanded && (
          <p className="mt-1 text-[12px] text-muted-foreground">
            A hub: many unrelated claims share it, so it is never used to relate claims.
          </p>
        )}
      </div>
      <section>
        <h3 className="text-[12px] font-semibold">
          Claims <span className="num font-normal text-muted-foreground">({records.claims.length}{records.truncated ? "+" : ""})</span>
        </h3>
        <ul className="mt-1 max-h-40 space-y-1 overflow-auto">
          {records.claims.map((claim) => (
            <li key={claim.claim_id} className="flex justify-between gap-2 text-[13px]">
              <Link href={`/claims/${claim.claim_id}`} className="num text-primary hover:underline">
                {claim.claim_id}
              </Link>
              <span className="num text-muted-foreground">{formatINR(claim.requested_amount)}</span>
            </li>
          ))}
        </ul>
      </section>
      {records.lines.length > 0 && (
        <section>
          <h3 className="text-[12px] font-semibold">
            Lines <span className="num font-normal text-muted-foreground">({records.lines.length})</span>
          </h3>
          <ul className="mt-1 max-h-40 space-y-1 overflow-auto">
            {records.lines.slice(0, 40).map((line) => (
              <li key={line.line_id} className="flex justify-between gap-2 text-[12px]">
                <span className="truncate">
                  <span className="num text-muted-foreground">{line.line_id}</span> {line.service_description}
                </span>
                <span className="num shrink-0">{formatINR(line.line_amount)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {records.documents.length > 0 && (
        <section>
          <h3 className="text-[12px] font-semibold">Documents</h3>
          <ul className="mt-1 space-y-1">
            {records.documents.map((doc) => (
              <li key={doc.id} className="truncate text-[12px]">
                {doc.file_name} <span className="num text-muted-foreground">({doc.claim_id})</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function GroupSummary({ group }: { group: GroupOut }) {
  return (
    <div className="rounded-md border bg-muted/40 px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="num text-[12px] font-semibold">{group.group_id}</span>
        {group.tags.map((tag) => (
          <Badge key={tag} variant={tag === "WEAK_PATTERN" ? "outline" : "destructive"}>
            {tagLabel(tag)}
          </Badge>
        ))}
        <span className="num ml-auto text-[12px] text-muted-foreground">
          {group.claim_ids.length} claims · {group.policy_count} {group.policy_count === 1 ? "policy" : "policies"} ·{" "}
          {formatINR(group.total_requested)}
        </span>
      </div>
      <p className="mt-1 text-[13px] text-pretty">{group.summary}</p>
    </div>
  );
}

function GraphCanvas({ related }: { related: RelatedOut }) {
  const { resolvedTheme } = useTheme();
  const layout = useMemo(() => layoutRelated(related), [related]);
  const [selection, setSelection] = useState<Selection>(null);
  return (
    <div className="grid lg:grid-cols-3">
      <div className="h-[520px] border-b lg:col-span-2 lg:border-r lg:border-b-0">
        <ReactFlow
          nodes={layout.nodes}
          edges={layout.edges}
          nodeTypes={NODE_TYPES}
          colorMode={resolvedTheme === "dark" ? "dark" : "light"}
          nodesConnectable={false}
          nodesDraggable
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.3}
          proOptions={{ hideAttribution: true }}
          onEdgeClick={(_, edge) => setSelection({ kind: "edge", edge })}
          onNodeClick={(_, node) => setSelection({ kind: "node", node })}
          onPaneClick={() => setSelection(null)}
          className="related-graph"
        >
          <Background gap={20} size={1} />
          <Controls showInteractive={false} position="bottom-left" />
        </ReactFlow>
      </div>
      <aside className="max-h-[520px] overflow-auto p-4" aria-live="polite">
        {selection?.kind === "edge" && <EdgeDetails edge={selection.edge} />}
        {selection?.kind === "node" && <NodeDetails node={selection.node} />}
        {selection === null && (
          <div className="space-y-2 text-[13px] text-muted-foreground">
            <p>Click a link between claims to see the fields and values that matched, or a node to list its records.</p>
            <ul className="space-y-1.5">
              <li className="flex items-center gap-2">
                <span className="h-0.5 w-6 bg-destructive" aria-hidden="true" /> Strong link
              </li>
              <li className="flex items-center gap-2">
                <span className="h-0 w-6 border-t-2 border-dashed border-warning" aria-hidden="true" /> Weak link
              </li>
              <li className="flex items-center gap-2">
                <span className="h-px w-6 bg-border" aria-hidden="true" /> Structural (claim to entity)
              </li>
            </ul>
            <p>Provider and policy nodes are hubs: shown, never used to relate claims.</p>
          </div>
        )}
      </aside>
    </div>
  );
}

/**
 * A claim's related-claim groups and its subgraph. Takes the claim ID (and optionally the related data, when a
 * parent already has it); no routing or auth logic, so any page can embed it.
 */
export function RelatedClaimsGraph({ claimId, related }: { claimId: string; related?: RelatedOut }) {
  const query = useRelated(claimId);
  const data = related ?? query.data;
  return (
    <Panel>
      <PanelHeader
        title="Related claims"
        description="Claims connected to this one through shared invoices, incidents, documents or other matching records."
      />
      {!data && query.isPending && <Skeleton className="m-4 h-[420px]" />}
      {!data && query.isError && <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />}
      {data && (
        <ReactFlowProvider>
          {data.groups.length > 0 ? (
            <div className="space-y-2 border-b p-4">
              {data.groups.map((group) => (
                <GroupSummary key={group.group_id} group={group} />
              ))}
            </div>
          ) : (
            <div className="border-b px-4 py-3 text-[13px] text-muted-foreground">
              This claim is not in any related-claim group. Its own entities are shown below.
            </div>
          )}
          {data.nodes.length > 0 ? (
            <GraphCanvas related={data} />
          ) : (
            <EmptyState
              icon={Network}
              title="No graph yet"
              description="Run validation to build the correlation graph."
            />
          )}
        </ReactFlowProvider>
      )}
    </Panel>
  );
}
