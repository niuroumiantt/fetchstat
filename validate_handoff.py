#!/usr/bin/env python3
"""Read-only, offline employee package checks; never an adoption/HTTP receiver."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

TEAMS = {"fetchstat", "fetchfilings", "fetchreports", "fetchquotes"}
SHA = re.compile(r"[a-f0-9]{64}\Z")
REVISION = re.compile(r"[a-f0-9]{40}\Z")
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_ROWS = 100000


def _file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("invalid relative path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or any(p in {".", ".."} for p in relative.split("/")):
        raise ValueError("unsafe relative path")
    candidate = root
    for part in parts.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("symlink is not a package file")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
        raise ValueError("package file missing or outside root")
    return candidate


def _json(root: Path, relative: str):
    path = _file(root, relative)
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("metadata too large")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_bad_constant)


def _bad_constant(value):
    raise ValueError("non-finite JSON number")


def _rows(root: Path, relative: str):
    with _file(root, relative).open("rb") as stream:
        for index in range(1, MAX_ROWS + 2):
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return
            if index > MAX_ROWS or len(raw) > MAX_LINE_BYTES:
                raise ValueError("JSONL row/line limit exceeded")
            try:
                yield index, json.loads(raw, parse_constant=_bad_constant)
            except (ValueError, UnicodeError):
                yield index, None


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value):
    try:
        return (isinstance(value, str) and "T" in value
                and datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None)
    except ValueError:
        return False


def _time(value):
    if not isinstance(value, dict):
        return False
    precision, raw = value.get("precision"), value.get("value")
    if precision == "unknown":
        return raw is None
    if not _text(value.get("basis")) or not isinstance(raw, str):
        return False
    try:
        if precision == "year":
            return bool(re.fullmatch(r"[0-9]{4}", raw)) and 1 <= int(raw) <= 9999
        if precision == "month":
            return bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}", raw)) and bool(date.fromisoformat(raw + "-01"))
        if precision == "day":
            return bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw)) and bool(date.fromisoformat(raw))
        return precision == "datetime" and _timestamp(raw)
    except ValueError:
        return False


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _observation_errors(row, item_ids):
    if not isinstance(row, dict):
        return ["invalid JSON object"]
    errors = []
    if not _text(row.get("observation_id")) or row.get("source_item_id") not in item_ids:
        errors.append("missing ID or dangling source reference")
    obj = row.get("object", {})
    if not isinstance(obj, dict):
        obj = {}
    if (obj.get("type") not in {"site", "company", "product", "statistic_series", "study"}
            or not _text(obj.get("name")) or not isinstance(obj.get("identifiers", {}), dict)):
        errors.append("object identity shape invalid")
    if obj.get("match_status") == "matched":
        if not _text(obj.get("canonical_id")) or not _text(obj.get("match_basis")):
            errors.append("matched object requires ID and basis; actual matching is not checked offline")
    elif obj.get("match_status") != "unresolved" or obj.get("canonical_id") is not None:
        errors.append("unresolved object must not claim a canonical ID")
    if not _text(row.get("metric")) or not _text(row.get("scope")):
        errors.append("metric/scope missing")
    if row.get("kind") not in {"reported", "measured", "estimated", "calculated", "forecast", "offer"}:
        errors.append("kind invalid")
    value = row.get("value", {})
    if not isinstance(value, dict):
        value = {}
    typ = value.get("type")
    valid_value = ((typ == "number" and _number(value.get("number")))
                   or (typ == "range" and _number(value.get("lower")) and _number(value.get("upper"))
                       and value["lower"] <= value["upper"])
                   or (typ == "text" and _text(value.get("text"))))
    if not valid_value or not _text(value.get("raw")):
        errors.append("value/raw invalid (ranges retain both bounds)")
    if (typ in {"number", "range"} and not _text(row.get("unit"))) or "unit" not in row:
        errors.append("numeric unit missing")
    for key in ("effective_time", "published_time"):
        if not _time(row.get(key)):
            errors.append(key + " invalid; unknown is allowed, invented precision is not")
    evidence = row.get("evidence", {})
    if not isinstance(evidence, dict) or any(not _text(evidence.get(k)) for k in ("locator", "quote", "context")):
        errors.append("evidence location/quote/context missing")
    if "revision_of" not in row or not (row["revision_of"] is None or _text(row["revision_of"])):
        errors.append("revision_of invalid")
    for key in ("conflicts_with", "target_ids"):
        values = row.get(key, [] if key == "target_ids" else None)
        if not isinstance(values, list) or any(not _text(v) for v in values):
            errors.append(key + " invalid")
    # Reception, research review and adoption belong to the receiving system.
    if any(k in row for k in ("first_received_at", "adopted", "verified_date", "reviewed_at")):
        errors.append("supplier cannot assert reception/review/adoption")
    return errors


def validate(package):
    root = Path(package).expanduser().resolve(strict=True)
    errors, invalid, item_ids, paths = [], [], set(), {}
    manifest = _json(root, "manifest.json")
    if (not isinstance(manifest, dict) or manifest.get("contract") != "fetchdata-handoff/1"
            or manifest.get("provider_id") not in TEAMS or not _text(manifest.get("delivery_id"))
            or not isinstance(manifest.get("collector_revision"), str)
            or not REVISION.fullmatch(manifest["collector_revision"])
            or not _timestamp(manifest.get("generated_at"))):
        raise ValueError("manifest identity/version/time invalid")
    items = manifest.get("items")
    if not isinstance(items, list) or not items or len(items) > 10000:
        raise ValueError("items must contain 1..10000 source records")
    for index, item in enumerate(items):
        label = "item[" + str(index) + "]"
        try:
            if not isinstance(item, dict):
                raise ValueError("item is not an object")
            if any(not _text(item.get(k)) for k in ("item_id", "source_id", "source_item_id", "title", "publisher", "content_type")):
                raise ValueError("source identity/metadata missing")
            if item["item_id"] in item_ids:
                raise ValueError("duplicate item_id")
            item_ids.add(item["item_id"])
            url = urlsplit(item.get("url", ""))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise ValueError("source URL missing/credentialed")
            if "retrieved_at" not in item or (item["retrieved_at"] is not None and not _timestamp(item["retrieved_at"])):
                raise ValueError("retrieved_at invalid")
            if item["retrieved_at"] is None and (not _timestamp(item.get("reused_at")) or not _text(item.get("provenance_id"))):
                raise ValueError("unknown old download needs reuse time and provenance reference")
            if item.get("access_scope") not in {"public", "restricted", "unknown"} or item.get("completeness") not in {"complete", "partial", "unknown"}:
                raise ValueError("access/completeness invalid")
            if "version_of" not in item or not (item["version_of"] is None or _text(item["version_of"])):
                raise ValueError("version_of invalid")
            sha, relative = item.get("sha256"), item.get("path")
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise ValueError("SHA invalid")
            if not isinstance(relative, str) or not re.fullmatch(r"originals/" + sha + r"\.[A-Za-z0-9]{1,12}", relative):
                raise ValueError("original must use content-addressed relative path")
            path = _file(root, relative)
            if relative not in paths:
                hasher = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(block)
                if hasher.hexdigest() != sha:
                    raise ValueError("SHA mismatch")
                paths[relative] = sha
        except (ValueError, TypeError, OSError) as error:
            errors.append(label + ": " + str(error))
    sums = _file(root, "SHA256SUMS")
    if sums.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("checksum metadata too large")
    lines = sums.read_text(encoding="ascii").splitlines()
    if sorted(lines) != sorted(sha + "  " + name for name, sha in paths.items()):
        errors.append("SHA256SUMS differs from unique manifest files")
    observation_ids, total = set(), 0
    for line, row in _rows(root, "observations.jsonl"):
        total += 1
        issues = _observation_errors(row, item_ids)
        if isinstance(row, dict) and _text(row.get("observation_id")):
            if row["observation_id"] in observation_ids:
                issues.append("duplicate observation_id")
            observation_ids.add(row["observation_id"])
        if issues:
            invalid.append({"line": line, "errors": issues})
    failure_rows = 0
    for line, row in _rows(root, "errors.jsonl"):
        failure_rows += 1
        if (not isinstance(row, dict) or any(not _text(row.get(k)) for k in ("source_id", "stage", "error_type", "next_action"))
                or not _timestamp(row.get("at")) or not isinstance(row.get("retryable"), bool)):
            errors.append("errors.jsonl line " + str(line) + " invalid")
    report = _json(root, "run-report.json")
    if (not isinstance(report, dict) or report.get("team") != manifest["provider_id"]
            or report.get("collector_revision") != manifest["collector_revision"]
            or not _text(report.get("run_id")) or not _timestamp(report.get("started_at"))
            or not _timestamp(report.get("finished_at")) or not isinstance(report.get("counts"), dict)
            or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in report.get("counts", {}).values())
            or not _number(report.get("duration_seconds")) or report["duration_seconds"] < 0
            or not isinstance(report.get("bytes_downloaded"), int) or isinstance(report["bytes_downloaded"], bool)
            or report["bytes_downloaded"] < 0):
        errors.append("run-report identity/time/counts/resources invalid")
    return {"contract": manifest["contract"], "delivery_id": manifest["delivery_id"],
            "provider_id": manifest["provider_id"], "source_items": len(items), "unique_originals": len(paths),
            "candidate_rows": total, "valid_candidate_rows": total - len(invalid), "failure_rows": failure_rows,
            "package_errors": errors, "invalid_candidates": invalid,
            "offline_valid": not errors and not invalid, "formal_adoption": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    args = parser.parse_args()
    try:
        report = validate(args.package)
    except (ValueError, TypeError, KeyError, OSError, UnicodeError) as error:
        report = {"offline_valid": False, "formal_adoption": False, "package_errors": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["offline_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
