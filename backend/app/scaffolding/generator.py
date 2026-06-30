"""Project scaffold generator.

Copies the matched template tree into a timestamped output directory,
overwrites README.md with spec-derived content, and writes one stub file
per P0 feature.

Nothing is installed or executed — output is files only.
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from .matcher import MatchResult

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Default output root: backend/generated/  — override with SCAFFOLD_OUTPUT_DIR.
_DEFAULT_OUTPUT_ROOT = Path(__file__).parent.parent.parent / "generated"


def _output_root() -> Path:
    env = os.getenv("SCAFFOLD_OUTPUT_DIR", "").strip()
    return Path(env) if env else _DEFAULT_OUTPUT_ROOT


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:48]


def _to_pascal(name: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[\s\-_]+", name) if w)


def _to_snake(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.strip().lower())


def _p0_features(spec: dict) -> list[dict]:
    features = spec.get("scope_and_features", {}).get("mvp_features", [])
    if not isinstance(features, list):
        return []
    return [
        f for f in features
        if isinstance(f, dict) and f.get("priority") == "P0"
    ]


# ── README content ────────────────────────────────────────────────────────────

def _mvp_table(features: list) -> str:
    if not features or features == ["unspecified"]:
        return "\n_No MVP features specified._\n"

    buckets: dict[str, list[str]] = {"P0": [], "P1": [], "P2": []}
    for f in features:
        if isinstance(f, dict):
            tier = f.get("priority", "P1")
            buckets.get(tier, buckets["P1"]).append(f.get("name", "?"))

    labels = {
        "P0": "Must-have (P0)",
        "P1": "Should-have (P1)",
        "P2": "Could-have (P2)",
    }
    lines: list[str] = []
    for tier, label in labels.items():
        if buckets[tier]:
            lines.append(f"\n**{label}**")
            for n in buckets[tier]:
                lines.append(f"- {n}")
    return "\n".join(lines) if lines else "\n_No MVP features specified._\n"


def _build_readme(spec: dict, match: MatchResult) -> str:
    pv = spec.get("problem_and_vision", {})
    one_liner = pv.get("one_liner") or "Untitled project"
    if one_liner == "unspecified":
        one_liner = "Untitled project"
    problem = pv.get("problem_statement") or "_Not specified._"
    if problem == "unspecified":
        problem = "_Not specified._"
    features = spec.get("scope_and_features", {}).get("mvp_features", [])

    note_block = f"\n> **Scaffold note:** {match.note}\n" if match.note else ""

    return (
        f"# {one_liner}\n"
        f"{note_block}\n"
        f"## Problem\n\n"
        f"{problem}\n\n"
        f"## MVP Features\n"
        f"{_mvp_table(features)}\n\n"
        f"## Getting Started\n\n"
        f"See the sub-directories for setup instructions specific to each part of the stack.\n"
        f"No dependencies have been installed — run the appropriate package manager command\n"
        f"inside each directory before starting.\n"
    )


# ── Feature stub generators ───────────────────────────────────────────────────

def _tsx_stub(feature_name: str) -> str:
    pascal = _to_pascal(feature_name)
    return (
        f"// TODO: {feature_name}\n"
        f"// Implement the {feature_name} UI here.\n\n"
        f"export default function {pascal}Page() {{\n"
        f"  return (\n"
        f"    <main>\n"
        f"      <h1>{feature_name}</h1>\n"
        f"      <p>TODO: implement this page.</p>\n"
        f"    </main>\n"
        f"  );\n"
        f"}}\n"
    )


def _py_route_stub(feature_name: str, slug: str) -> str:
    snake = _to_snake(feature_name)
    return (
        f"# TODO: {feature_name}\n"
        f"# Implement the {feature_name} backend route here.\n\n"
        f"from fastapi import APIRouter\n\n"
        f"router = APIRouter()\n\n\n"
        f"@router.get('/{slug}')\n"
        f"def get_{snake}():\n"
        f"    # TODO: implement\n"
        f"    return {{'message': 'TODO: {feature_name}'}}\n"
    )


def _js_route_stub(feature_name: str, slug: str) -> str:
    return (
        f"// TODO: {feature_name}\n"
        f"// Implement the {feature_name} backend route here.\n\n"
        f"import express from 'express';\n"
        f"const router = express.Router();\n\n"
        f"router.get('/{slug}', (_req, res) => {{\n"
        f"  // TODO: implement\n"
        f"  res.json({{ message: 'TODO: {feature_name}' }});\n"
        f"}});\n\n"
        f"export default router;\n"
    )


def _generic_py_stub(feature_name: str) -> str:
    snake = _to_snake(feature_name)
    return (
        f"# TODO: {feature_name}\n"
        f"# Implement {feature_name} here.\n\n\n"
        f"def {snake}():\n"
        f"    # TODO: implement\n"
        f"    raise NotImplementedError('{feature_name}')\n"
    )


def _stubs_for(template: str, feature_name: str, slug: str, out: Path) -> list[tuple[Path, str]]:
    if template == "nextjs-fastapi":
        return [
            (out / "frontend" / "app" / slug / "page.tsx", _tsx_stub(feature_name)),
            (out / "backend" / "app" / "routes" / f"{slug}.py", _py_route_stub(feature_name, slug)),
        ]
    if template == "nextjs-node":
        return [
            (out / "frontend" / "app" / slug / "page.tsx", _tsx_stub(feature_name)),
            (out / "backend" / "src" / "routes" / f"{slug}.js", _js_route_stub(feature_name, slug)),
        ]
    # generic
    return [
        (out / "src" / f"{slug}.py", _generic_py_stub(feature_name)),
    ]


# ── Copy hook: rename gitignore → .gitignore, env.example → .env.example ────

def _copy_with_renames(src: Path, dst: Path) -> None:
    """Recursively copy src → dst, renaming dotfile stubs on the way."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target_name = item.name
        if target_name == "gitignore":
            target_name = ".gitignore"
        elif target_name == "env.example":
            target_name = ".env.example"
        target = dst / target_name
        if item.is_dir():
            _copy_with_renames(item, target)
        else:
            shutil.copy2(item, target)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_scaffold(spec: dict, match: MatchResult) -> dict:
    """Copy template, write README, write P0 stubs. Returns result metadata."""
    template_src = _TEMPLATES_DIR / match.template

    # Build output directory name from one_liner slug + timestamp.
    one_liner = (
        spec.get("problem_and_vision", {}).get("one_liner") or ""
    ).strip()
    if not one_liner or one_liner == "unspecified":
        one_liner = "project"
    slug = _slugify(one_liner)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = _output_root() / f"{slug}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy template tree (with dotfile renaming).
    _copy_with_renames(template_src, out_dir)

    # 2. Enumerate copied files.
    files_created: list[str] = []
    for root, _, files in os.walk(out_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), out_dir)
            files_created.append(rel.replace(os.sep, "/"))

    # 3. Overwrite README.md with spec-derived content.
    readme_path = out_dir / "README.md"
    readme_path.write_text(_build_readme(spec, match), encoding="utf-8")
    if "README.md" not in files_created:
        files_created.append("README.md")

    # 4. Write one stub per P0 feature.
    for feature in _p0_features(spec):
        name = feature.get("name", "unnamed-feature")
        feature_slug = _slugify(name)
        for path, content in _stubs_for(match.template, name, feature_slug, out_dir):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            rel = str(path.relative_to(out_dir)).replace(os.sep, "/")
            if rel not in files_created:
                files_created.append(rel)

    return {
        "output_path": str(out_dir),
        "template": match.template,
        "match_exact": match.exact,
        "match_note": match.note,
        "files_created": sorted(files_created),
    }
