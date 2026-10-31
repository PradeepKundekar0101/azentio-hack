"use client";

import { useRouter } from "next/navigation";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  AXIS_PROPS,
  BAR_RADIUS_H,
  BarList,
  BAR_RADIUS_V,
  ChartEmpty,
  ChartTable,
  ChartTooltip,
  CURSOR_FILL,
  LegendKey,
  useElementWidth,
} from "@/components/review/charts";
import { type AlertFilters, filtersToSearch } from "@/lib/alerts/filters";
import {
  type AlertCategory,
  categoryLabel,
  categoryRank,
  type DashboardSummary,
  SEVERITIES,
  type Severity,
  severityLabel,
} from "@/lib/alerts/model";
import { formatINR, formatINRCompact, formatNumber } from "@/lib/format";

const CALCULATED_COLOR = "var(--chart-1)";
const ESTIMATED_COLOR = "var(--chart-2)";
const NO_AMOUNT_COLOR = "var(--chart-5)";

const ROW_HEIGHT = 34;
/** Below this width the horizontal charts become labelled bar lists. */
const NARROW = 520;

function plural(n: number, word: string) {
  return `${formatNumber(n)} ${n === 1 ? word : `${word}s`}`;
}

/** Opens the alerts list with the dashboard's filters plus one more. */
function useDrillDown(filters: AlertFilters) {
  const router = useRouter();
  return (patch: Partial<AlertFilters>) => router.push(`/alerts${filtersToSearch({ ...filters, ...patch })}`);
}

interface CategoryDatum {
  category: string;
  label: string;
  alerts: number;
  calculated: string;
  estimated: string;
  /** Bar length: the category's calculated amount, or its estimated amount. Never their sum. */
  value: number;
  kind: "calculated" | "estimated" | "none";
}

function categoryData(rows: DashboardSummary["by_category"]): CategoryDatum[] {
  return [...rows]
    .sort((a, b) => categoryRank(a.category) - categoryRank(b.category))
    .map((row) => {
      const calculated = Number(row.calculated_amount);
      const estimated = Number(row.estimated_amount);
      const kind = calculated > 0 ? "calculated" : estimated > 0 ? "estimated" : "none";
      return {
        category: row.category,
        label: categoryLabel(row.category),
        alerts: row.alerts,
        calculated: row.calculated_amount,
        estimated: row.estimated_amount,
        value: kind === "calculated" ? calculated : kind === "estimated" ? estimated : 0,
        kind,
      };
    });
}

function CategoryTick({
  x,
  y,
  payload,
  data,
}: {
  x?: number | string;
  y?: number | string;
  payload?: { value: string };
  data: CategoryDatum[];
}) {
  const datum = data.find((d) => d.category === payload?.value);
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={11}>
      <tspan fill="var(--foreground)">{datum?.label ?? payload?.value}</tspan>
      <tspan fill="var(--chart-axis)" dx={5}>
        {datum ? formatNumber(datum.alerts) : ""}
      </tspan>
    </text>
  );
}

/** Alerts and amount by category. Calculated and estimated amounts get their own colour. */
export function CategoryChart({ summary, filters }: { summary: DashboardSummary; filters: AlertFilters }) {
  const data = categoryData(summary.by_category);
  const drill = useDrillDown(filters);
  const [ref, width] = useElementWidth<HTMLDivElement>();
  if (data.length === 0) return <ChartEmpty>No alerts match these filters.</ChartEmpty>;
  const hasEstimated = data.some((d) => d.kind === "estimated");
  const hasNone = data.some((d) => d.kind === "none");
  const narrow = width !== null && width < NARROW;

  return (
    <div ref={ref}>
      <LegendKey
        className="mb-2"
        items={[
          { label: "Calculated amount", color: CALCULATED_COLOR },
          ...(hasEstimated ? [{ label: "Estimated amount", color: ESTIMATED_COLOR }] : []),
          ...(hasNone ? [{ label: "Suspected, no amount", color: NO_AMOUNT_COLOR }] : []),
        ]}
      />
      {narrow ? (
        <BarList
          label="Alerts and amount by category"
          items={data.map((d) => ({
            key: d.category,
            label: d.label,
            detail: plural(d.alerts, "alert"),
            value: d.value,
            display: d.value > 0 ? formatINRCompact(d.value) : "No amount",
            color: d.kind === "estimated" ? ESTIMATED_COLOR : d.kind === "none" ? NO_AMOUNT_COLOR : CALCULATED_COLOR,
            onSelect: () => drill({ category: [d.category as AlertCategory] }),
          }))}
        />
      ) : (
        <div style={{ height: data.length * ROW_HEIGHT + 28 }} aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 0, right: 64, bottom: 0, left: 4 }}
              barCategoryGap={8}
            >
              <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
              <XAxis type="number" {...AXIS_PROPS} tickFormatter={(v: number) => formatINRCompact(v)} />
              <YAxis
                type="category"
                dataKey="category"
                {...AXIS_PROPS}
                axisLine={false}
                width={168}
                interval={0}
                tick={(props) => <CategoryTick {...props} data={data} />}
              />
              <Tooltip
                cursor={CURSOR_FILL}
                content={(props) => (
                  <ChartTooltip
                    {...props}
                    title={(d) => String(d.label)}
                    rows={(d) => [
                      {
                        label: "Alerts",
                        value: formatNumber(d.alerts as number),
                      },
                      {
                        label: "Calculated",
                        value: formatINR(d.calculated as string),
                        color: CALCULATED_COLOR,
                      },
                      {
                        label: "Estimated",
                        value: formatINR(d.estimated as string),
                        color: ESTIMATED_COLOR,
                      },
                    ]}
                  />
                )}
              />
              <Bar
                isAnimationActive={false}
                dataKey="value"
                radius={BAR_RADIUS_H}
                minPointSize={3}
                className="cursor-pointer"
                onClick={(entry) =>
                  drill({
                    category: [(entry as unknown as CategoryDatum).category as AlertCategory],
                  })
                }
              >
                {data.map((d) => (
                  <Cell
                    key={d.category}
                    fill={
                      d.kind === "estimated" ? ESTIMATED_COLOR : d.kind === "none" ? NO_AMOUNT_COLOR : CALCULATED_COLOR
                    }
                  />
                ))}
                <LabelList
                  dataKey="value"
                  position="right"
                  fontSize={11}
                  fill="var(--foreground)"
                  formatter={(v: unknown) => (Number(v) > 0 ? formatINRCompact(Number(v)) : "–")}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <ChartTable
        caption="Alerts and amount by category"
        columns={["Category", "Alerts", "Calculated", "Estimated"]}
        rows={data.map((d) => [d.label, formatNumber(d.alerts), formatINR(d.calculated), formatINR(d.estimated)])}
      />
    </div>
  );
}

/** Alerts by severity, most severe first; severities with no alerts show as zero. */
export function SeverityChart({ summary, filters }: { summary: DashboardSummary; filters: AlertFilters }) {
  const counts = new Map(summary.by_severity.map((r) => [r.severity, r.alerts]));
  const data = SEVERITIES.map((s) => ({
    severity: s,
    label: severityLabel(s),
    alerts: counts.get(s) ?? 0,
  }));
  const drill = useDrillDown(filters);
  if (data.every((d) => d.alerts === 0)) return <ChartEmpty>No alerts match these filters.</ChartEmpty>;

  return (
    <div>
      <div className="h-56" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 18, right: 4, bottom: 0, left: -20 }} barCategoryGap="28%">
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis dataKey="label" {...AXIS_PROPS} interval={0} />
            <YAxis {...AXIS_PROPS} axisLine={false} allowDecimals={false} />
            <Tooltip
              cursor={CURSOR_FILL}
              content={(props) => (
                <ChartTooltip
                  {...props}
                  title={(d) => String(d.label)}
                  rows={(d) => [
                    {
                      label: "Alerts",
                      value: formatNumber(d.alerts as number),
                    },
                  ]}
                />
              )}
            />
            <Bar
              isAnimationActive={false}
              dataKey="alerts"
              fill="var(--chart-1)"
              radius={BAR_RADIUS_V}
              className="cursor-pointer"
              onClick={(entry) =>
                drill({
                  severity: [(entry as unknown as { severity: Severity }).severity],
                })
              }
            >
              <LabelList
                dataKey="alerts"
                position="top"
                fontSize={11}
                fill="var(--foreground)"
                formatter={(v: unknown) => formatNumber(Number(v))}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable
        caption="Alerts by severity"
        columns={["Severity", "Alerts"]}
        rows={data.map((d) => [d.label, formatNumber(d.alerts)])}
      />
    </div>
  );
}

function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** One line per provider; long names are shortened and shown in full in the tooltip. */
function ProviderTick({ x, y, payload }: { x?: number | string; y?: number | string; payload?: { value: string } }) {
  const name = payload?.value ?? "";
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={11} fill="var(--foreground)">
      <title>{name}</title>
      {truncate(name, 26)}
    </text>
  );
}

/** Calculated leakage by provider, top 10. */
export function ProviderChart({ summary, filters }: { summary: DashboardSummary; filters: AlertFilters }) {
  const data = summary.top_providers
    .filter((p) => Number(p.calculated_amount) > 0)
    .slice(0, 10)
    .map((p) => ({ ...p, value: Number(p.calculated_amount) }));
  const drill = useDrillDown(filters);
  const [ref, width] = useElementWidth<HTMLDivElement>();
  if (data.length === 0) return <ChartEmpty>No calculated leakage matches these filters.</ChartEmpty>;
  const narrow = width !== null && width < NARROW;

  return (
    <div ref={ref}>
      {narrow ? (
        <BarList
          label="Calculated leakage by provider"
          items={data.map((p) => ({
            key: p.provider_id,
            label: p.provider_name,
            detail: plural(p.alerts, "alert"),
            value: p.value,
            display: formatINRCompact(p.calculated_amount),
            color: CALCULATED_COLOR,
            onSelect: () => drill({ provider_id: [p.provider_id] }),
          }))}
        />
      ) : (
        <div style={{ height: data.length * ROW_HEIGHT + 28 }} aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 0, right: 64, bottom: 0, left: 4 }}
              barCategoryGap={8}
            >
              <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
              <XAxis type="number" {...AXIS_PROPS} tickFormatter={(v: number) => formatINRCompact(v)} />
              <YAxis
                type="category"
                dataKey="provider_name"
                {...AXIS_PROPS}
                axisLine={false}
                width={168}
                interval={0}
                tick={(props) => <ProviderTick {...props} />}
              />
              <Tooltip
                cursor={CURSOR_FILL}
                content={(props) => (
                  <ChartTooltip
                    {...props}
                    title={(d) => String(d.provider_name)}
                    rows={(d) => [
                      {
                        label: "Calculated",
                        value: formatINR(d.calculated_amount as string),
                        color: CALCULATED_COLOR,
                      },
                      {
                        label: "Alerts",
                        value: formatNumber(d.alerts as number),
                      },
                    ]}
                  />
                )}
              />
              <Bar
                isAnimationActive={false}
                dataKey="value"
                fill={CALCULATED_COLOR}
                radius={BAR_RADIUS_H}
                className="cursor-pointer"
                onClick={(entry) =>
                  drill({
                    provider_id: [(entry as unknown as { provider_id: string }).provider_id],
                  })
                }
              >
                <LabelList
                  dataKey="value"
                  position="right"
                  fontSize={11}
                  fill="var(--foreground)"
                  formatter={(v: unknown) => formatINRCompact(Number(v))}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <ChartTable
        caption="Calculated leakage by provider, top 10"
        columns={["Provider", "Calculated leakage", "Alerts"]}
        rows={data.map((p) => [p.provider_name, formatINR(p.calculated_amount), plural(p.alerts, "alert")])}
      />
    </div>
  );
}
