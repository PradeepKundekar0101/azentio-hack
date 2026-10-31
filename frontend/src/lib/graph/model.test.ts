import { describe, expect, it } from "vitest";

import { describeEvidence, edgeHeadline, layoutRelated, linkLabel, type RelatedOut } from "./model";

const related: RelatedOut = {
  claim_id: "CLM-1",
  build_id: 3,
  groups: [],
  nodes: [
    { node_id: "claim:CLM-1", node_type: "claim", node_key: "CLM-1", label: "CLM-1", attributes: { requested_amount: "48500.00" }, expanded: true },
    { node_id: "claim:CLM-2", node_type: "claim", node_key: "CLM-2", label: "CLM-2", attributes: { requested_amount: "48500.00" }, expanded: true },
    { node_id: "invoice:PRV-0012|INV452", node_type: "invoice", node_key: "PRV-0012|INV452", label: "INV452", attributes: {}, expanded: true },
    { node_id: "provider:PRV-0012", node_type: "provider", node_key: "PRV-0012", label: "Apollo Chennai", attributes: {}, expanded: false },
    { node_id: "policy:POL-1", node_type: "policy", node_key: "POL-1", label: "POL-1", attributes: {}, expanded: false },
  ],
  edges: [
    { edge_id: 1, from_node: "claim:CLM-1", to_node: "invoice:PRV-0012|INV452", edge_type: "billed_on", strength: "structural", evidence: null, score: null, generated_by: "rule" },
    { edge_id: 2, from_node: "claim:CLM-2", to_node: "invoice:PRV-0012|INV452", edge_type: "billed_on", strength: "structural", evidence: null, score: null, generated_by: "rule" },
    { edge_id: 3, from_node: "claim:CLM-1", to_node: "provider:PRV-0012", edge_type: "treated_at", strength: "structural", evidence: null, score: null, generated_by: "rule" },
    { edge_id: 4, from_node: "claim:CLM-1", to_node: "policy:POL-1", edge_type: "filed_under", strength: "structural", evidence: null, score: null, generated_by: "rule" },
    {
      edge_id: 5,
      from_node: "claim:CLM-1",
      to_node: "claim:CLM-2",
      edge_type: "shared_invoice",
      strength: "strong",
      evidence: {
        fields: ["provider_id", "invoice_reference"],
        values: {
          provider_id: "PRV-0012",
          provider_name: "Apollo Chennai",
          invoice_reference: { "CLM-1": "INV452", "CLM-2": "inv 452" },
          line_amounts: { "CLM-1": ["48500.00"], "CLM-2": ["48500.00"] },
        },
      },
      score: null,
      generated_by: "rule",
    },
  ],
};

describe("layoutRelated", () => {
  it("puts claims in the middle row, connecting entities above and hubs below", () => {
    const { nodes } = layoutRelated(related);
    const y = (id: string) => nodes.find((n) => n.id === id)!.position.y;
    expect(y("claim:CLM-1")).toBe(y("claim:CLM-2"));
    expect(y("invoice:PRV-0012|INV452")).toBeLessThan(y("claim:CLM-1"));
    expect(y("provider:PRV-0012")).toBeGreaterThan(y("claim:CLM-1"));
    expect(y("policy:POL-1")).toBe(y("provider:PRV-0012"));
  });

  it("keeps the focus claim first and spaces nodes in a row apart", () => {
    const { nodes } = layoutRelated(related);
    const claims = nodes.filter((n) => n.type === "claim").sort((a, b) => a.position.x - b.position.x);
    expect(claims.map((n) => n.id)).toEqual(["claim:CLM-1", "claim:CLM-2"]);
    expect(claims[1].position.x - claims[0].position.x).toBeGreaterThanOrEqual(200);
  });

  it("puts the focus claim between its linked neighbours, so every link joins adjacent cards", () => {
    const claimNode = (id: string) => ({ ...related.nodes[0], node_id: `claim:${id}`, node_key: id, label: id });
    const link = (id: number, a: string, b: string) => ({ ...related.edges[4], edge_id: id, from_node: `claim:${a}`, to_node: `claim:${b}` });
    const chain: RelatedOut = {
      ...related,
      claim_id: "CLM-B",
      nodes: [claimNode("CLM-A"), claimNode("CLM-B"), claimNode("CLM-C"), claimNode("CLM-D")],
      edges: [link(1, "CLM-A", "CLM-B"), link(2, "CLM-B", "CLM-C"), link(3, "CLM-C", "CLM-D")],
    };
    const { nodes } = layoutRelated(chain);
    const order = nodes.sort((a, b) => a.position.x - b.position.x).map((n) => n.id);
    for (const edge of chain.edges) {
      expect(Math.abs(order.indexOf(edge.from_node) - order.indexOf(edge.to_node))).toBe(1);
    }
  });

  it("draws one side-to-side edge per claim pair, carrying every link, strongest first", () => {
    const withWeak: RelatedOut = {
      ...related,
      edges: [
        ...related.edges,
        { ...related.edges[4], edge_id: 6, edge_type: "similar_amount", strength: "weak", evidence: { fields: [], values: {} } },
      ],
    };
    const { edges } = layoutRelated(withWeak);
    const links = edges.filter((e) => e.data?.strength !== "structural");
    expect(links).toHaveLength(1);
    const [link] = links;
    expect(link.label).toBe("Same invoice · Similar amount");
    expect(link.data?.strength).toBe("strong");
    expect(link.data?.links.map((l) => l.edge_type)).toEqual(["shared_invoice", "similar_amount"]);
    expect([link.source, link.sourceHandle, link.target, link.targetHandle]).toEqual([
      "claim:CLM-1",
      "right",
      "claim:CLM-2",
      "left",
    ]);
    expect(edges.find((e) => e.id === "1")!.label).toBeUndefined();
  });

  it("marks hub nodes as not expanded", () => {
    const { nodes } = layoutRelated(related);
    expect(nodes.find((n) => n.id === "provider:PRV-0012")!.data.expanded).toBe(false);
  });
});

describe("evidence", () => {
  const link = related.edges[4];

  it("names a shared invoice the way an analyst would say it", () => {
    expect(edgeHeadline(link)).toBe("Same invoice INV452 from Apollo Chennai (PRV-0012)");
  });

  it("lists every matched field with the value on each claim", () => {
    expect(describeEvidence(link)).toEqual([
      { label: "Provider", value: "Apollo Chennai (PRV-0012)" },
      { label: "Invoice number", value: "CLM-1: INV452 · CLM-2: inv 452" },
      { label: "Line amounts", value: "CLM-1: ₹48,500 · CLM-2: ₹48,500" },
    ]);
  });

  it("labels every link type", () => {
    expect(linkLabel("shared_incident")).toBe("Same incident");
    expect(linkLabel("overlapping_stays")).toBe("Overlapping stays");
    expect(linkLabel("similar_amount")).toBe("Similar amount");
    expect(linkLabel("unknown_type")).toBe("unknown type");
  });
});
