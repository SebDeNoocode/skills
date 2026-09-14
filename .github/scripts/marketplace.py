#!/usr/bin/env python3
"""Build the marketplace manifests from the plugin directories.

    python3 .github/scripts/marketplace.py            # rewrite the two manifests
    python3 .github/scripts/marketplace.py --check    # exit 1 if they are out of date

Every directory under featured/ and community/ that carries .claude-plugin/plugin.json is one
entry. The tier is the top-level folder. Contributors never edit the manifests: a workflow on
main regenerates them after each merge.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIERS = ("featured", "community")

MARKETPLACE = {
    "name": "qonto",
    "owner": {"name": "Qonto", "url": "https://qonto.com"},
    "description": "Agent Skills for business banking and financial tools on Qonto. "
                   "Featured plugins are built by Qonto, community plugins are reviewed by Qonto before they ship.",
}

CLAUDE_OUT = ROOT / ".claude-plugin" / "marketplace.json"
CODEX_OUT = ROOT / ".agents" / "plugins" / "marketplace.json"


def plugins() -> list[tuple[str, Path, dict]]:
    out = []
    for tier in TIERS:
        base = ROOT / tier
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            manifest = d / ".claude-plugin" / "plugin.json"
            if d.is_dir() and manifest.is_file():
                out.append((tier, d, json.loads(manifest.read_text(encoding="utf-8"))))
    return out


def claude_entry(tier: str, d: Path, m: dict) -> dict:
    e = {
        "name": m["name"],
        "source": f"./{tier}/{d.name}",
        "description": m.get("description", ""),
        "version": m.get("version", "0.1.0"),
        "category": tier.capitalize(),
        "tags": sorted(set(m.get("keywords", [])) | {tier}),
    }
    for k in ("author", "homepage", "repository", "license"):
        if k in m:
            e[k] = m[k]
    return e


def codex_entry(tier: str, d: Path, m: dict) -> dict:
    return {
        "name": m["name"],
        "source": {"source": "local", "path": f"./{tier}/{d.name}"},
        "description": m.get("description", ""),
        "policy": {"installation": "AVAILABLE"},
        "category": tier.capitalize(),
        "tags": sorted(set(m.get("keywords", [])) | {tier}),
    }


def render() -> tuple[str, str]:
    found = plugins()
    claude = dict(MARKETPLACE, plugins=[claude_entry(t, d, m) for t, d, m in found])
    codex = {
        "name": MARKETPLACE["name"],
        "interface": {"displayName": "Qonto"},
        "plugins": [codex_entry(t, d, m) for t, d, m in found if (d / ".codex-plugin" / "plugin.json").is_file()],
    }
    return json.dumps(claude, indent=2) + "\n", json.dumps(codex, indent=2) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the committed manifests match the plugin directories")
    args = ap.parse_args()
    claude, codex = render()
    if args.check:
        stale = [p for p, want in ((CLAUDE_OUT, claude), (CODEX_OUT, codex))
                 if not p.is_file() or p.read_text(encoding="utf-8") != want]
        for p in stale:
            print(f"out of date: {p.relative_to(ROOT).as_posix()}")
        return 1 if stale else 0
    CLAUDE_OUT.parent.mkdir(parents=True, exist_ok=True)
    CODEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_OUT.write_text(claude, encoding="utf-8")
    CODEX_OUT.write_text(codex, encoding="utf-8")
    n = len(plugins())
    print(f"{n} plugin(s): wrote {CLAUDE_OUT.relative_to(ROOT).as_posix()} and {CODEX_OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
