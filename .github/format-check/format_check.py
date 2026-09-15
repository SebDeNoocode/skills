#!/usr/bin/env python3
"""Format check: public, deterministic shape rules for community skills.

Runs the same locally and in CI:

    python3 .github/format-check/format_check.py --all                # every plugin under community/ and featured/
    python3 .github/format-check/format_check.py --base origin/main   # only what a branch changed

Everything here is a rule a contributor can read, reproduce and fix. Intent and
behaviour are reviewed elsewhere; this gate only checks shape.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("format-check: pyyaml is required (pip install pyyaml==6.0.2)")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATALOGUE = json.loads((HERE / "tools.json").read_text())
KNOWN_TOOLS: dict[str, dict] = {t["name"]: t for t in CATALOGUE["tools"]}
WRITE_TOOLS = {n for n, t in KNOWN_TOOLS.items() if not t["read_only"]}
DESTRUCTIVE_TOOLS = {n for n, t in KNOWN_TOOLS.items() if t["destructive"]}

PLUGIN_ROOTS = ("featured", "community")   # featured/ is Qonto's, community/ takes contributions
CONTRIB_ROOT = "community"
SKILLS_DIR = "skills"                      # inside a plugin: <plugin>/skills/<skill>/SKILL.md
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][\w.]+)?$")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
TOOL_TOKEN_RE = re.compile(r"`(?:mcp__qonto__|qonto\.)?([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
# mcp__qonto__<tool> anywhere, or qonto.<tool> where <tool> has the snake_case shape every catalogue entry has
# (so qonto.com, qonto.co, qonto.s3 in prose are domains, not tool references)
QUALIFIED_TOOL_RE = re.compile(r"mcp__qonto__([A-Za-z0-9_]+)|\bqonto\.([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b(?![./-])")
TOOL_VERBS = ("list_", "get_", "create_", "update_", "delete_", "send_", "mark_",
              "change_", "modify_", "remove_", "decline_", "request_", "upload_")
URL_RE = re.compile(r"https?://[^\s)\]>'\"`]+", re.I)

FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata",
                    "compatibility", "permissions"}
NATIVE_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "Bash", "Glob", "Grep", "WebFetch",
                "WebSearch", "Task", "NotebookEdit", "TodoWrite", "AskUserQuestion", "Skill"}

TEXT_EXT = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".py", ".js", ".mjs", ".cjs",
            ".ts", ".tsx", ".jsx", ".sh", ".html", ".css", ".toml", ".example", ".svg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_EXT = TEXT_EXT | IMAGE_EXT
ALLOWED_DOTFILES = {".mcp.json", ".gitignore"}
ALLOWED_DOTDIRS = {".claude-plugin", ".codex-plugin"}   # the plugin's own manifests
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh"}

MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_PLUGIN_BYTES = 10 * 1024 * 1024
MAX_FILES = 200
SKILL_MD_WARN_LINES = 500
SKILL_MD_FAIL_LINES = 1000

# Paths only maintainers may touch (catalogue, manifests, workflows, this check, the featured tier).
PROTECTED_PREFIXES = (".github/", ".claude-plugin/", ".codex-plugin/", ".agents/", "featured/")
PROTECTED_FILES = {"LICENSE", "MAINTAINERS", "CODEOWNERS", "DCO"}

# Install commands are tokenised rather than regex-matched so flags (`npm i -D x`, `pip install -U x`) cannot hide
# the package, several packages on one line are all checked, and `pkg@latest` counts as unpinned.
INSTALLERS = (
    (re.compile(r"\bpip3?\s+install\b"), "pip"),
    (re.compile(r"\buv\s+pip\s+install\b"), "pip"),
    (re.compile(r"\b(?:npm|pnpm)\s+(?:i|install|add)\b"), "npm"),
    (re.compile(r"\byarn\s+add\b"), "npm"),
    (re.compile(r"\bnpx\b"), "npx"),
    (re.compile(r"\buvx\b"), "uvx"),
)
FLAG_TAKES_VALUE = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url", "--extra-index-url", "-t",
                    "--target", "--prefix", "--python", "-p", "--package", "--from", "--with", "--filter", "--registry",
                    "--index", "--find-links", "-f", "--root", "--platform", "--implementation", "--abi"}
PIP_PINNED = re.compile(r"^[A-Za-z0-9][\w.\-]*(?:\[[\w,.\-]+\])?==\d[\w.]*$")
NPM_EXACT = re.compile(r"^\d+\.\d+\.\d+(?:[-+][\w.]+)?$")
SPEC_TOKEN = re.compile(r"^[-@\w][\w./@:+~^<>=!,\[\]-]*$")
LOCAL_SPEC = ("./", "../", "/", "~", "file:", "git+", "git:", "github:", "http://", "https://", "ssh://", "link:", "workspace:")
NPX_YES = re.compile(r"\bnpx\s+(-y|--yes)\b")


@dataclass
class Finding:
    level: str          # fail | warn | note
    check: str
    message: str
    file: str = ""
    line: int = 0
    fix: str = ""


@dataclass
class Report:
    plugins: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, check: str, message: str, file: str = "", line: int = 0, fix: str = ""):
        self.findings.append(Finding(level, check, message, file, line, fix))

    @property
    def failed(self) -> bool:
        return any(f.level == "fail" for f in self.findings)


# --------------------------------------------------------------------------- helpers

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True).stdout


def changed_files(base: str, head: str) -> list[str]:
    # three-dot: only what the branch adds since it forked from base. In CI head is the merge commit, so
    # this equals the plain diff; locally it keeps base's own newer commits out of the picture.
    out = git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}")
    return sorted(p for p in out.splitlines() if p.strip())


def all_plugin_files() -> list[str]:
    out = git("ls-files", "--", *PLUGIN_ROOTS, "README.md")
    return sorted(p for p in out.splitlines() if p.strip())


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> tuple[dict | None, str, int]:
    """Returns (frontmatter, body, body_start_line). None when absent or invalid."""
    if not text.startswith("---"):
        return None, text, 1
    lines = text.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError:
                return None, text, 1
            if not isinstance(data, dict):
                return None, text, 1
            return data, "\n".join(lines[i + 1:]), i + 2
    return None, text, 1


def maintainers() -> set[str]:
    p = ROOT / "MAINTAINERS"
    if not p.is_file():
        return set()
    return {l.strip().lstrip("@").lower() for l in p.read_text().splitlines()
            if l.strip() and not l.startswith("#")}


def suggest(name: str) -> str:
    m = difflib.get_close_matches(name, KNOWN_TOOLS, n=1, cutoff=0.6)
    return f" Did you mean `{m[0]}`?" if m else ""


SIGNOFF_RE = re.compile(r"^Signed-off-by:\s*(.+?)\s*<([^>]+)>\s*$", re.M)


def check_dco(base: str, head: str, rep: Report):
    """Every commit the branch adds carries a Signed-off-by line whose e-mail is the author's or committer's."""
    out = git("log", "--no-merges", "--format=%H%x00%ae%x00%ce%x00%B%x1e", f"{base}..{head}")
    fix = ("Sign off every commit: `git rebase --signoff origin/main` then force-push, or `git commit --amend -s` "
           "for a single commit. The sign-off certifies the Developer Certificate of Origin in `DCO`.")
    for rec in out.split("\x1e"):
        if not rec.strip():
            continue
        sha, ae, ce, body = rec.lstrip("\n").split("\x00", 3)
        offs = SIGNOFF_RE.findall(body)
        if not offs:
            rep.add("fail", "dco", f"Commit `{sha[:7]}` has no `Signed-off-by` line.", fix=fix)
        elif not any(e.strip().lower() in {ae.lower(), ce.lower()} for _, e in offs):
            who = ", ".join(e for _, e in offs)
            rep.add("fail", "dco", f"Commit `{sha[:7]}` is signed off by {who}, but authored by {ae}.", fix=fix)


# --------------------------------------------------------------------------- checks

def check_repo_level(files: list[str], actor: str, rep: Report) -> set[str]:
    """Protected paths, stray files. Returns the set of plugin dirs touched."""
    is_maintainer = actor.lower() in maintainers() if actor else False
    plugins: set[str] = set()
    for f in files:
        parts = f.split("/")
        if f.startswith(PROTECTED_PREFIXES) or f in PROTECTED_FILES:
            if not is_maintainer:
                rep.add("fail", "protected-path",
                        f"`{f}` is maintained by the Qonto team and cannot change in a skill submission.",
                        file=f, fix=f"Remove this file from the pull request. Contributions go under `{CONTRIB_ROOT}/`.")
                continue
            if parts[0] not in PLUGIN_ROOTS:
                continue  # a maintainer edit to the tooling: a featured plugin falls through and gets checked
        if f == "README.md" or (parts[0] in PLUGIN_ROOTS and parts[1:] == [".gitkeep"]):
            continue
        if parts[0] in PLUGIN_ROOTS and len(parts) >= 3:
            plugins.add(f"{parts[0]}/{parts[1]}")
            continue
        if parts[0] in PLUGIN_ROOTS and len(parts) == 2:
            rep.add("fail", "stray-file", f"`{f}` sits loose in `{parts[0]}/` and would be ignored by every agent.",
                    file=f, fix=f"Move it into `{parts[0]}/<plugin-name>/`.")
            continue
        if is_maintainer and "/" not in f and f.lower().endswith(".md"):
            continue  # maintainers may edit top-level docs
        rep.add("fail", "stray-file", f"`{f}` is outside `{CONTRIB_ROOT}/<plugin-name>/`.",
                file=f, fix=f"A contribution is one plugin directory: `{CONTRIB_ROOT}/<plugin-name>/.claude-plugin/plugin.json` "
                            "plus its skills under `skills/<skill-name>/SKILL.md`. Move the file there, or drop it if it is "
                            "build output or documentation for humans.")
    return plugins


def walk_plugin(pdir: Path, rep: Report) -> list[Path]:
    kept: list[Path] = []
    total = 0
    count = 0
    for p in sorted(pdir.rglob("*")):
        r = rel(p)
        if p.is_symlink():
            rep.add("fail", "file-type", f"`{r}` is a symlink.", file=r, fix="Ship the file itself.")
            continue
        if p.is_dir():
            if p.name.startswith(".") and p.name not in ALLOWED_DOTDIRS:
                rep.add("fail", "file-type", f"Hidden directory `{r}/` is not allowed in a plugin.",
                        file=r, fix="Remove it. Manifests go in `.claude-plugin/`, hooks in `hooks/`, agents in `agents/`, "
                                    "commands in `commands/`.")
            continue
        count += 1
        size = p.stat().st_size
        total += size
        if p.name.startswith(".") and p.name not in ALLOWED_DOTFILES:
            rep.add("fail", "file-type", f"Hidden file `{r}` is not allowed.", file=r, fix="Remove it.")
            continue
        ext = p.suffix.lower()
        if p.name in ALLOWED_DOTFILES:
            ext = ".json" if p.name.endswith(".json") else ".txt"
        if p.name.lower() in {"dockerfile", "makefile", "license", "license.md", "readme"}:
            ext = ".txt"
        if ext not in ALLOWED_EXT:
            rep.add("fail", "file-type",
                    f"`{r}` has a file type we do not accept ({ext or 'no extension'}).", file=r,
                    fix="Allowed: Markdown, text, JSON, YAML, CSV, Python, JavaScript/TypeScript, shell, HTML/CSS, "
                        "SVG and PNG/JPEG/GIF/WebP images. No archives, documents, notebooks or compiled files.")
            continue
        if size > MAX_FILE_BYTES:
            rep.add("fail", "size-cap", f"`{r}` is {size // 1024} KiB, over the 1 MiB per-file cap.", file=r,
                    fix="Split it, trim it, or link to it instead.")
            continue
        if ext in TEXT_EXT:
            head = p.read_bytes()[:8192]
            if b"\x00" in head:
                rep.add("fail", "file-type", f"`{r}` looks binary despite its extension.", file=r,
                        fix="Text files only. Re-save it as UTF-8 text or remove it.")
                continue
        kept.append(p)
    if count > MAX_FILES:
        rep.add("fail", "size-cap", f"`{rel(pdir)}/` has {count} files, over the cap of {MAX_FILES}.",
                file=rel(pdir), fix="A skill is instructions plus a few scripts. Remove generated output and vendored code.")
    if total > MAX_PLUGIN_BYTES:
        rep.add("fail", "size-cap", f"`{rel(pdir)}/` is {total // (1024 * 1024)} MiB, over the 10 MiB cap.",
                file=rel(pdir), fix="Remove large assets.")
    return kept


def str_list(perms: dict, key: str, r: str, rep: Report) -> list[str]:
    """`permissions.<key>` as a list of strings, or a finding and an empty list."""
    v = perms.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        rep.add("fail", "permissions", f"`permissions.{key}` must be a list of strings.", file=r, line=2,
                fix=f"Example: `{key}: []` or `{key}: [one, two]`.")
        return []
    return v


def check_plugin_manifest(pdir: Path, rep: Report) -> dict:
    """`<plugin>/.claude-plugin/plugin.json`: the marketplace entry is generated from it."""
    name = pdir.name
    if not NAME_RE.match(name) or len(name) > 64:
        rep.add("fail", "layout", f"Plugin directory `{name}` must be lowercase letters, digits and single hyphens (max 64).",
                file=rel(pdir), fix="Rename the directory, for example `overdue-invoice-chaser`.")
    manifest = pdir / ".claude-plugin" / "plugin.json"
    r = rel(manifest)
    if not manifest.is_file():
        rep.add("fail", "layout", f"`{r}` is missing.", file=rel(pdir),
                fix="Every plugin carries a manifest, the marketplace entry is built from it:\n```json\n{\n"
                    '  "name": "' + name + '",\n  "version": "0.1.0",\n  "description": "What it does, and when an agent should use it.",\n'
                    '  "author": { "name": "Your name", "url": "https://github.com/you" },\n  "license": "MIT"\n}\n```')
        return {}
    try:
        m = json.loads(read_text(manifest))
    except json.JSONDecodeError as e:
        rep.add("fail", "layout", f"`{r}` is not valid JSON ({e.msg}, line {e.lineno}).", file=r, line=e.lineno)
        return {}
    if not isinstance(m, dict):
        rep.add("fail", "layout", f"`{r}` must be a JSON object.", file=r)
        return {}
    if m.get("name") != name:
        rep.add("fail", "layout", f"Manifest `name` is `{m.get('name')}` but the directory is `{name}`.", file=r,
                fix="Make them identical.")
    desc = m.get("description")
    if not isinstance(desc, str) or len(desc.strip()) < 20:
        rep.add("fail", "layout", "Manifest `description` is missing or too short.", file=r,
                fix="One or two sentences: what the plugin does and who it is for.")
    if not isinstance(m.get("version"), str) or not SEMVER_RE.match(m["version"]):
        rep.add("fail", "layout", f"Manifest `version` `{m.get('version')}` is not a semantic version.", file=r,
                fix="Use `MAJOR.MINOR.PATCH`, for example `0.1.0`.")
    if not isinstance(m.get("author"), dict) or not m["author"].get("name"):
        rep.add("warn", "layout", "Manifest has no `author.name`.", file=r, fix='Add `"author": { "name": "...", "url": "..." }`.')
    if m.get("license") not in (None, "MIT"):
        rep.add("warn", "layout", f"Manifest `license` is `{m.get('license')}`, the repository is MIT.", file=r)
    if "skills" in m and m["skills"] not in ("./skills/", "./skills", "skills", "skills/"):
        rep.add("fail", "layout", f"Manifest `skills` points at `{m['skills']}`.", file=r,
                fix="Skills live in `skills/` inside the plugin. Drop the key or set it to `./skills/`.")
    return m


def check_frontmatter(pdir: Path, rep: Report) -> tuple[dict, set[str], set[str]]:
    """Returns (frontmatter, declared qonto tools, declared network hosts)."""
    skill_md = pdir / "SKILL.md"
    r = rel(skill_md)
    name = pdir.name
    if not NAME_RE.match(name) or len(name) > 64:
        rep.add("fail", "layout", f"Skill directory `{name}` must be lowercase letters, digits and single hyphens (max 64).",
                file=rel(pdir), fix="Rename the directory, for example `overdue-invoice-chaser`.")
    if not skill_md.is_file():
        rep.add("fail", "layout", f"`{rel(pdir)}/SKILL.md` is missing.", file=rel(pdir),
                fix="Every skill needs a `SKILL.md` with YAML frontmatter (`name`, `description`, `permissions`).")
        return {}, set(), set()
    text = read_text(skill_md)
    n_lines = text.count("\n") + 1
    if n_lines > SKILL_MD_FAIL_LINES:
        rep.add("fail", "size-cap", f"`SKILL.md` is {n_lines} lines. The cap is {SKILL_MD_FAIL_LINES}.", file=r,
                fix="Move detail into `references/` and keep `SKILL.md` to the steps an agent follows.")
    elif n_lines > SKILL_MD_WARN_LINES:
        rep.add("warn", "size-cap", f"`SKILL.md` is {n_lines} lines. Aim for under {SKILL_MD_WARN_LINES}.", file=r,
                fix="Move detail into `references/`.")
    fm, _, _ = parse_frontmatter(text)
    if fm is None:
        rep.add("fail", "layout", "`SKILL.md` must start with YAML frontmatter between two `---` lines.", file=r, line=1,
                fix="Start the file with:\n```\n---\nname: my-skill\ndescription: What it does. Use when ...\npermissions:\n  mcp:\n    qonto: []\n  network: []\n  env: []\n  tools: []\n---\n```")
        return {}, set(), set()
    if fm.get("name") != name:
        rep.add("fail", "layout", f"Frontmatter `name` is `{fm.get('name')}` but the directory is `{name}`.", file=r, line=2,
                fix="Make them identical.")
    desc = fm.get("description")
    if not isinstance(desc, str) or len(desc.strip()) < 20:
        rep.add("fail", "layout", "`description` is missing or too short.", file=r, line=2,
                fix="Say what the skill does and when an agent should load it, in one or two sentences.")
    elif len(desc) > 1024:
        rep.add("fail", "layout", f"`description` is {len(desc)} characters. The cap is 1024.", file=r, line=2,
                fix="Keep the trigger in `description`, move the rest into the body.")
    for k in fm:
        if k not in FRONTMATTER_KEYS:
            rep.add("warn", "layout", f"Unknown frontmatter key `{k}`.", file=r, line=2,
                    fix=f"Known keys: {', '.join(sorted(FRONTMATTER_KEYS))}.")

    declared: set[str] = set()
    hosts: set[str] = set()
    perms = fm.get("permissions")
    if not isinstance(perms, dict):
        rep.add("fail", "permissions", "The `permissions` block is missing from the frontmatter.", file=r, line=2,
                fix="Declare what the skill needs, even when the answer is nothing:\n```yaml\npermissions:\n  mcp:\n"
                    "    qonto: [list_client_invoices, get_client]\n  network: []\n  env: []\n  tools: [Read]\n```")
        return fm, declared, hosts
    for key in ("mcp", "network", "env", "tools"):
        if key not in perms:
            rep.add("fail", "permissions", f"`permissions.{key}` is missing.", file=r, line=2,
                    fix=f"Add `{key}: []` if the skill needs none.")
    mcp = perms.get("mcp")
    if mcp is not None and not isinstance(mcp, dict):
        rep.add("fail", "permissions", "`permissions.mcp` must be a map of server name to tool list.", file=r, line=2,
                fix="Example: `mcp:\\n  qonto: [list_transactions]`")
        mcp = {}
    for server, tools in (mcp or {}).items():
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            rep.add("fail", "permissions", f"`permissions.mcp.{server}` must be a list of tool names.", file=r, line=2)
            continue
        if server != "qonto":
            rep.add("note", "permissions", f"Declares a second MCP server `{server}` with {len(tools)} tool(s). "
                    "Reviewers look at this closely.", file=r, line=2)
            continue
        for t in tools:
            if t not in KNOWN_TOOLS:
                rep.add("fail", "tool-name", f"`{t}` is not a Qonto MCP tool.{suggest(t)}", file=r, line=2,
                        fix="Tool names come from the Qonto MCP catalogue. See `.github/format-check/tools.json`.")
            else:
                declared.add(t)
    if declared & DESTRUCTIVE_TOOLS:
        rep.add("note", "permissions", "Declares destructive tools: " + ", ".join(sorted(declared & DESTRUCTIVE_TOOLS)) +
                ". Reviewers will check every call site.", file=r, line=2)
    elif declared & WRITE_TOOLS:
        rep.add("note", "permissions", "Declares write tools: " + ", ".join(sorted(declared & WRITE_TOOLS)) + ".",
                file=r, line=2)
    for h in str_list(perms, "network", r, rep):
        if not HOST_RE.match(h.lower()):
            rep.add("fail", "permissions", f"`permissions.network` entry `{h}` is not a hostname.", file=r, line=2,
                    fix="Use bare hostnames such as `api.example.com`, no scheme, no path, no wildcard.")
        else:
            hosts.add(h.lower())
    for e in str_list(perms, "env", r, rep):
        if not ENV_RE.match(e):
            rep.add("fail", "permissions", f"`permissions.env` entry `{e}` is not an environment variable name.",
                    file=r, line=2, fix="Upper-case letters, digits and underscores, for example `MY_SERVICE_TOKEN`.")
    for t in str_list(perms, "tools", r, rep):
        if t not in NATIVE_TOOLS:
            rep.add("warn", "permissions", f"`permissions.tools` entry `{t}` is not a native agent tool we know.",
                    file=r, line=2, fix=f"Known: {', '.join(sorted(NATIVE_TOOLS))}.")

    at = fm.get("allowed-tools")
    if at:
        items = at.replace(",", " ").split() if isinstance(at, str) else [str(x) for x in at]
        for item in items:
            if item.startswith("mcp__qonto__"):
                t = item[len("mcp__qonto__"):]
                if t not in KNOWN_TOOLS:
                    rep.add("fail", "tool-name", f"`allowed-tools` lists `{item}`, which is not a Qonto MCP tool.{suggest(t)}",
                            file=r, line=2)
                elif t not in declared:
                    rep.add("fail", "permissions", f"`allowed-tools` lists `{item}` but `permissions.mcp.qonto` does not declare `{t}`.",
                            file=r, line=2, fix="Add it to `permissions.mcp.qonto`.")
    return fm, declared, hosts


DENY_KEYS = ("disallowedTools", "disallowed-tools", "disallowed_tools", "deny", "denied", "blocked")
DENY_LINE_RE = re.compile(r"^\s*(?:" + "|".join(DENY_KEYS) + r")\s*:")


def blank_deny_lists(text: str, r: str, rep: Report) -> str:
    """Return the text with frontmatter deny lists blanked out (line numbers kept): a tool an agent is forbidden to call
    is not a call site, so it needs no `permissions` entry. Unknown names in a deny list only get a warning."""
    fm, _, _ = parse_frontmatter(text)
    if fm is None:
        return text
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    i = 1
    while i < end:
        if DENY_LINE_RE.match(lines[i]):
            block = [i]
            j = i + 1
            while j < end and (lines[j].startswith((" ", "\t")) or not lines[j].strip()):
                block.append(j); j += 1
            joined = "\n".join(lines[k] for k in block)
            for mm in QUALIFIED_TOOL_RE.finditer(joined):
                t = mm.group(1) or mm.group(2)
                if t not in KNOWN_TOOLS:
                    rep.add("warn", "tool-name", f"Deny list names `{mm.group(0)}`, which is not a Qonto MCP tool, so the entry "
                            f"does nothing.{suggest(t)}", file=r, line=i + 1)
            for k in block:
                lines[k] = ""
            i = j
        else:
            i += 1
    return "\n".join(lines)


def scan_text_file(p: Path, declared: set[str], hosts: set[str], rep: Report,
                   reported: set[str] | None = None, perms_present: bool = True):
    reported = set() if reported is None else reported
    r = rel(p)
    text = read_text(p)
    ext = p.suffix.lower()
    if ext == ".md":
        text = blank_deny_lists(text, r, rep)
    # 1. pinned dependencies
    for ln, line in enumerate(text.splitlines(), 1):
        if NPX_YES.search(line):
            rep.add("fail", "pinned-deps", "`npx --yes` installs and runs a package without asking.", file=r, line=ln,
                    fix="Pin the version (`npx pkg@1.2.3`) and drop `--yes`.")
        for cmd, pkg in unpinned_installs(line):
            rep.add("fail", "pinned-deps", f"`{cmd}` installs `{pkg}` without an exact version.", file=r, line=ln,
                    fix="Pin an exact version, for example `pip install requests==2.32.3`, `npm install left-pad@1.3.0`, "
                        "`npx prettier@3.3.3`.")
    # 2. tool references
    seen: set[str] = set()
    for ln, line in enumerate(text.splitlines(), 1):
        for m in QUALIFIED_TOOL_RE.finditer(line):
            t = m.group(1) or m.group(2)
            if t in seen:
                continue
            seen.add(t)
            if t not in KNOWN_TOOLS:
                if t not in reported:
                    reported.add(t)
                    rep.add("fail", "tool-name", f"`{m.group(0)}` is not a Qonto MCP tool.{suggest(t)}", file=r, line=ln)
            elif t not in declared and perms_present and t not in reported:
                reported.add(t)
                rep.add("fail", "permissions", f"Uses `{t}` but `permissions.mcp.qonto` does not declare it.", file=r, line=ln,
                        fix="Declare it, or remove the reference.")
        for m in TOOL_TOKEN_RE.finditer(line):
            t = m.group(1)
            if t in seen:
                continue
            if t in KNOWN_TOOLS:
                seen.add(t)
                if t not in declared and perms_present and t not in reported:
                    reported.add(t)
                    rep.add("fail", "permissions", f"Uses `{t}` but `permissions.mcp.qonto` does not declare it.",
                            file=r, line=ln, fix="Declare it, or remove the reference.")
            elif t.startswith(TOOL_VERBS) and ext == ".md" and t not in reported:
                seen.add(t)
                reported.add(t)
                rep.add("warn", "tool-name", f"`{t}` looks like a tool name but is not in the Qonto MCP catalogue.{suggest(t)}",
                        file=r, line=ln)
    # 3. .mcp.json servers
    if p.name == ".mcp.json":
        try:
            cfg = json.loads(text)
        except json.JSONDecodeError:
            rep.add("fail", "layout", "`.mcp.json` is not valid JSON.", file=r)
            return
        for sname, s in (cfg.get("mcpServers") or {}).items():
            url = (s or {}).get("url", "")
            host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].lower()
            if url and host not in hosts:
                rep.add("fail", "permissions", f"`.mcp.json` server `{sname}` connects to `{host}`, which `permissions.network` does not declare.",
                        file=r, fix="Add the host to `permissions.network`.")
            rep.add("note", "permissions", f"Bundles an MCP server config `{sname}`.", file=r)


def unpinned_installs(line: str):
    """Yield (command, package) for every package an install command on this line would fetch without an exact version."""
    for verb_re, kind in INSTALLERS:
        for m in verb_re.finditer(line):
            rest = re.split(r"\s(?:&&|\|\||;|\||#|>|2>)\s", line[m.end():])[0]
            rest = rest.split("`")[0]     # an inline code span ends the command in Markdown prose
            toks = rest.replace("'", " ").replace('"', " ").split()
            packages: list[str] = []
            kind0 = kind
            i = 0
            while i < len(toks):
                t = toks[i].rstrip(".,;:)")
                if not t or not SPEC_TOKEN.match(t):
                    break                 # prose after the command, not a package
                if t.startswith("-"):
                    if t in FLAG_TAKES_VALUE and i + 1 < len(toks):
                        if t in ("-p", "--package", "--from", "--with"):   # the value is a package
                            packages.append(toks[i + 1])
                            if kind in ("npx", "uvx"):
                                kind = "cmd-follows"   # the command that follows is not a package any more
                        i += 2
                        continue
                    i += 1
                    continue
                if kind in ("npx", "uvx"):
                    packages.append(t)          # the first bare token is the package, the rest are its arguments
                    break
                if kind == "cmd-follows":
                    break
                packages.append(t)
                i += 1
            for pkg in packages:
                if pkg.startswith(LOCAL_SPEC) or pkg.endswith((".whl", ".tar.gz", ".tgz", ".zip")) or pkg in (".", "-"):
                    continue
                if kind0 == "pip" or (kind0 == "uvx" and "==" in pkg):
                    if not PIP_PINNED.match(pkg):
                        yield m.group(0).strip(), pkg
                    continue
                name, sep, ver = (pkg[1:].partition("@") if pkg.startswith("@") else pkg.partition("@"))
                if not sep or not NPM_EXACT.match(ver):
                    yield m.group(0).strip(), pkg


def check_pinned_manifest(p: Path, rep: Report):
    r = rel(p)
    text = read_text(p)
    if p.name.startswith("requirements") and p.suffix == ".txt":
        for ln, line in enumerate(text.splitlines(), 1):
            s = line.split("#")[0].strip()
            if not s or s.startswith(("-r", "--", "-c")):
                continue
            if "==" not in s.split(";")[0]:
                rep.add("fail", "pinned-deps", f"`{s}` is not pinned to an exact version.", file=r, line=ln,
                        fix="Use `package==1.2.3`.")
    elif p.name == "package.json":
        try:
            pkg = json.loads(text)
        except json.JSONDecodeError:
            rep.add("fail", "layout", "`package.json` is not valid JSON.", file=r)
            return
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            for dep, ver in (pkg.get(section) or {}).items():
                if not isinstance(ver, str) or not re.match(r"^\d+\.\d+\.\d+(?:[-+][\w.]+)?$", ver):
                    rep.add("fail", "pinned-deps", f"`{dep}: {ver}` in `{section}` is not an exact version.", file=r,
                            fix="Use exact versions such as `1.2.3`, no `^`, `~`, ranges, tags or URLs.")
    elif p.name == "pyproject.toml":
        for ln, line in enumerate(text.splitlines(), 1):
            m = re.match(r'^\s*"([A-Za-z0-9_.\-\[\]]+)\s*([<>=!~]{1,2})?', line)
            if m and m.group(2) and m.group(2) != "==":
                rep.add("fail", "pinned-deps", f"`{line.strip()}` is not pinned with `==`.", file=r, line=ln)


def check_hooks(pdir: Path, rep: Report):
    hooks = pdir / "hooks" / "hooks.json"
    if hooks.is_file():
        rep.add("note", "hooks", "Registers agent hooks. Reviewers read every hook and the script it runs.", file=rel(hooks))
    for sub in ("agents", "commands"):
        if (pdir / sub).is_dir():
            rep.add("note", "layout", f"Ships `{sub}/`.", file=rel(pdir / sub))


def check_readme_row(name: str, rep: Report):
    readme = ROOT / "README.md"
    if not readme.is_file() or "Available skills" not in read_text(readme):
        return
    if not re.search(rf"\|\s*\[?`?{re.escape(name)}`?\]?", read_text(readme)):
        rep.add("warn", "readme", f"`README.md` has no row for `{name}` in the **Available skills** table.",
                file="README.md", fix="Add a row so people can find the skill.")


def check_manifest(rep: Report):
    """`claude plugin validate` on the marketplace manifest. Skipped, with a note, when there is no manifest or no CLI."""
    if not (ROOT / ".claude-plugin" / "marketplace.json").is_file():
        rep.add("note", "manifest", "No `.claude-plugin/marketplace.json`, manifest validation skipped.")
        return
    exe = shutil.which("claude")
    if not exe:
        rep.add("note", "manifest", "`claude` CLI not on PATH, skipped `claude plugin validate .`.")
        return
    try:
        out = subprocess.run([exe, "plugin", "validate", ".", "--strict", "--json"], cwd=ROOT, text=True,
                             capture_output=True, timeout=120)
        data = json.loads(out.stdout or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        rep.add("warn", "manifest", f"`claude plugin validate` did not return a report ({e.__class__.__name__}).")
        return
    for w in (data.get("manifest") or {}).get("warnings", []):
        rep.add("warn", "manifest", f"{w.get('path')}: {w.get('message')}", file=".claude-plugin/marketplace.json")
    if not data.get("success", False):
        for err in (data.get("manifest") or {}).get("errors", []):
            rep.add("fail", "manifest", f"{err.get('path')}: {err.get('message')}", file=".claude-plugin/marketplace.json")
        for item in data.get("contents") or []:
            for err in item.get("errors", []):
                rep.add("fail", "manifest", f"{item.get('file')}: {err.get('message')}", file=str(item.get("file", "")))


def check_plugin(name: str, rep: Report):
    pdir = ROOT / name   # <tier>/<plugin>
    if not pdir.is_dir():
        return  # deleted in this PR
    files = walk_plugin(pdir, rep)
    check_plugin_manifest(pdir, rep)
    skills_dir = pdir / SKILLS_DIR
    skill_dirs = sorted(d for d in skills_dir.iterdir() if d.is_dir()) if skills_dir.is_dir() else []
    if not skill_dirs:
        rep.add("fail", "layout", f"`{rel(pdir)}/{SKILLS_DIR}/` has no skill.", file=rel(pdir),
                fix=f"Add at least one `{SKILLS_DIR}/<skill-name>/SKILL.md`.")
    declared: set[str] = set()
    hosts: set[str] = set()
    perms_present = True
    for sd in skill_dirs:
        fm, d, h = check_frontmatter(sd, rep)
        declared |= d
        hosts |= h
        perms_present = perms_present and isinstance(fm.get("permissions"), dict)
    reported: set[str] = set()
    for p in files:
        ext = p.suffix.lower()
        if p.name in {"requirements.txt", "package.json", "pyproject.toml"} or p.name.startswith("requirements"):
            check_pinned_manifest(p, rep)
        if ext in TEXT_EXT and ext != ".svg" or p.name in ALLOWED_DOTFILES:
            scan_text_file(p, declared, hosts, rep, reported=reported, perms_present=perms_present)
    check_hooks(pdir, rep)
    check_readme_row(name, rep)


# --------------------------------------------------------------------------- output

def annotations(rep: Report):
    lvl = {"fail": "error", "warn": "warning", "note": "notice"}
    for f in rep.findings:
        loc = f"file={f.file}," if f.file else ""
        loc += f"line={f.line}," if f.line else ""
        msg = f.message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{lvl[f.level]} {loc}title=format-check/{f.check}::{msg}")


def markdown(rep: Report) -> str:
    fails = [f for f in rep.findings if f.level == "fail"]
    warns = [f for f in rep.findings if f.level == "warn"]
    notes = [f for f in rep.findings if f.level == "note"]
    out = ["<!-- format-check -->"]
    if rep.failed:
        out.append(f"### Format check failed ({len(fails)} to fix)\n")
        out.append("These are shape rules, not a judgement on the skill. Fix them, push, and the check reruns.\n")
    else:
        out.append("### Format check passed\n")
        out.append("The submission has the right shape. The Qonto team reviews every skill before merging.\n")
    if rep.plugins:
        out.append("Plugins in this pull request: " + ", ".join(f"`{p}`" for p in rep.plugins) + "\n")

    def block(title: str, items: list[Finding], with_fix: bool):
        if not items:
            return
        out.append(f"<details open><summary><b>{title}</b> ({len(items)})</summary>\n")
        for f in items:
            where = f"`{f.file}`" + (f":{f.line}" if f.line else "") if f.file else ""
            out.append(f"- **{f.check}** {where}  \n  {f.message}")
            if with_fix and f.fix:
                out.append(f"  \n  Fix: {f.fix}" if "```" not in f.fix else f"  \n  Fix:\n{f.fix}")
        out.append("\n</details>\n")

    block("Must fix", fails, True)
    block("Worth a look", warns, True)
    block("For the reviewers", notes, False)
    out.append("Run the same check locally: `python3 .github/format-check/format_check.py --base origin/main`")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="git ref to diff against (default: scan everything with --all)")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--all", action="store_true", help="check every plugin under community/ and featured/")
    ap.add_argument("--actor", default=os.environ.get("FORMAT_CHECK_ACTOR", ""), help="GitHub login of the PR author")
    ap.add_argument("--json", help="write the report as JSON here")
    ap.add_argument("--markdown", help="write the Markdown summary here")
    ap.add_argument("--annotations", action="store_true", help="print GitHub workflow annotations")
    args = ap.parse_args()

    rep = Report()
    if args.all or not args.base:
        files = all_plugin_files()
        plugins = {"/".join(f.split("/")[:2]) for f in files if f.split("/")[0] in PLUGIN_ROOTS and f.count("/") >= 2}
    else:
        files = changed_files(args.base, args.head)
        plugins = check_repo_level(files, args.actor, rep)
        check_dco(args.base, args.head, rep)
    rep.plugins = sorted(plugins)
    for name in rep.plugins:
        check_plugin(name, rep)
    check_manifest(rep)

    md = markdown(rep)
    if args.annotations:
        annotations(rep)
    if args.json:
        Path(args.json).write_text(json.dumps({"failed": rep.failed, "plugins": rep.plugins,
                                               "findings": [asdict(f) for f in rep.findings]}, indent=2))
    if args.markdown:
        Path(args.markdown).write_text(md)
    print(md)
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
