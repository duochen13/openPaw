#!/usr/bin/env python3
"""Regenerate the travel-assistant API docs from the live FastAPI app.

Single source of truth: ``travel_assistant.service``'s OpenAPI schema
(``app.openapi()``). The endpoint reference below is rendered from that
spec — never hand-edit ``api-reference.md`` or ``openapi.json``; edit the
route metadata in ``service.py`` and re-run this script.

Usage:
    cd travel-assistant && python3 docs/generate_api_docs.py [--check]

``--check`` exits non-zero (printing a unified diff) when the committed
docs are stale — for CI or the repo's push-time docs-sync hook.
"""

import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # travel-assistant/docs
PROJECT = HERE.parent                            # travel-assistant
sys.path.insert(0, str(PROJECT))

from travel_assistant.service import app  # noqa: E402


def _schema_type(schema):
    """Human-readable type label for a JSON-schema fragment."""
    if not isinstance(schema, dict):
        return ""
    t = schema.get("type", "")
    if t == "array":
        items = schema.get("items", {})
        return f"array of {_schema_type(items) or 'any'}"
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    enum = schema.get("enum")
    label = t or "any"
    if enum:
        label += f" ({' | '.join(str(e) for e in enum)})"
    return label


def _prop_rows(properties, required=()):
    rows = []
    for name, subschema in (properties or {}).items():
        req = "yes" if name in (required or ()) else "no"
        default = subschema.get("default", "")
        default = f"`{default}`" if default != "" else ""
        desc = (subschema.get("description") or "").replace("\n", " ")
        rows.append(
            f"| `{name}` | {_schema_type(subschema)} | {req} | {default} "
            f"| {desc} |"
        )
    return rows


def _param_table(parameters):
    if not parameters:
        return "_None._\n"
    lines = ["| Name | In | Type | Required | Default | Description |",
             "| --- | --- | --- | --- | --- | --- |"]
    for p in parameters:
        schema = p.get("schema", {})
        default = schema.get("default", "")
        default = f"`{default}`" if default != "" else ""
        desc = (p.get("description") or "").replace("\n", " ")
        lines.append(
            f"| `{p['name']}` | {p.get('in', '')} | "
            f"{_schema_type(schema)} | {'yes' if p.get('required') else 'no'} "
            f"| {default} | {desc} |"
        )
    return "\n".join(lines) + "\n"


def _body_section(request_body):
    if not request_body:
        return ""
    out = ["### Request body\n"]
    content = request_body.get("content", {})
    for media, media_obj in content.items():
        schema = media_obj.get("schema", {})
        out.append(f"Content type: `{media}`\n")
        props = schema.get("properties")
        if props:
            out.append("| Field | Type | Required | Default | Description |")
            out.append("| --- | --- | --- | --- | --- |")
            out.extend(_prop_rows(props, schema.get("required")))
            out.append("")
        example = media_obj.get("example")
        examples = media_obj.get("examples")
        if example is not None:
            out.append("Example:\n")
            out.append("```json")
            out.append(json.dumps(example, indent=2))
            out.append("```\n")
        elif examples:
            for name, ex in examples.items():
                out.append(f"Example ({name}):\n")
                out.append("```json")
                out.append(json.dumps(ex.get("value"), indent=2))
                out.append("```\n")
    return "\n".join(out)


def _responses_section(responses):
    out = ["### Responses\n"]
    for status, resp in responses.items():
        desc = resp.get("description", "")
        out.append(f"#### `{status}` — {desc}\n")
        content = resp.get("content", {})
        for media, media_obj in content.items():
            if media == "text/html":
                out.append(f"Returns `text/html`.\n")
                continue
            example = media_obj.get("example")
            examples = media_obj.get("examples")
            if example is not None:
                out.append(f"`{media}` example:\n")
                out.append("```json")
                out.append(json.dumps(example, indent=2))
                out.append("```\n")
            elif examples:
                for name, ex in examples.items():
                    out.append(f"`{media}` example ({name}):\n")
                    out.append("```json")
                    out.append(json.dumps(ex.get("value"), indent=2))
                    out.append("```\n")
    return "\n".join(out)


def render_reference(spec):
    info = spec.get("info", {})
    lines = [
        "# travel-assistant API reference",
        "",
        "> Generated from the live OpenAPI spec — do not edit by hand. "
        "Regenerate with `python3 docs/generate_api_docs.py` "
        "(run from the `travel-assistant/` directory).",
        "",
        f"**Version:** `{info.get('version', '')}`",
        "",
        "**Base URL:** `http://127.0.0.1:8000` (default; see `TA_SERVICE_HOST` / "
        "`TA_SERVICE_PORT`)",
        "",
        "**Auth:** every endpoint requires "
        "`Authorization: Bearer <api_key>` — see [authentication](authentication.md).",
        "",
        "**Errors:** `application/problem+json` with a machine-readable `code` — "
        "see the [error catalog](errors.md).",
        "",
        "## Endpoints",
        "",
    ]
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            summary = op.get("summary") or ""
            lines.append(f"- `{method.upper()} {path}` — {summary}")
    lines.append("")

    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            summary = op.get("summary") or ""
            lines.append(f"## `{method.upper()} {path}`")
            lines.append("")
            if summary:
                lines.append(f"*{summary}.*")
                lines.append("")
            description = (op.get("description") or "").strip()
            if description:
                lines.append(description)
                lines.append("")
            params = [p for p in op.get("parameters", [])]
            if params:
                lines.append("### Parameters\n")
                lines.append(_param_table(params))
            body_md = _body_section(op.get("requestBody"))
            if body_md:
                lines.append(body_md)
            lines.append(_responses_section(op.get("responses", {})))
    return "\n".join(lines).rstrip() + "\n"


def main(argv):
    check = "--check" in argv
    spec = app.openapi()
    openapi_text = json.dumps(spec, indent=2) + "\n"
    reference_text = render_reference(spec)

    targets = {
        HERE / "openapi.json": openapi_text,
        HERE / "api-reference.md": reference_text,
    }
    failed = False
    for path, text in targets.items():
        if check:
            current = path.read_text() if path.exists() else ""
            if current != text:
                failed = True
                print(f"STALE: {path.relative_to(PROJECT)}")
                print("".join(difflib.unified_diff(
                    current.splitlines(True), text.splitlines(True),
                    fromfile="committed", tofile="generated")))
        else:
            path.write_text(text)
            print(f"wrote {path.relative_to(PROJECT)}")
    if check:
        if failed:
            print("\nDocs are stale — re-run without --check to regenerate.")
            return 1
        print("docs are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
