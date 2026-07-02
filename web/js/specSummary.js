// Plain-DOM port of frontend/app/components/SpecSummary.tsx — same section/
// field layout and priority/impact grouping, rendered as elements instead of
// React nodes.

const PRIORITY_LABEL = { P0: "Must-have", P1: "Should-have", P2: "Nice-to-have" };
const PRIORITY_CLASS = { P0: "tag-red", P1: "tag-yellow", P2: "tag-slate" };
const IMPACT_CLASS = { High: "tag-red", Medium: "tag-yellow", Low: "tag-green" };

const SECTIONS = [
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
      { key: "non_functional_requirements", label: "Non-functional requirements", kind: "list" },
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

function isNotSpecified(v) {
  return (
    v === null ||
    v === undefined ||
    v === "" ||
    v === "unspecified" ||
    (Array.isArray(v) && v.length === 0) ||
    (Array.isArray(v) && v.length === 1 && v[0] === "unspecified")
  );
}

function el(tag, className, children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const child of children ?? []) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function notSpecifiedEl() {
  return el("span", "not-specified", ["Not specified"]);
}

function stringFieldEl(value) {
  if (isNotSpecified(value)) return notSpecifiedEl();
  return el("span", "field-string", [String(value)]);
}

function listFieldEl(value) {
  if (!Array.isArray(value) || isNotSpecified(value)) return notSpecifiedEl();
  const ul = el("ul", "field-list");
  for (const item of value) ul.appendChild(el("li", null, [String(item)]));
  return ul;
}

function mvpFeaturesFieldEl(value) {
  if (!Array.isArray(value) || isNotSpecified(value)) return notSpecifiedEl();
  const groups = { P0: [], P1: [], P2: [] };
  for (const f of value) {
    if (f && typeof f === "object" && "priority" in f && groups[f.priority]) {
      groups[f.priority].push(f);
    }
  }
  const wrap = el("div", "mvp-groups");
  for (const p of ["P0", "P1", "P2"]) {
    if (!groups[p].length) continue;
    const group = el("div", "mvp-group", [
      el("span", `tag ${PRIORITY_CLASS[p]}`, [PRIORITY_LABEL[p]]),
      el(
        "ul",
        "field-list mt-1",
        groups[p].map((f) => el("li", null, [f.name]))
      ),
    ]);
    wrap.appendChild(group);
  }
  return wrap;
}

function knownRisksFieldEl(value) {
  if (!Array.isArray(value) || isNotSpecified(value)) return notSpecifiedEl();
  const wrap = el("div", "risk-list");
  for (const r of value) {
    if (!r || typeof r !== "object" || !("risk" in r)) continue;
    const impactClass = IMPACT_CLASS[r.impact] ?? "tag-slate";
    const card = el("div", "risk-card", [
      el("div", "risk-card-head", [
        el("span", `tag ${impactClass}`, [r.impact]),
        el("span", "risk-card-title", [r.risk]),
      ]),
    ]);
    if (r.mitigation && r.mitigation !== "unspecified") {
      card.appendChild(el("p", "risk-card-mitigation", [`Mitigation: ${r.mitigation}`]));
    }
    wrap.appendChild(card);
  }
  return wrap;
}

function fieldValueEl(value, kind) {
  if (kind === "mvp_features") return mvpFeaturesFieldEl(value);
  if (kind === "known_risks") return knownRisksFieldEl(value);
  if (kind === "list") return listFieldEl(value);
  return stringFieldEl(value);
}

export function renderSpecSummary(spec) {
  const root = el("div", "spec-summary");
  for (const section of SECTIONS) {
    const sectionData = spec[section.key];
    if (!sectionData) continue;
    const rows = el(
      "div",
      "spec-section-rows",
      section.fields.map((field) =>
        el("div", "spec-field-row", [
          el("span", "spec-field-label", [field.label]),
          fieldValueEl(sectionData[field.key], field.kind),
        ])
      )
    );
    root.appendChild(el("div", "spec-section", [el("h3", "spec-section-title", [section.title]), rows]));
  }
  return root;
}
