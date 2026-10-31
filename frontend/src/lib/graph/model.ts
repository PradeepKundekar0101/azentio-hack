/**
 * Pure helpers for the related-claims graph: a layered layout (connecting entities above the claims, hubs below),
 * link labels, and the evidence of a link as label/value rows.
 */
import type { Edge, Node } from "@xyflow/react";

import type { Schemas } from "@/lib/api/client";

import { formatINR } from "../format";

export type RelatedOut = Schemas["RelatedOut"];
export type GraphNodeOut = Schemas["NodeOut"];
export type GraphEdgeOut = Schemas["EdgeOut"];
export type GroupOut = Schemas["GroupOut"];
export type GroupDetail = Schemas["GroupDetail"];
export type NodeRecords = Schemas["NodeRecords"];

export type EntityType = "claim" | "policy" | "claimant" | "provider" | "invoice" | "incident" | "document";

export interface GraphNodeData extends Record<string, unknown> {
  node: GraphNodeOut;
  focus: boolean;
  expanded: boolean;
}

export interface GraphEdgeData extends Record<string, unknown> {
  edge: GraphEdgeOut;
  strength: "structural" | "strong" | "weak";
  /** Every link between the two claims of a claim-to-claim edge, strongest first (one entry for structural). */
  links: GraphEdgeOut[];
}

const LINK_LABELS: Record<string, string> = {
  shared_invoice: "Same invoice",
  shared_incident: "Same incident",
  shared_document: "Same document",
  duplicate_match: "Duplicate",
  overlapping_stays: "Overlapping stays",
  same_claimant_provider: "Same claimant and provider",
  same_policy_provider: "Same policy and provider",
  similar_amount: "Similar amount",
};

export const ENTITY_LABELS: Record<EntityType, string> = {
  claim: "Claim",
  policy: "Policy",
  claimant: "Claimant",
  provider: "Provider",
  invoice: "Invoice",
  incident: "Incident",
  document: "Document",
};

export function linkLabel(edgeType: string): string {
  return LINK_LABELS[edgeType] ?? edgeType.replaceAll("_", " ");
}

const STRENGTH_RANK: Record<string, number> = { strong: 0, weak: 1, structural: 2 };
const TOP: EntityType[] = ["invoice", "incident", "document", "claimant"];
const BOTTOM: EntityType[] = ["provider", "policy"];
const ROW_Y = { top: 0, claims: 200, bottom: 400 };
const CLAIM_GAP = 440;
const ENTITY_GAP = 200;

function row(ids: string[], gap: number, y: number, width: number): Map<string, { x: number; y: number }> {
  const span = (ids.length - 1) * gap;
  const start = (width - span) / 2;
  return new Map(ids.map((id, i) => [id, { x: start + i * gap, y }]));
}

/**
 * Claims left to right, grown outward from the focus claim along its links: each newly reached claim goes next to
 * the end claim it was reached from, so a chain of links joins neighbouring cards. Unlinked claims go last.
 */
export function orderClaims(claimIds: string[], links: GraphEdgeOut[], focus: string): string[] {
  const neighbours = new Map<string, string[]>(claimIds.map((id) => [id, []]));
  for (const link of links) {
    neighbours.get(link.from_node)?.push(link.to_node);
    neighbours.get(link.to_node)?.push(link.from_node);
  }
  for (const list of neighbours.values()) list.sort();
  const start = neighbours.has(focus) ? focus : [...claimIds].sort()[0];
  if (start === undefined) return [];
  const order = [start];
  const queue = [start];
  const seen = new Set(order);
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of neighbours.get(current) ?? []) {
      if (seen.has(next)) continue;
      seen.add(next);
      queue.push(next);
      const atLeft = order[0] === current;
      const atRight = order[order.length - 1] === current;
      // The focus claim fills its right side first; any other claim extends the end it sits at.
      if (atRight && (!atLeft || order.length === 1 || order[0] !== start)) order.push(next);
      else if (atLeft) order.unshift(next);
      else order.splice(order.indexOf(current) + 1, 0, next);
    }
  }
  return [...order, ...claimIds.filter((id) => !seen.has(id)).sort()];
}

/** React Flow nodes and edges for a claim's subgraph. */
export function layoutRelated(related: RelatedOut): { nodes: Node<GraphNodeData>[]; edges: Edge<GraphEdgeData>[] } {
  const focus = `claim:${related.claim_id}`;
  const byType = (types: EntityType[]) =>
    related.nodes
      .filter((n) => types.includes(n.node_type as EntityType))
      .sort((a, b) => types.indexOf(a.node_type as EntityType) - types.indexOf(b.node_type as EntityType) || a.node_id.localeCompare(b.node_id))
      .map((n) => n.node_id);
  const claims = orderClaims(
    related.nodes.filter((n) => n.node_type === "claim").map((n) => n.node_id),
    related.edges.filter((e) => e.strength !== "structural"),
    focus,
  );
  const top = byType(TOP);
  const bottom = byType(BOTTOM);
  const width = Math.max(claims.length * CLAIM_GAP, top.length * ENTITY_GAP, bottom.length * ENTITY_GAP);
  const positions = new Map([
    ...row(top, ENTITY_GAP, ROW_Y.top, width),
    ...row(claims, CLAIM_GAP, ROW_Y.claims, width),
    ...row(bottom, ENTITY_GAP, ROW_Y.bottom, width),
  ]);
  const nodes: Node<GraphNodeData>[] = related.nodes.map((node) => ({
    id: node.node_id,
    type: node.node_type === "claim" ? "claim" : "entity",
    position: positions.get(node.node_id) ?? { x: 0, y: 0 },
    data: { node, focus: node.node_id === focus, expanded: node.expanded ?? true },
  }));
  const edges: Edge<GraphEdgeData>[] = [];
  const pairs = new Map<string, GraphEdgeOut[]>();
  for (const edge of related.edges) {
    if (edge.strength === "structural") {
      edges.push({
        id: String(edge.edge_id),
        source: edge.from_node,
        target: edge.to_node,
        className: "edge-structural",
        data: { edge, strength: "structural", links: [edge] },
      });
      continue;
    }
    const key = [edge.from_node, edge.to_node].sort().join("|");
    pairs.set(key, [...(pairs.get(key) ?? []), edge]);
  }
  // One edge per claim pair, drawn side to side from the left claim to the right one.
  for (const [key, links] of pairs) {
    links.sort((a, b) => STRENGTH_RANK[a.strength] - STRENGTH_RANK[b.strength] || a.edge_type.localeCompare(b.edge_type));
    const [a, b] = key.split("|");
    const [left, right] = (positions.get(a)?.x ?? 0) <= (positions.get(b)?.x ?? 0) ? [a, b] : [b, a];
    const strength = links[0].strength as GraphEdgeData["strength"];
    edges.push({
      id: `link:${key}`,
      source: left,
      sourceHandle: "right",
      target: right,
      targetHandle: "left",
      label: links.map((link) => linkLabel(link.edge_type)).join(" · "),
      className: `edge-${strength}`,
      zIndex: 1,
      data: { edge: links[0], strength, links },
    });
  }
  return { nodes, edges };
}

type Values = Record<string, unknown>;

function perClaim(value: unknown, format: (v: unknown) => string = String): string {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Values)
      .map(([claim, v]) => `${claim}: ${format(v)}`)
      .join(" · ");
  }
  return format(value);
}

function sumAmounts(value: unknown): string {
  const items = Array.isArray(value) ? value : [value];
  const paise = items.reduce<bigint>((total, v) => total + BigInt(Math.round(Number(v) * 100)), BigInt(0));
  return formatINR((Number(paise) / 100).toFixed(2));
}

function provider(values: Values): string {
  return values.provider_name ? `${values.provider_name} (${values.provider_id})` : String(values.provider_id);
}

/** One line naming what connects two claims, e.g. "Same invoice INV452 from Apollo Chennai (PRV-0012)". */
export function edgeHeadline(edge: GraphEdgeOut): string {
  const values = (edge.evidence?.values ?? {}) as Values;
  const first = (v: unknown) => (v && typeof v === "object" ? String(Object.values(v as Values)[0]) : String(v));
  switch (edge.edge_type) {
    case "shared_invoice":
      return `Same invoice ${first(values.invoice_reference)} from ${provider(values)}`;
    case "shared_incident":
      return `Same incident ${first(values.incident_reference)}`;
    case "shared_document":
      return values.hash_distance === 0 ? "Same document file" : `Near-identical document (distance ${values.hash_distance})`;
    case "overlapping_stays":
      return `Same claimant ${values.claimant_id} in two hospitals at once`;
    case "duplicate_match":
      return values.match_type === "exact_claim" ? "Exact duplicate claim" : "Near-duplicate claim";
    default:
      return linkLabel(edge.edge_type);
  }
}

const FIELD_LABELS: Record<string, string> = {
  provider_id: "Provider",
  invoice_reference: "Invoice number",
  incident_reference: "Incident reference",
  sha256: "File hash (SHA-256)",
  phash: "Image hash",
  match_type: "Match type",
  score: "Score",
  claimant_id: "Claimant",
  periods: "Service periods",
  policy_number: "Policy",
  service_dates: "Service dates",
  requested_amount: "Requested amounts",
};

/** The matched fields of a link, then its supporting values, as label/value rows. */
export function describeEvidence(edge: GraphEdgeOut): { label: string; value: string }[] {
  const fields = (edge.evidence?.fields ?? []) as string[];
  const values = (edge.evidence?.values ?? {}) as Values;
  const rows = fields.map((field) => {
    const value = values[field];
    let text: string;
    if (field === "provider_id") text = provider(values);
    else if (field === "periods") text = perClaim(value, (v) => (Array.isArray(v) ? v.join(" to ") : String(v)));
    else if (field === "requested_amount") text = perClaim(value, (v) => formatINR(String(v)));
    else if (field === "sha256" || field === "phash") text = perClaim(value, (v) => String(v).slice(0, 12) + "…");
    else text = perClaim(value);
    return { label: FIELD_LABELS[field] ?? field.replaceAll("_", " "), value: text };
  });
  if (values.line_amounts) rows.push({ label: "Line amounts", value: perClaim(values.line_amounts, sumAmounts) });
  if (values.hash_distance !== undefined && !fields.includes("hash_distance"))
    rows.push({ label: "Hash distance", value: String(values.hash_distance) });
  if (values.gap_days !== undefined) rows.push({ label: "Days apart", value: String(values.gap_days) });
  if (values.file_names) rows.push({ label: "Files", value: perClaim(values.file_names) });
  return rows;
}
