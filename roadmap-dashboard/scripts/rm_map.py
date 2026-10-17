"""rm_map: scan skills, agents, memory, project code and git into .claude/roadmap/map.json.

  map    write map.json (districts, nodes, relations); prints one summary line

Nothing here opens the .env file: the secret node is made from os.path.exists only.
Every read is capped (frontmatter 2-8 KB, mention scan only for files <= 64 KB).
"""
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import rm_data
from rm_data import Err, rd

MAX_TEXT = 64 * 1024
REL_CAP = 200
HUES = {"teal", "gold", "blue", "green", "coral", "slate", "purple"}
DISTRICTS = [
    ("skills-global", "Global skills", "Reusable skills in the home folder, shared by every project.", "teal"),
    ("skills-project", "Project skills", "Skills that live in this repo and travel with it.", "green"),
    ("memory", "Memory and state", "Resume notes and the durable project state notes.", "gold"),
    ("agents", "Agents", "Subagent definitions with their model and effort.", "purple"),
    ("code", "Project code", "The primary source packages, one tile per package.", "blue"),
    ("scripts", "Scripts", "High-level project support scripts (setup, smoke test).", "slate"),
    ("repo", "Repo and git", "Manifest, project file and the secrets marker. Branches are in the Git activity tab.", "coral"),
]


def slugify(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


# ---------------------------------------------------------------- small helpers
def read_head(path, n):
    try:
        with open(path, "rb") as f:
            return f.read(n).decode("utf-8", "replace")
    except OSError:
        return ""


def iso(path):
    try:
        t = os.stat(path).st_mtime
    except OSError:
        return None
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def size(path):
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def retired(path):
    return "retired" in Path(path).parts


def frontmatter(text):
    """(dict of simple keys, body) from a leading --- block. Folded/literal values are joined."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    block = text[4:end] if end > 0 else text[4:]
    body = text[end + 4:] if end > 0 else ""
    out, key = {}, None
    for line in block.split("\n"):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, val = m.group(1), m.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    for k, v in list(out.items()):
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            out[k] = v[1:-1]
    return out, body


def clip(s, n=200):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."


def first_line(body):
    for line in body.split("\n"):
        t = line.strip()
        if t and t != "---":
            return re.sub(r"^[#>*\-\s]+", "", t).strip()
    return ""


def describe(path):
    fm, body = frontmatter(read_head(path, 8192))
    return clip(fm.get("description") or first_line(body)), fm


class Ctx:
    def __init__(self, home, project):
        self.home = Path(home).resolve()
        self.project = Path(project).resolve()
        self.nodes = {}
        self.src = {}   # node id -> Path of the text file scanned for mentions
        self.rel = []

    def tp(self, p):
        """Display path: ~/... for the home folder, repo-relative otherwise; never an absolute path."""
        p = Path(p)
        try:
            return "~/" + p.resolve().relative_to(self.home.parent).as_posix()
        except ValueError:
            pass
        try:
            return p.resolve().relative_to(self.project).as_posix()
        except ValueError:
            return p.name

    def add(self, nid, district, kind, name, path=None, desc="", src=None, stat=True, **extra):
        n = {"id": nid, "district": district, "kind": kind, "name": name}
        if path is not None:
            n["path"] = self.tp(path)
            if stat and Path(path).is_file():
                n["bytes"] = size(path)
                n["modified"] = iso(path)
        n["desc"] = clip(desc)
        n["children"] = extra.get("children", [])
        n["links"] = extra.get("links", [])
        n["meta"] = extra.get("meta", {})
        self.nodes[nid] = n
        if src is not None:
            self.src[nid] = Path(src)
        return n


def files_under(d):
    out = []
    if Path(d).is_dir():
        for p in sorted(Path(d).rglob("*")):
            if p.is_file() and not retired(p) and "__pycache__" not in p.parts:
                out.append(p)
    return out


# ---------------------------------------------------------------- scanners
def scan_skills(ctx, root, district, prefix):
    root = Path(root)
    if not root.is_dir():
        return
    for d in sorted(root.iterdir()):
        sk = d / "SKILL.md"
        if not d.is_dir() or retired(d) or not sk.is_file():
            continue
        desc, fm = describe(sk)
        kids = []
        for sub in ("references", "scripts"):
            for f in files_under(d / sub):
                kids.append({"name": f.relative_to(d).as_posix(), "path": ctx.tp(f), "bytes": size(f)})
        assets = len(files_under(d / "assets"))
        ctx.add(f"{prefix}:{d.name}", district, "skill", d.name, sk, desc, src=sk,
                children=kids, meta={"assets": assets})


def scan_memory(ctx):
    mem = ctx.home / "projects" / slugify(ctx.project) / "memory"
    for f in sorted(mem.glob("*.md")) if mem.is_dir() else []:
        # detail notes in memory/<prefix>/ are listed as children of the <prefix>_*.md summary note
        sub = mem / f.stem.split("_", 1)[0]
        kids = [{"name": c.name, "path": ctx.tp(c), "bytes": size(c)}
                for c in sorted(sub.glob("*.md"))] if "_" in f.stem and sub.is_dir() else []
        extra = {"children": kids} if kids else {}
        ctx.add(f"memory:{f.name}", "memory", "memory", f.name, f, describe(f)[0], src=f, **extra)
    st = ctx.project / ".claude" / "state"
    for f in sorted(st.glob("*.md")) if st.is_dir() else []:
        ctx.add(f"state:{f.name}", "memory", "state", f.name, f, describe(f)[0], src=f)


def scan_agents(ctx):
    d = ctx.home / "agents"
    for f in sorted(d.glob("*.md")) if d.is_dir() else []:
        desc, fm = describe(f)
        meta = {k: fm.get(k, "") for k in ("model", "effort")}
        ctx.add(f"agent:{f.stem}", "agents", "agent", fm.get("name") or f.stem, f, desc, src=f, meta=meta)


def load_code_config(project):
    """Optional per-project declaration of where the primary code lives: roadmap/map-groups.json,
    {"code": {"root": "packages/ttPy", "packages": [{"name": "backtest", "desc": "..."}, ...]}}.
    `root` is required (repo-relative); `packages` entries are optional per-package descriptions,
    matched by folder name. Nothing is shown if this isn't declared -- there's no generic way to
    guess a project's primary source directory."""
    f = rd(project) / "map-groups.json"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    code = cfg.get("code") if isinstance(cfg, dict) else None
    if not isinstance(code, dict) or not code.get("root"):
        return None
    descs = {p.get("name"): p.get("desc", "") for p in code.get("packages", []) if isinstance(p, dict) and p.get("name")}
    return {"root": str(code["root"]), "descs": descs}


def scan_code(ctx):
    """One node per immediate sub-package (a directory with __init__.py) of the declared root --
    package level only, primary source code only. No files, no tests, no tooling. Size and modified
    date are the package's own aggregate (summed / latest across its .py files), and its file list
    is shown as children, same as a skill's references/scripts list."""
    cfg = load_code_config(ctx.project)
    if not cfg:
        return
    root = ctx.project / cfg["root"]
    if not root.is_dir():
        return
    for d in sorted(root.iterdir()):
        if not d.is_dir() or retired(d) or d.name.startswith("__") or d.name.endswith(".egg-info"):
            continue
        if not (d / "__init__.py").is_file():
            continue
        pyfiles = [f for f in files_under(d) if f.suffix == ".py"]
        kids = [{"name": f.relative_to(d).as_posix(), "path": ctx.tp(f), "bytes": size(f)} for f in pyfiles]
        n = ctx.add(f"pkg:{d.name}", "code", "package", d.name, d, cfg["descs"].get(d.name, ""),
                    stat=False, meta={"files": len(pyfiles)}, children=kids)
        n["bytes"] = sum(size(f) for f in pyfiles)
        mtimes = [m for m in (iso(f) for f in pyfiles) if m]
        if mtimes:
            n["modified"] = max(mtimes)


def scan_scripts_bat(ctx):
    d = ctx.project / ".setup"
    for f in sorted(d.glob("*.bat")) if d.is_dir() else []:
        ctx.add(f"script:.setup/{f.name}", "scripts", "script", f.name, f, "Setup script", src=f)


def git(ctx, *args):
    try:
        r = subprocess.run(["git", "-C", str(ctx.project), *args], capture_output=True, text=True,
                           encoding="utf-8", timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def scan_repo(ctx, man, use_git):
    mf = ctx.project / ".claude" / "project-manifest.json"
    if mf.is_file():
        ctx.add("manifest:project", "repo", "manifest", "project-manifest.json", mf,
                "Repo manifest: declares dashboards, skills, agents and environment", src=mf)
    py = ctx.project / "pyproject.toml"
    if py.is_file():
        ctx.add("manifest:pyproject", "repo", "manifest", "pyproject.toml", py, "Python project definition", src=py)
    if os.path.exists(ctx.project / ".env"):  # existence only, never opened
        ctx.add("secret:env", "repo", "secret", ".env", ".env", "Never read", stat=False)
        ctx.nodes["secret:env"]["path"] = ".env"


# ---------------------------------------------------------------- groups
MEMORY_GROUPS = [("index", "Memory: index"), ("feedback", "Memory: guidance"), ("project", "Memory: project"),
                 ("user", "Memory: about you"), ("reference", "Memory: references")]


def load_state_groups(project):
    """Optional per-project grouping of the state notes: roadmap/map-groups.json,
    {"state": [{"name": "State: rules", "files": ["operating-rules.md", "f*-*.md"]}, ...]}."""
    f = rd(project) / "map-groups.json"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for g in cfg.get("state", []) if isinstance(cfg, dict) else []:
        if isinstance(g, dict) and g.get("name") and isinstance(g.get("files"), list):
            out.append((str(g["name"]), [str(x) for x in g["files"]]))
    return out


def assign_groups(ctx):
    """Give each node a `group` (a subheading inside its district) and `gorder` (its position there).
    Districts whose nodes have no group are drawn flat."""
    state = load_state_groups(ctx.project)
    for n in ctx.nodes.values():
        k, name = n["kind"], n["name"]
        if k == "memory":
            key = "index" if name == "MEMORY.md" else name.split("_", 1)[0].lower()
            for i, (pre, label) in enumerate(MEMORY_GROUPS):
                if key == pre:
                    n["group"], n["gorder"] = label, 10 + i
                    break
            else:
                n["group"], n["gorder"] = "Memory: other", 19
        elif k == "state":
            for i, (label, pats) in enumerate(state):
                if any(fnmatch.fnmatch(name, p) for p in pats):
                    n["group"], n["gorder"] = label, 20 + i
                    break
            else:
                n["group"], n["gorder"] = ("State: other" if state else "State: notes"), 40

# ---------------------------------------------------------------- relations
def declares(ctx, man):
    if "manifest:project" not in ctx.nodes:
        return
    want = []
    sk = man.get("skills", {}) or {}
    want += [f"skill:{s}" for s in sk.get("global", [])]
    want += [f"pskill:{s}" for s in sk.get("project", [])]
    want += [f"agent:{a}" for a in (man.get("agents", {}) or {}).get("global", [])]
    for t in want:
        if t in ctx.nodes:
            ctx.rel.append({"from": "manifest:project", "to": t, "kind": "declares"})


def mentions(ctx):
    toks = {}
    for nid, n in ctx.nodes.items():
        if n["kind"] in ("secret", "package"):
            continue
        cands = {n["name"].rstrip("/")}
        if n.get("path"):
            cands.add(n["path"].rsplit("/", 1)[-1])
        cands.discard("SKILL.md")
        for c in cands:
            if len(c) >= 4:
                toks.setdefault(c, set()).add(nid)
    toks = {t: next(iter(v)) for t, v in toks.items() if len(v) == 1}
    if not toks:
        return []
    pat = re.compile(r"(?<![A-Za-z0-9_-])(" + "|".join(re.escape(t) for t in sorted(toks, key=len, reverse=True))
                     + r")(?![A-Za-z0-9_-])")
    found = set()
    for nid, p in sorted(ctx.src.items()):
        if size(p) > MAX_TEXT:
            continue
        for m in pat.findall(read_head(p, MAX_TEXT)):
            if toks[m] != nid:
                found.add((nid, toks[m]))
    return [{"from": a, "to": b, "kind": "mentions"} for a, b in sorted(found)]


def finish_relations(ctx):
    rels, seen = [], set()
    for r in ctx.rel + mentions(ctx):
        key = (r["from"], r["to"], r["kind"])
        if r["from"] == r["to"] or key in seen or r["from"] not in ctx.nodes or r["to"] not in ctx.nodes:
            continue
        seen.add(key)
        rels.append(r)
    return rels[:REL_CAP]


# ---------------------------------------------------------------- build
def build(home, project, use_git=True):
    ctx = Ctx(home, project)
    man = {}
    mf = ctx.project / ".claude" / "project-manifest.json"
    if mf.is_file() and size(mf) <= MAX_TEXT:
        try:
            man = json.loads(read_head(mf, MAX_TEXT))
        except json.JSONDecodeError:
            man = {}
    scan_skills(ctx, ctx.home / "skills", "skills-global", "skill")
    scan_skills(ctx, ctx.project / ".claude" / "skills", "skills-project", "pskill")
    scan_memory(ctx)
    scan_agents(ctx)
    scan_code(ctx)
    scan_scripts_bat(ctx)
    scan_repo(ctx, man, use_git)
    assign_groups(ctx)
    declares(ctx, man)
    rels = finish_relations(ctx)
    nodes = sorted(ctx.nodes.values(), key=lambda n: (n["district"], n["id"]))
    for n in nodes:
        n.setdefault("modified", None)
        if n["modified"] is None:
            del n["modified"]
    return {
        "schema": 1,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "project": man.get("project") or ctx.project.name,
        "districts": [{"id": i, "name": n, "blurb": b, "order": k + 1, "hue": h}
                      for k, (i, n, b, h) in enumerate(DISTRICTS)],
        "nodes": nodes,
        "relations": rels,
    }


def summary(m):
    counts = {}
    for n in m["nodes"]:
        counts[n["district"]] = counts.get(n["district"], 0) + 1
    per = ", ".join(f"{d['id']} {counts.get(d['id'], 0)}" for d in m["districts"])
    return f"ok map {len(m['nodes'])} nodes ({per}), {len(m['relations'])} relations"


def cmd_map(args, project):
    m = build(Path.home() / ".claude", project)
    rm_data.write_json(rd(project) / "map.json", m)
    print(summary(m))


def refresh(project):
    cmd_map(None, project)


def register(sub):
    p = sub.add_parser("map", help="scan skills, agents, memory, project code and git into map.json")
    p.set_defaults(func=cmd_map)


# ---------------------------------------------------------------- selftest
def selftest():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        home, proj = t / "home" / ".claude", t / "proj"
        sk = home / "skills" / "demo-skill"
        (sk / "references").mkdir(parents=True)
        (sk / "scripts").mkdir()
        (sk / "assets").mkdir()
        (sk / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo skill text\n---\nBody\n", encoding="utf-8")
        (sk / "references" / "guide.md").write_text("see helper_tool.py", encoding="utf-8")
        (sk / "scripts" / "helper_tool.py").write_text("print(1)\n", encoding="utf-8")
        (sk / "assets" / "a.png").write_bytes(b"x")
        (home / "skills" / "retired" / "old-skill").mkdir(parents=True)
        (home / "skills" / "retired" / "old-skill" / "SKILL.md").write_text("---\nname: old\n---\n", encoding="utf-8")
        (home / "agents").mkdir()
        (home / "agents" / "bot-agent.md").write_text(
            "---\nname: bot-agent\ndescription: Does demo-skill work\nmodel: sonnet\neffort: high\n---\nx\n", encoding="utf-8")
        proj.mkdir(parents=True)
        mem = home / "projects" / slugify(proj.resolve()) / "memory"
        mem.mkdir(parents=True)
        (mem / "note.md").write_text("# Resume note\ntext\n", encoding="utf-8")
        (proj / ".claude").mkdir()
        (proj / ".claude" / "project-manifest.json").write_text(
            json.dumps({"project": "demo", "skills": {"global": ["demo-skill"]}, "agents": {"global": ["bot-agent"]}}),
            encoding="utf-8")
        (proj / ".env").write_text("API_KEY=TOPSECRETVALUE\n", encoding="utf-8")
        (proj / "pkgs" / "widget").mkdir(parents=True)
        (proj / "pkgs" / "widget" / "__init__.py").write_text("", encoding="utf-8")
        (proj / "pkgs" / "widget" / "core.py").write_text("x = 1\n", encoding="utf-8")
        (proj / "pkgs" / "not_a_package").mkdir()  # no __init__.py: excluded
        (proj / "pkgs" / "not_a_package" / "loose.py").write_text("x = 1\n", encoding="utf-8")
        (proj / ".claude" / "roadmap").mkdir(parents=True)
        (proj / ".claude" / "roadmap" / "map-groups.json").write_text(
            json.dumps({"code": {"root": "pkgs", "packages": [{"name": "widget", "desc": "Widget package"}]}}),
            encoding="utf-8")
        (proj / ".setup").mkdir()
        (proj / ".setup" / "setup.bat").write_text("echo hi\n", encoding="utf-8")
        m = build(home, proj, use_git=False)
        ids = {n["id"]: n for n in m["nodes"]}
        assert "skill:demo-skill" in ids and "agent:bot-agent" in ids and "memory:note.md" in ids, ids.keys()
        assert "skill:old-skill" not in ids and not any("retired" in i for i in ids), "retired not excluded"
        assert ids["skill:demo-skill"]["meta"]["assets"] == 1 and len(ids["skill:demo-skill"]["children"]) == 2
        assert not any(n["kind"] == "script" and n["district"] == "skills-global" for n in m["nodes"]), \
            "skill scripts should not appear in the map"
        assert ids["agent:bot-agent"]["meta"] == {"model": "sonnet", "effort": "high"}
        assert ids["memory:note.md"]["desc"] == "Resume note"
        assert ids["memory:note.md"]["group"] == "Memory: other" and ids["agent:bot-agent"].get("group") is None, ids
        assert "pkg:widget" in ids and ids["pkg:widget"]["district"] == "code" and ids["pkg:widget"]["kind"] == "package"
        pw = ids["pkg:widget"]
        assert pw["desc"] == "Widget package" and pw["meta"]["files"] == 2, pw
        assert pw["bytes"] > 0 and len(pw["children"]) == 2, pw  # __init__.py (empty) + core.py
        assert "pkg:not_a_package" not in ids, "a folder without __init__.py is not a package"
        assert ids["script:.setup/setup.bat"]["district"] == "scripts", ids.get("script:.setup/setup.bat")
        env = ids["secret:env"]
        assert env["desc"] == "Never read" and "bytes" not in env and "modified" not in env, env
        for r in m["relations"]:
            assert r["from"] in ids and r["to"] in ids and r["from"] != r["to"], r
        kinds = {(r["from"], r["to"], r["kind"]) for r in m["relations"]}
        assert ("manifest:project", "skill:demo-skill", "declares") in kinds, kinds
        assert ("agent:bot-agent", "skill:demo-skill", "mentions") in kinds, kinds
        assert not any(r["to"] == "pkg:widget" or r["from"] == "pkg:widget" for r in m["relations"]), \
            "package nodes should not participate in mentions"
        blob = json.dumps(m)
        for bad in (str(t), t.as_posix(), "TOPSECRETVALUE", "C:\\\\Users", "C:/Users"):
            assert bad not in blob, f"leak: {bad}"
        assert ids["skill:demo-skill"]["path"].startswith("~/"), ids["skill:demo-skill"]["path"]
        assert not any(n["kind"] == "branch" for n in m["nodes"]) and not any(r["kind"] == "based-on" for r in m["relations"])
        assert all(d["hue"] in HUES for d in m["districts"])
    print("selftest ok (rm_map)")
