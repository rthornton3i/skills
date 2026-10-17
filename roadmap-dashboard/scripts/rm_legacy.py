"""rm_legacy: one-time migration of the old single-file roadmap HTML into the schema-1 data files.

  migrate-legacy --html FILE [--force]   build plan.json, plan-archive.json, tabs.json,
                                         archive/story-logs.jsonl, archive/legacy/legacy-story-usage.json
  migrate-legacy --verify [--html FILE]  reload the legacy HTML and prove nothing was lost

The legacy HTML is only read. The data is pulled out of it by extract_legacy.js (node).
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import rm_data
from rm_data import Err, rd

LEGACY_DIR = "roadmap/archive/legacy"   # under the project agent folder (.agent, or .claude when that is what the project uses)
STORY_KEYS = ("agent", "critic", "loop", "escalated", "obe", "completed")
CHIP_KEYS = ("name", "initials", "model", "modelLabel", "role")
TABS = {"title": "Project Roadmap",
        "subtitle": "Phases, features and stories. Click a phase to focus, or a story for details.",
        "tabs": [
            {"id": "plan", "title": "Plan", "script": "tab-plan.js",
             "data": {"plan": "plan.json", "tokens": "tokens.json"}, "lazy": {"archive": "plan-archive.json"}},
            {"id": "map", "title": "Project map", "script": "tab-map.js", "data": {"map": "map.json"}},
            {"id": "git", "title": "Git activity", "script": "tab-git.js", "data": {"git": "git.json"}}]}


def extract(html_path):
    node = shutil.which("node")
    if not node:
        raise Err("node is required for migrate-legacy but was not found on PATH")
    js = Path(__file__).resolve().parent / "extract_legacy.js"
    r = subprocess.run([node, str(js), str(html_path)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise Err("extract_legacy.js failed: " + (r.stderr.strip() or f"exit {r.returncode}"))
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise Err(f"extract_legacy.js output does not parse: {e}")
    for k in ("phases", "agents", "features", "stories", "storyDetails", "storyUsage"):
        if k not in data:
            raise Err(f"legacy data has no {k}")
    return data


# ---------------------------------------------------------------- outcome
def cut200(text):
    """Text cut at a sentence boundary to at most 200 characters (whole text if it already fits)."""
    t = " ".join((text or "").split())
    if len(t) <= 200:
        return t
    win = t[:200]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", win)]
    if ends and ends[-1] >= 40:
        return win[:ends[-1]].strip()
    win = t[:197]
    sp = win.rfind(" ")
    return (win[:sp] if sp > 40 else win).rstrip(" ,;:") + "..."


def first_sentence(text):
    t = " ".join((text or "").split())
    m = re.match(r".*?[.!?](?=\s|$)", t)
    return cut200(m.group(0) if m else t)


SKIP_LOG = ("Review", "Approver", "Orchestrator final approval")


def derive_outcome(story, det):
    """First sentence of desc (<= 200); else the last log entry that is not a review/approval verdict;
    else the obe text; else the story name."""
    if (det.get("desc") or "").strip():
        return first_sentence(det["desc"])
    for e in reversed(det.get("log") or []):
        w = (e.get("what") or "").strip()
        if w and not w.startswith(SKIP_LOG):
            return cut200(w)
    if story.get("obe"):
        return "Closed without being built."
    return story["name"]


def norm_details(det):
    return {"desc": det.get("desc", ""), "criteria": det.get("criteria", []),
            "log": det.get("log", []), "notes": det.get("notes", "")}


def default_html(project):
    """The single *.html in <agent folder>/roadmap/archive/legacy/; more or fewer than one needs --html."""
    base = Path(project)
    agent = base / ".agent" if (base / ".agent").is_dir() else base / ".claude"
    found = sorted((agent / LEGACY_DIR).glob("*.html"))
    if len(found) != 1:
        raise Err(f"expected exactly one legacy page in {agent / LEGACY_DIR}, found {len(found)}; pass --html")
    return found[0]


# ---------------------------------------------------------------- migrate
def cmd_migrate(args, project):
    if args.verify:
        return verify(args, project)
    d = rd(project)
    html = Path(args.html) if args.html else default_html(project)
    if not html.is_absolute():
        html = Path(project) / html if not html.exists() else html.resolve()
    if not html.exists():
        raise Err(f"{html} not found")
    if (d / "plan.json").exists() and not args.force:
        raise Err("plan.json already exists; migrate-legacy is one-time (use --force to rebuild it)")
    data = extract(html)

    plan = rm_data.empty_plan(Path(project).resolve().name)
    arch = rm_data.empty_archive()
    plan["phases"] = [{"id": p["id"], "name": p["name"]} for p in data["phases"]]
    plan["features"] = [{"id": f["id"], "phase": f["phase"], "name": f["name"]} for f in data["features"]]
    plan["agents"] = {k: {c: a[c] for c in CHIP_KEYS if a.get(c) not in (None, "")} for k, a in data["agents"].items()}

    logs = d / "archive" / "story-logs.jsonl"
    logs.parent.mkdir(parents=True, exist_ok=True)
    logs.write_text("", encoding="utf-8")
    n_done = 0
    for s in data["stories"]:
        det = norm_details(data["storyDetails"].get(s["id"]) or {})
        st = {"id": s["id"], "feature": s["feature"], "name": s["name"], "status": s["status"]}
        for k in STORY_KEYS:
            if s.get(k) not in (None, ""):
                st[k] = s[k]
        if s["status"] == "done":
            st["outcome"] = derive_outcome(st, det)
            st["details"] = det
            rm_data.append_jsonl(logs, rm_data.log_row(st, "legacy-html", True))
            del st["details"]
            n_done += 1
        else:
            st["details"] = det
        plan["stories"].append(st)

    moved = rm_data.do_sweep(project, plan, arch)
    files = rm_data.save(project, plan, arch, ["archive/story-logs.jsonl"])
    rm_data.write_json(d / "tabs.json", TABS)
    rm_data.write_json(d / "archive" / "legacy" / "legacy-story-usage.json", data["storyUsage"])
    files += ["tabs.json", "archive/legacy/legacy-story-usage.json"]
    c = plan["counts"]
    rm_data.ok(f"migrate-legacy {len(data['stories'])} stories ({len(plan['stories'])} active, {len(arch['stories'])} archived, "
               f"{n_done} log rows), plan.json {(d / 'plan.json').stat().st_size} B, "
               f"plan-archive.json {(d / 'plan-archive.json').stat().st_size} B; overall {c['overall']['done']}/"
               f"{c['overall']['total']}" + rm_data.moved_text(moved), files)


# ---------------------------------------------------------------- verify
def verify(args, project):
    d = rd(project)
    html = Path(args.html) if args.html else default_html(project)
    data = extract(html)
    plan, arch = rm_data.load(project)
    bad = []

    def chk(cond, msg):
        if not cond and len(bad) < 15:
            bad.append(msg)

    logs = [r for r in rm_data.read_jsonl(d / "archive" / "story-logs.jsonl")
            if r.get("source") == "legacy-html" and "log_entry" not in r]
    log_by = {}
    for r in logs:
        chk(r["id"] not in log_by, f"story {r['id']} has two legacy log rows")
        log_by[r["id"]] = r
    where = {}
    for s in plan["stories"]:
        chk(s["id"] not in where, f"story {s['id']} appears twice")
        where[s["id"]] = ("plan", s)
    for s in arch["stories"]:
        chk(s["id"] not in where, f"story {s['id']} appears twice")
        where[s["id"]] = ("archive", s)

    legacy_ids = [s["id"] for s in data["stories"]]
    chk(sorted(where) == sorted(legacy_ids), "story id sets differ: extra "
        f"{sorted(set(where) - set(legacy_ids))}, missing {sorted(set(legacy_ids) - set(where))}")
    n_details = 0
    for s in data["stories"]:
        sid = s["id"]
        if sid not in where:
            continue
        loc, new = where[sid]
        for k in ("name", "feature"):
            chk(new.get(k) == s.get(k), f"{sid} {k}: {s.get(k)!r} != {new.get(k)!r}")
        new_status = "done" if loc == "archive" else new.get("status")
        chk(new_status == s["status"], f"{sid} status: {s['status']!r} != {new_status!r}")
        for k in ("agent", "critic", "loop", "completed", "obe", "escalated"):
            chk(new.get(k) == (s.get(k) if s.get(k) not in (None, "") else None), f"{sid} {k}: {s.get(k)!r} != {new.get(k)!r}")
        old = data["storyDetails"].get(sid) or {}
        if any(old.get(k) for k in ("desc", "criteria", "log", "notes")):
            n_details += 1
        holder = log_by.get(sid) if s["status"] == "done" else new.get("details", {})
        chk(holder is not None, f"{sid} has no details record")
        if holder is None:
            continue
        for k, empty in (("desc", ""), ("criteria", []), ("log", []), ("notes", "")):
            chk(holder.get(k, empty) == old.get(k, empty), f"{sid} detail {k} differs")
        if s["status"] == "done":
            chk(bool(log_by[sid].get("outcome")) and bool(new.get("outcome")), f"{sid} has no outcome")
    allph = {p["id"]: p["name"] for p in plan["phases"] + arch["phases"]}
    chk(allph == {p["id"]: p["name"] for p in data["phases"]}, "phase lists differ")
    allft = {f["id"]: (f["phase"], f["name"]) for f in plan["features"] + arch["features"]}
    chk(allft == {f["id"]: (f["phase"], f["name"]) for f in data["features"]}, "feature lists differ")
    chk(set(plan["agents"]) == set(data["agents"]), "agent id sets differ: "
        f"{sorted(set(plan['agents']) ^ set(data['agents']))}")
    for k, a in data["agents"].items():
        chip = plan["agents"].get(k, {})
        for c in CHIP_KEYS:
            chk(chip.get(c) == a.get(c), f"agent {k} {c}: {a.get(c)!r} != {chip.get(c)!r}")
    if bad:
        for b in bad:
            print("error: " + b, file=sys.stderr)
        raise Err(f"verify failed: {len(bad)} problem(s) (first shown)")
    print(f"verify ok: {len(legacy_ids)} stories ({len(plan['stories'])} active, {len(arch['stories'])} archived), "
          f"{len(data['phases'])} phases, {len(data['features'])} features, {n_details} details, {len(data['agents'])} agents")


def register(sub):
    p = sub.add_parser("migrate-legacy", help="one-time migration of the old roadmap HTML (or --verify it)")
    p.add_argument("--html", help="legacy page (default: the single *.html in <agent folder>/roadmap/archive/legacy/)")
    p.add_argument("--verify", action="store_true", help="prove the migration lost nothing")
    p.add_argument("--force", action="store_true", help="rebuild even if plan.json exists")
    p.set_defaults(func=cmd_migrate)


# ---------------------------------------------------------------- selftest
def selftest():
    if not shutil.which("node"):
        return
    assert cut200("Short one.") == "Short one."
    long = ("A" * 60 + ". ") + ("B" * 60 + ". ") + ("C" * 60 + ". ") + "D" * 60
    assert cut200(long) == ("A" * 60 + ". ") + ("B" * 60 + ". ") + ("C" * 60 + "."), cut200(long)
    assert first_sentence("One two. Three.") == "One two."
    assert derive_outcome({"name": "n", "obe": True}, {}) == "Closed without being built."
    assert derive_outcome({"name": "n"}, {"desc": "Did it. More."}) == "Did it."
    assert derive_outcome({"name": "n"}, {"desc": "", "log": [{"when": "a", "what": "Last words."}, {"when": "b", "what": "Review PASS."}]}) == "Last words."
    assert len(cut200("word " * 100)) <= 200 and cut200("word " * 100).endswith("...")
    tmp = Path(tempfile.mkdtemp(prefix="rm_legacy_selftest_"))
    try:
        proj = tmp / "proj"
        (rd(proj)).mkdir(parents=True)
        html = tmp / "legacy.html"
        html.write_text(
            "<html><script>\r\n(function(){\r\n /* header mentions RENDER ENGINE marker */\r\n"
            "const phases=[{id:'m1',name:'P1'},{id:'m2',name:'P2'}];\r\n"
            "const agents={'claude':{name:'Orc',initials:'OR',model:'a',modelLabel:'S',role:'Orchestrator',status:'idle',current:null}};\r\n"
            "const features=[{id:'f1',phase:'m1',name:'F1'},{id:'f2',phase:'m2',name:'F2'}];\r\n"
            "const stories=[{id:'s1',feature:'f1',name:'One',status:'done',agent:'claude',completed:'2026-01-01'},\r\n"
            "{id:'s2',feature:'f2',name:'Two',status:'not-started'}];\r\n"
            "const storyDetails={s1:{desc:'Did one. Fine.',criteria:[{t:'c',done:true}],log:[{when:'Jan 1',what:'Shipped.'}]}};\r\n"
            "const storyUsage={generated:'x',stories:{},total:{},unattributed:{}};\r\n"
            "/* ===========\r\n     RENDER ENGINE - below\r\n   =========== */\r\n document.body;\r\n})();</script></html>",
            encoding="utf-8", newline="")
        import argparse
        ap = argparse.ArgumentParser()
        sp = ap.add_subparsers(dest="cmd", required=True)
        register(sp)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            a = ap.parse_args(["migrate-legacy", "--html", str(html)])
            a.func(a, proj)
            a = ap.parse_args(["migrate-legacy", "--verify", "--html", str(html)])
            a.func(a, proj)
        assert "verify ok: 2 stories (1 active, 1 archived), 2 phases, 2 features, 1 details, 1 agents" in out.getvalue(), out.getvalue()
        plan, arch = rm_data.load(proj)
        assert [p["id"] for p in arch["phases"]] == ["m1"] and plan["stories"][0]["id"] == "s2"
        assert arch["stories"][0]["outcome"] == "Did one."
        assert "status" not in plan["agents"]["claude"]
        try:
            a = ap.parse_args(["migrate-legacy", "--html", str(html)])
            a.func(a, proj)
        except Err:
            pass
        else:
            raise AssertionError("second migrate should refuse without --force")
        plan["stories"][0]["name"] = "Changed"
        rm_data.save(proj, plan, arch)
        try:
            a = ap.parse_args(["migrate-legacy", "--verify", "--html", str(html)])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                a.func(a, proj)
        except Err:
            pass
        else:
            raise AssertionError("verify should fail after a change")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
