"use client";

// Human-readable summary of the completed spec JSON, shown on the confirmation
// screen before PRD generation. Renders all 9 sections as labeled cards.

type MvpFeature = { name: string; priority: "P0" | "P1" | "P2" };
type KnownRisk = { risk: string; impact: "High" | "Medium" | "Low"; mitigation: string };

export interface SpecSummaryProps {
  spec: Record<string, unknown>;
}

const PRIORITY_LABEL: Record<string, string> = {
  P0: "Must-have",
  P1: "Should-have",
  P2: "Nice-to-have",
};

const PRIORITY_COLOR: Record<string, string> = {
  P0: "bg-red-100 text-red-700",
  P1: "bg-yellow-100 text-yellow-700",
  P2: "bg-slate-100 text-slate-600",
};

const IMPACT_COLOR: Record<string, string> = {
  High: "bg-red-100 text-red-700",
  Medium: "bg-yellow-100 text-yellow-700",
  Low: "bg-green-100 text-green-700",
};

function isNotSpecified(v: unknown): boolean {
  return (
    v === null ||
    v === undefined ||
    v === "" ||
    v === "unspecified" ||
    (Array.isArray(v) && v.length === 0) ||
    (Array.isArray(v) && v.length === 1 && v[0] === "unspecified")
  );
}

function NotSpecified() {
  return <span className="text-sm italic text-slate-400">Not specified</span>;
}

function StringField({ value }: { value: unknown }) {
  if (isNotSpecified(value)) return <NotSpecified />;
  return <span className="text-sm text-slate-800">{String(value)}</span>;
}

function ListField({ value }: { value: unknown }) {
  if (!Array.isArray(value) || isNotSpecified(value)) return <NotSpecified />;
  return (
    <ul className="list-inside list-disc space-y-0.5">
      {value.map((item, i) => (
        <li key={i} className="text-sm text-slate-800">
          {String(item)}
        </li>
      ))}
    </ul>
  );
}

function MvpFeaturesField({ value }: { value: unknown }) {
  if (!Array.isArray(value) || isNotSpecified(value)) return <NotSpecified />;
  const features = value as MvpFeature[];
  const groups: Record<string, MvpFeature[]> = { P0: [], P1: [], P2: [] };
  for (const f of features) {
    if (f && typeof f === "object" && "priority" in f) {
      (groups[f.priority] ??= []).push(f);
    }
  }
  return (
    <div className="space-y-2">
      {(["P0", "P1", "P2"] as const).map((p) => {
        if (!groups[p]?.length) return null;
        return (
          <div key={p}>
            <span
              className={`rounded px-1.5 py-0.5 text-xs font-medium ${PRIORITY_COLOR[p]}`}
            >
              {PRIORITY_LABEL[p]}
            </span>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {groups[p].map((f, i) => (
                <li key={i} className="text-sm text-slate-800">
                  {f.name}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function KnownRisksField({ value }: { value: unknown }) {
  if (!Array.isArray(value) || isNotSpecified(value)) return <NotSpecified />;
  const risks = value as KnownRisk[];
  return (
    <div className="space-y-2">
      {risks.map((r, i) =>
        r && typeof r === "object" && "risk" in r ? (
          <div key={i} className="rounded-md border border-slate-200 p-3">
            <div className="flex items-start gap-2">
              <span
                className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${IMPACT_COLOR[r.impact] ?? "bg-slate-100 text-slate-600"}`}
              >
                {r.impact}
              </span>
              <span className="text-sm font-medium text-slate-800">{r.risk}</span>
            </div>
            {r.mitigation && r.mitigation !== "unspecified" && (
              <p className="mt-1 pl-10 text-sm text-slate-500">
                Mitigation: {r.mitigation}
              </p>
            )}
          </div>
        ) : null
      )}
    </div>
  );
}

type FieldKind = "string" | "list" | "mvp_features" | "known_risks";

interface FieldDef {
  key: string;
  label: string;
  kind?: FieldKind;
}

interface SectionDef {
  key: string;
  title: string;
  fields: FieldDef[];
}

const SECTIONS: SectionDef[] = [
  {
    key: "problem_and_vision",
    title: "Problem & Vision",
    fields: [
      { key: "one_liner", label: "One-liner" },
      { key: "problem_statement", label: "Problem statement" },
      { key: "business_goals", label: "Business goals" },
      { key: "motivation", label: "Motivation" },
      { key: "success_metrics", label: "Success metrics", kind: "list" },
    ],
  },
  {
    key: "users_and_use_cases",
    title: "Users & Use Cases",
    fields: [
      { key: "target_users", label: "Target users" },
      { key: "primary_use_cases", label: "Primary use cases", kind: "list" },
      { key: "user_personas", label: "User personas", kind: "list" },
    ],
  },
  {
    key: "scope_and_features",
    title: "Scope & Features",
    fields: [
      { key: "mvp_features", label: "MVP features", kind: "mvp_features" },
      { key: "future_features", label: "Future features", kind: "list" },
      { key: "explicitly_out_of_scope", label: "Out of scope", kind: "list" },
    ],
  },
  {
    key: "technical_requirements",
    title: "Technical Requirements",
    fields: [
      { key: "tech_stack_preference", label: "Tech stack" },
      { key: "integrations", label: "Integrations", kind: "list" },
      { key: "data_model", label: "Data model" },
      {
        key: "non_functional_requirements",
        label: "Non-functional requirements",
        kind: "list",
      },
      { key: "compliance_requirements", label: "Compliance", kind: "list" },
    ],
  },
  {
    key: "ux_design",
    title: "UX & Design",
    fields: [
      { key: "platform", label: "Platform" },
      { key: "design_preferences", label: "Design preferences" },
      { key: "accessibility_needs", label: "Accessibility" },
    ],
  },
  {
    key: "deployment_infra",
    title: "Deployment & Infrastructure",
    fields: [
      { key: "deployment_target", label: "Deployment target" },
      { key: "environments", label: "Environments" },
      { key: "cicd_needs", label: "CI/CD" },
    ],
  },
  {
    key: "timeline_resources",
    title: "Timeline & Resources",
    fields: [
      { key: "timeline", label: "Timeline" },
      { key: "budget", label: "Budget" },
      { key: "team_size_roles", label: "Team" },
    ],
  },
  {
    key: "maintenance_ops",
    title: "Maintenance & Operations",
    fields: [
      { key: "maintenance_plan", label: "Maintenance plan" },
      { key: "monitoring_logging", label: "Monitoring & logging" },
      { key: "support_plan", label: "Support plan" },
    ],
  },
  {
    key: "risks_assumptions",
    title: "Risks & Assumptions",
    fields: [
      { key: "known_risks", label: "Known risks", kind: "known_risks" },
      { key: "assumptions", label: "Assumptions", kind: "list" },
      { key: "dependencies", label: "Dependencies", kind: "list" },
    ],
  },
];

function FieldValue({ value, kind }: { value: unknown; kind?: FieldKind }) {
  if (kind === "mvp_features") return <MvpFeaturesField value={value} />;
  if (kind === "known_risks") return <KnownRisksField value={value} />;
  if (kind === "list") return <ListField value={value} />;
  return <StringField value={value} />;
}

export default function SpecSummary({ spec }: SpecSummaryProps) {
  return (
    <div className="space-y-6">
      {SECTIONS.map((section) => {
        const sectionData = spec[section.key] as Record<string, unknown> | undefined;
        if (!sectionData) return null;
        return (
          <div key={section.key}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              {section.title}
            </h3>
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {section.fields.map((field) => (
                <div
                  key={field.key}
                  className="grid grid-cols-[9rem_1fr] gap-4 px-4 py-3"
                >
                  <span className="pt-0.5 text-sm font-medium text-slate-500">
                    {field.label}
                  </span>
                  <FieldValue value={sectionData[field.key]} kind={field.kind} />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
