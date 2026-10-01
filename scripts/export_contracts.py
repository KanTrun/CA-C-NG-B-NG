"""Export JSON Schema for the five contracts + real TypeScript types."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))

from ca_contracts import CONTRACTS  # noqa: E402
from ca_contracts.catchment_survey_v2 import (  # noqa: E402
    CatchmentSurveyResponse as CatchmentSurveyResponseV2,
)

OUT = ROOT / "packages" / "contracts" / "schema"

# Schema xuất riêng, KHÔNG nằm trong CONTRACTS (giữ nguyên phạm vi TS export
# và test_contracts.py). Nguồn: plan 260913-1455 mục 3.
EXTRA_SCHEMAS: dict[str, type] = {
    "CatchmentPriceSurveyV2": CatchmentSurveyResponseV2,
}

_TS_PRIM = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}


def _ts_literal(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def _ts_type(node: Any, defs: dict[str, Any]) -> str:
    """Map one JSON Schema node to a TS type expression (pydantic v2 shapes)."""
    if not isinstance(node, dict):
        return "unknown"
    if "$ref" in node:
        return str(node["$ref"]).rsplit("/", 1)[-1]
    if "enum" in node:
        return " | ".join(dict.fromkeys(_ts_literal(v) for v in node["enum"]))
    if "anyOf" in node:
        parts = [_ts_type(x, defs) for x in node["anyOf"]]
        return " | ".join(dict.fromkeys(parts))
    t = node.get("type")
    if t == "array":
        item = _ts_type(node.get("items") or {}, defs)
        return f"Array<{item}>" if "|" in item else f"{item}[]"
    if t == "object" or "properties" in node:
        props = node.get("properties")
        if isinstance(props, dict) and props:
            req = set(node.get("required") or [])
            fields = [
                f"{k}{'' if k in req else '?'}: {_ts_type(v, defs)}"
                for k, v in props.items()
            ]
            return "{ " + "; ".join(fields) + " }"
        add = node.get("additionalProperties")
        if isinstance(add, dict):
            return f"Record<string, {_ts_type(add, defs)}>"
        return "Record<string, JsonValue>"
    if isinstance(t, dict):  # union of primitive types
        return " | ".join(dict.fromkeys(_ts_type({**node, "type": x}, defs) for x in t["type"]))
    return _TS_PRIM.get(str(t), "unknown")


def _ts_fields(schema: dict[str, Any], defs: dict[str, Any]) -> list[str]:
    req = set(schema.get("required") or [])
    return [
        f"  {k}{'' if k in req else '?'}: {_ts_type(v, defs)};"
        for k, v in (schema.get("properties") or {}).items()
    ]


def ts_types_from_schemas(schemas: dict[str, dict[str, Any]]) -> str:
    """Một interface mỗi hợp đồng; nested $defs cũng xuất để tham chiếu được."""
    lines = [
        "// Sinh tự động từ JSON Schema của pydantic — chạy `make contracts`.",
        "// KHÔNG sửa tay: nguồn sự thật là packages/contracts/src/ca_contracts.",
        "",
        "export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };",
        "",
    ]
    emitted: set[str] = set()
    for name, schema in schemas.items():
        defs: dict[str, Any] = schema.get("$defs") or {}
        for def_name, def_schema in defs.items():
            if def_name in emitted or not isinstance(def_schema, dict):
                continue
            if def_schema.get("properties"):
                lines.append(f"export interface {def_name} {{")
                lines.extend(_ts_fields(def_schema, defs))
                lines.append("}")
            else:
                lines.append(f"export type {def_name} = {_ts_type(def_schema, defs)};")
            lines.append("")
            emitted.add(def_name)
        if name in emitted:
            continue
        lines.append(f"export interface {name} {{")
        lines.extend(_ts_fields(schema, defs))
        lines.append("}")
        lines.append("")
        emitted.add(name)
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    schemas: dict[str, dict[str, Any]] = {}
    for name, model in CONTRACTS.items():
        schema = model.model_json_schema()
        schemas[name] = schema
        path = OUT / f"{name}.json"
        # `newline="\n"` BẮT BUỘC: `write_text` mặc định dịch `\n` thành CRLF trên
        # Windows, làm git tưởng 79 file đổi (thực ra chỉ khác xuống dòng) và gây
        # nhiễu diff. CI chạy Linux nên không thấy, nhưng dev Windows thì có.
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        index[name] = str(path.relative_to(ROOT)).replace("\\", "/")
    # Schema bổ sung nằm ngoài CONTRACTS (không vào TS bundle dùng chung).
    for name, model in EXTRA_SCHEMAS.items():
        schema = model.model_json_schema()
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        index[name] = str(path.relative_to(ROOT)).replace("\\", "/")
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    ts = ROOT / "packages" / "contracts" / "ts" / "contracts.ts"
    ts.parent.mkdir(parents=True, exist_ok=True)
    ts.write_text(ts_types_from_schemas(schemas), encoding="utf-8", newline="\n")
    print("wrote", len(CONTRACTS) + len(EXTRA_SCHEMAS), "schemas + ts types")


if __name__ == "__main__":
    main()
