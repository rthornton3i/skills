"""rm_data: schema-1 data model for the roadmap dashboard (plan.json, plan-archive.json,
archive/story-logs.jsonl, ledger/events.jsonl) and the story/plan commands.

Pure standard library. Command functions are func(args, project) and print ONE line
"ok <what> [files]" on success; failures raise Err (roadmap.py prints it to stderr, exit 1).
"""
import argparse
import builtins
import contextlib
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ["not-started", "planning", "plan-review", "progress", "review", "approval", "done"]
STORY_TYPES = ["story", "bug"]
POINTS_SCALE = {1, 2, 3, 5, 8, 13, 21}
SHELL_FILES = ["index.html", "styles.css", "app.js", "tabs.json", "tab-plan.js", "tab-map.js", "tab-git.js"]
DATA_FILES = ["plan.json", "tokens.json", "plan-archive.json", "map.json", "git.json", "activity.json"]
ID_RE = {"story": re.compile(r"^s\d+$"), "feature": re.compile(r"^f\d+$"), "phase": re.compile(r"^m\d+$")}
PREFIX = {"story": "s", "feature": "f", "phase": "m"}


class Err(Exception):
    pass


# ---------------------------------------------------------------- paths and io
def rd(project):
    return Path(project) / ".claude" / "roadmap"


def dumps(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def write_json(path, o):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(o) + "\n")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise Err(f"{path.name} not found")
    except json.JSONDecodeError as e:
        raise Err(f"{path.name} does not parse: {e}")


def append_jsonl(path, row, compact=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = dumps(row) if compact else json.dumps(row, ensure_ascii=False)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                raise Err(f"{path.name} line {n} does not parse")
    return rows


def now_ts():
    d = datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def now_minute():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def today_iso():
    return datetime.now().strftime("%Y-%m-%d")


def today_short():
    d = datetime.now()
    return d.strftime("%b ") + str(d.day)


# ---------------------------------------------------------------- load / save
def empty_plan(project_name="project"):
    return {"schema": 1, "project": project_name, "generated": now_minute(), "phases": [],
            "features": [], "stories": [], "agents": {}, "counts": {}}


def empty_archive():
    return {"schema": 1, "phases": [], "features": [], "stories": []}


def load(project):
    d = rd(project)
    plan = read_json(d / "plan.json")
    if plan.get("schema") != 1:
        raise Err("plan.json schema is not 1")
    arch = read_json(d / "plan-archive.json") if (d / "plan-archive.json").exists() else empty_archive()
    for k in ("phases", "features", "stories"):
        plan.setdefault(k, [])
        arch.setdefault(k, [])
    plan.setdefault("agents", {})
    return plan, arch


def compute_counts(plan, arch):
    feat_phase = {f["id"]: f["phase"] for f in arch["features"] + plan["features"]}
    phases = {p["id"]: {"done": 0, "total": 0} for p in plan["phases"]}
    done = total = 0
    for s in plan["stories"]:
        total += 1
        is_done = s.get("status") == "done"
        done += is_done
        ph = feat_phase.get(s["feature"])
        if ph in phases:
            phases[ph]["total"] += 1
            phases[ph]["done"] += is_done
    for s in arch["stories"]:
        total += 1
        done += 1
        ph = feat_phase.get(s["feature"])
        if ph in phases:
            phases[ph]["total"] += 1
            phases[ph]["done"] += 1
    return {"overall": {"done": done, "total": total}, "archivedPhases": len(arch["phases"]),
            "phases": phases}


def problems(plan, arch):
    out = []

    def uniq(kind, items):
        seen = set()
        for it in items:
            i = it.get("id")
            if not i or not ID_RE[kind].match(i):
                out.append(f"bad {kind} id: {i!r}")
            elif i in seen:
                out.append(f"duplicate {kind} id {i}")
            seen.add(i)
        return seen

    ph = uniq("phase", plan["phases"] + arch["phases"])
    ft = uniq("feature", plan["features"] + arch["features"])
    uniq("story", plan["stories"] + arch["stories"])
    aph = {p["id"] for p in arch["phases"]}
    pph = {p["id"] for p in plan["phases"]}
    pft = {f["id"] for f in plan["features"]}
    aft = {f["id"] for f in arch["features"]}
    for f in plan["features"]:
        if f.get("phase") not in pph:
            out.append(f"feature {f['id']} phase {f.get('phase')} is not an active phase")
    for f in arch["features"]:
        if f.get("phase") not in aph:
            out.append(f"archived feature {f['id']} phase {f.get('phase')} is not an archived phase")
    for s in plan["stories"]:
        if s.get("feature") not in pft:
            out.append(f"story {s['id']} feature {s.get('feature')} is not an active feature")
        if s.get("status") not in STATUSES:
            out.append(f"story {s['id']} has bad status {s.get('status')!r}")
        if s.get("status") == "done" and "details" in s:
            out.append(f"story {s['id']} is done but still has details")
        if not s.get("name"):
            out.append(f"story {s['id']} has no name")
    for s in arch["stories"]:
        if s.get("feature") not in aft:
            out.append(f"archived story {s['id']} feature {s.get('feature')} is not archived")
    if pph & aph:
        out.append("phase ids in both plan and archive: " + ",".join(sorted(pph & aph)))
    if pft & aft:
        out.append("feature ids in both plan and archive: " + ",".join(sorted(pft & aft)))
    for f in plan["features"] + arch["features"]:
        if "points" in f and f["points"] not in POINTS_SCALE:
            out.append(f"feature {f['id']} has bad points {f['points']!r}")
        if "estTokens" in f and (not isinstance(f["estTokens"], int) or isinstance(f["estTokens"], bool)
                                  or f["estTokens"] < 0):
            out.append(f"feature {f['id']} has bad estTokens {f['estTokens']!r}")
    return out


def save(project, plan, arch, extra=()):
    """Revalidate, recompute counts, write plan.json and plan-archive.json. Returns file names."""
    bad = problems(plan, arch)
    if bad:
        raise Err("refusing to write, invalid data: " + "; ".join(bad[:5]))
    plan["counts"] = compute_counts(plan, arch)
    plan["generated"] = now_minute()
    d = rd(project)
    write_json(d / "plan.json", plan)
    write_json(d / "plan-archive.json", arch)
    return ["plan.json", "plan-archive.json"] + list(extra)


def find_story(plan, arch, sid):
    for s in plan["stories"]:
        if s["id"] == sid:
            return s, "plan"
    for s in arch["stories"]:
        if s["id"] == sid:
            return s, "archive"
    raise Err(f"story {sid} not found")


def active_story(plan, sid):
    for s in plan["stories"]:
        if s["id"] == sid:
            return s
    raise Err(f"story {sid} not found in the active plan")


def active_feature(plan, fid):
    for f in plan["features"]:
        if f["id"] == fid:
            return f
    raise Err(f"feature {fid} not found in the active plan")


def next_id(plan, arch, kind):
    key = {"story": "stories", "feature": "features", "phase": "phases"}[kind]
    p = PREFIX[kind]
    nums = [int(i["id"][1:]) for i in plan[key] + arch[key] if ID_RE[kind].match(i["id"])]
    return f"{p}{max(nums, default=0) + 1}"


def pick_id(plan, arch, kind, given):
    if not given:
        return next_id(plan, arch, kind)
    if not ID_RE[kind].match(given):
        raise Err(f"bad {kind} id {given!r} (expected {PREFIX[kind]}<number>)")
    key = {"story": "stories", "feature": "features", "phase": "phases"}[kind]
    if any(i["id"] == given for i in plan[key] + arch[key]):
        raise Err(f"{kind} id {given} already exists")
    return given


def log_row(story, source, archived):
    d = story.get("details") or {}
    row = {"id": story["id"], "feature": story["feature"], "name": story["name"], "status": "done"}
    for k in ("agent", "critic", "loop", "escalated", "obe", "completed", "outcome", "type"):
        if story.get(k) not in (None, ""):
            row[k] = story[k]
    row.update({"desc": d.get("desc", ""), "criteria": d.get("criteria", []), "log": d.get("log", []),
                "notes": d.get("notes", ""), "archived": today_iso(), "source": source})
    return row


def light_row(story):
    row = {"id": story["id"], "feature": story["feature"], "name": story["name"]}
    for k in ("agent", "critic", "loop", "escalated", "obe", "completed", "outcome", "type"):
        if story.get(k) not in (None, ""):
            row[k] = story[k]
    return row


def do_sweep(project, plan, arch):
    """Move finished phases (every story done) with their features and stories to the archive.
    Nothing moves at feature level."""
    moved = {"phases": []}
    d = rd(project)
    for p in list(plan["phases"]):
        fids = {f["id"] for f in plan["features"] if f["phase"] == p["id"]}
        ss = [s for s in plan["stories"] if s["feature"] in fids]
        if not ss or not all(s.get("status") == "done" for s in ss):
            continue
        if any(not any(s["feature"] == fid for s in ss) for fid in fids):
            continue  # a feature with no stories yet keeps the phase open
        dates = [s["completed"] for s in ss if s.get("completed")]
        for s in ss:
            if s.get("details"):  # should not happen; keep the detail in the log
                append_jsonl(d / "archive" / "story-logs.jsonl", log_row(s, "close-story", True))
            arch["stories"].append(light_row(s))
            plan["stories"].remove(s)
        for f in [f for f in plan["features"] if f["id"] in fids]:
            row = dict(f)
            row["completed"] = max([s["completed"] for s in ss if s["feature"] == f["id"]
                                     and s.get("completed")], default=max(dates, default=today_iso()))
            arch["features"].append(row)
            plan["features"].remove(f)
        arch["phases"].append({"id": p["id"], "name": p["name"], "completed": max(dates, default=today_iso())})
        plan["phases"].remove(p)
        moved["phases"].append(p["id"])
    return moved


def do_reopen(plan, arch, pid):
    """Move an archived phase, its features and stories back into the active plan."""
    ph = [p for p in arch["phases"] if p["id"] == pid]
    if not ph:
        raise Err(f"phase {pid} is not archived")
    arch["phases"].remove(ph[0])
    plan["phases"].append({"id": pid, "name": ph[0]["name"]})
    fids = {f["id"] for f in arch["features"] if f["phase"] == pid}
    for f in [f for f in arch["features"] if f["id"] in fids]:
        arch["features"].remove(f)
        row = dict(f)
        row.pop("completed", None)
        row["phase"] = pid
        plan["features"].append(row)
    for s in [s for s in arch["stories"] if s["feature"] in fids]:
        arch["stories"].remove(s)
        plan["stories"].append(dict(s, status="done"))


def moved_text(m):
    return "; moved phases " + ",".join(m["phases"]) if m["phases"] else ""


def ok(what, files=()):
    print("ok " + what + (" [" + " ".join(files) + "]" if files else ""))


# ---------------------------------------------------------------- read commands
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_since_publish(project):
    d = rd(project)
    pub = d / "ledger" / "published.json"
    names = SHELL_FILES + DATA_FILES
    if not pub.exists():
        return None
    try:
        old = json.loads(pub.read_text(encoding="utf-8")).get("files", {})
    except Exception:
        return None
    return [n for n in names if (d / n).exists() and old.get(n) != sha(d / n)]


def age(path):
    if not path.exists():
        return "none"
    secs = datetime.now().timestamp() - path.stat().st_mtime
    return f"{secs / 3600:.1f} h old" if secs < 172800 else f"{secs / 86400:.0f} d old"


def unpublished_line(project, changed):
    """One status line: status events since the last publish and which published files differ."""
    pub = rd(project) / "ledger" / "published.json"
    try:
        at = str(json.loads(pub.read_text(encoding="utf-8")).get("at", ""))
    except Exception:
        return "unpublished: never published"
    if changed is None:
        return "unpublished: never published"
    n = sum(1 for e in read_jsonl(rd(project) / "ledger" / "events.jsonl")
            if str(e.get("ts", ""))[:16] > at[:16])
    if not n and not changed:
        return f"published {at}, up to date"
    return f"unpublished: {n} status events since {at} (changed files: {', '.join(changed) or 'none'})"


def cmd_status(args, project):
    plan, arch = load(project)
    c = compute_counts(plan, arch)
    o = c["overall"]
    header = (f"{plan.get('project', '')} plan {plan.get('generated', '')}: {o['done']}/{o['total']} stories done; "
              f"archived {c['archivedPhases']} phases")
    if getattr(args, "short", False):
        open_s = [s for s in plan["stories"] if s.get("status") not in ("done", "not-started")]
        line2 = "open: " + ("; ".join(f"{s['id']} {s['status']} {s.get('agent', '-')} {s['name'][:40]}"
                                       for s in open_s) if open_s else "none")
        ch = changed_since_publish(project)
        if ch is None:
            line3 = "publish: never published"
        elif ch:
            line3 = "publish: changed " + ", ".join(ch)
        else:
            line3 = "publish: up to date"
        print("\n".join([header, line2, line3]))
        return
    L = [header]
    for p in plan["phases"]:
        pc = c["phases"][p["id"]]
        L.append(f"phase {p['id']} {p['name']}: {pc['done']}/{pc['total']}")
    open_s = [s for s in plan["stories"] if s.get("status") not in ("done", "not-started")]
    L.append("open stories: " + ("none" if not open_s else ""))
    for s in open_s:
        L.append(f"  {s['id']} {s['status']} {s.get('agent', '-')} {s['name'][:50]}")
    nxt = []
    for f in plan["features"]:
        for s in plan["stories"]:
            if s["feature"] == f["id"] and s.get("status") == "not-started":
                nxt.append(f"  {f['id']}: {s['id']} {s['name'][:55]}")
                break
    if nxt:
        L.append("next not-started per feature:")
        L += nxt
    ch = changed_since_publish(project)
    L.append("publish: never published" if ch is None else
             "publish: " + (("changed " + ",".join(ch)) if ch else "up to date"))
    L.append(unpublished_line(project, ch))
    tk = rd(project) / "tokens.json"
    if tk.exists():
        try:
            L.append(f"tokens: {json.loads(tk.read_text(encoding='utf-8')).get('total', 0):,} fresh ({age(tk)})")
        except Exception:
            L.append("tokens: tokens.json unreadable")
    else:
        L.append("tokens: none yet")
    L.append("git.json: " + age(rd(project) / "git.json"))
    if len(L) > 26:
        L = L[:25] + [f"... {len(L) - 25} more lines cut"]
    print("\n".join(L))


def cmd_show(args, project):
    plan, arch = load(project)
    s, where = find_story(plan, arch, args.story)
    out = {"where": where, **s}
    rows = [r for r in read_jsonl(rd(project) / "archive" / "story-logs.jsonl") if r.get("id") == s["id"]]
    base = [r for r in rows if "log_entry" not in r]
    if base:
        out["archived_record"] = base[-1]
    extra = [dict(r["log_entry"], ts=r.get("ts")) for r in rows if "log_entry" in r]
    if extra:
        out["later_log"] = extra
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_next_ids(args, project):
    plan, arch = load(project)
    print(f"story {next_id(plan, arch, 'story')} feature {next_id(plan, arch, 'feature')} "
          f"phase {next_id(plan, arch, 'phase')}")


def cmd_validate(args, project):
    plan, arch = load(project)
    bad = problems(plan, arch)
    if bad:
        for b in bad:
            print("error: " + b, file=sys.stderr)
        raise Err(f"{len(bad)} problem(s)")
    d = rd(project)
    missing = [n for n in SHELL_FILES if not (d / n).exists()]
    for n in ("events.jsonl",):
        read_jsonl(d / "ledger" / n)
    read_jsonl(d / "archive" / "story-logs.jsonl")
    ok(f"validate {len(plan['stories'])} active + {len(arch['stories'])} archived stories" +
       (f"; warn shell files missing: {','.join(missing)}" if missing else ""))


# ---------------------------------------------------------------- write commands
def event_agent(state, agent, critic):
    """The agent to record on a status event: --critic for plan-review and review, otherwise --agent."""
    who = critic if state in ("plan-review", "review") else agent
    return who or None


def agent_hint(state, who):
    if state in ("planning", "progress") and not who:
        print(f"hint: no agent recorded for '{state}'; pass --agent so the Execution flow can name who did it")


def cmd_set_status(args, project):
    if args.status not in STATUSES:
        raise Err(f"unknown status {args.status!r}; use one of {', '.join(STATUSES)}")
    if args.status == "done":
        raise Err("use close-story to finish a story (it needs an outcome)")
    plan, arch = load(project)
    s = active_story(plan, args.story)
    if s.get("status") == "done":
        raise Err(f"story {args.story} is already done")
    s["status"] = args.status
    for k in ("agent", "critic", "loop", "escalated"):
        v = getattr(args, k)
        if v is not None:
            if v == "":
                s.pop(k, None)
            else:
                s[k] = v
    files = save(project, plan, arch, ["ledger/events.jsonl"])
    ev = {"ts": now_ts(), "story": args.story, "state": args.status, "note": args.note or ""}
    who = event_agent(args.status, args.agent, args.critic)
    if who:
        ev["agent"] = who
    append_jsonl(rd(project) / "ledger" / "events.jsonl", ev, compact=False)
    ok(f"set-status {args.story} {args.status}", files)
    agent_hint(args.status, who)


def cmd_set_story(args, project):
    plan, arch = load(project)
    s = active_story(plan, args.story)
    n = 0
    if args.name is not None:
        s["name"] = args.name
        n += 1
    if getattr(args, "type", None) is not None:
        if args.type == "story":
            s.pop("type", None)
        else:
            s["type"] = args.type
        n += 1
    for k in ("agent", "critic", "loop", "escalated"):
        v = getattr(args, k)
        if v is not None:
            n += 1
            if v == "":
                s.pop(k, None)
            else:
                s[k] = v
    for k in ("desc", "notes"):
        v = getattr(args, k)
        if v is not None:
            if "details" not in s:
                raise Err(f"story {args.story} has no details (it is done); use log or set-outcome")
            s["details"][k] = v
            n += 1
    if not n:
        raise Err("nothing to change; pass at least one option")
    ok(f"set-story {args.story}", save(project, plan, arch))


def cmd_set_feature(args, project):
    plan, arch = load(project)
    f = active_feature(plan, args.feature)
    n = 0
    if args.points is not None:
        if args.points == "":
            f.pop("points", None)
        else:
            try:
                pts = int(args.points)
            except ValueError:
                raise Err(f"--points must be an integer, got {args.points!r}")
            if pts not in POINTS_SCALE:
                raise Err(f"--points must be one of {sorted(POINTS_SCALE)}, got {pts}")
            f["points"] = pts
        n += 1
    if args.est_tokens is not None:
        if args.est_tokens == "":
            f.pop("estTokens", None)
        else:
            try:
                est = int(args.est_tokens)
            except ValueError:
                raise Err(f"--estTokens must be a non-negative integer, got {args.est_tokens!r}")
            if est < 0:
                raise Err(f"--estTokens must be a non-negative integer, got {est}")
            f["estTokens"] = est
        n += 1
    if not n:
        raise Err("nothing to change; pass --points and/or --estTokens")
    ok(f"set-feature {args.feature}", save(project, plan, arch))


def cmd_add_phase(args, project):
    plan, arch = load(project)
    if args.name.strip().lower().startswith("side track"):
        for p in plan["phases"] + arch["phases"]:
            if p["name"].strip().lower().startswith("side track"):
                raise Err(f"a Side track phase exists ({p['id']}): add a feature with add-feature --phase {p['id']} instead")
    i = pick_id(plan, arch, "phase", args.id)
    plan["phases"].append({"id": i, "name": args.name})
    ok(f"add-phase {i}", save(project, plan, arch))


def cmd_add_feature(args, project):
    plan, arch = load(project)
    reopened = any(p["id"] == args.phase for p in arch["phases"])
    if reopened:
        do_reopen(plan, arch, args.phase)
    if not any(p["id"] == args.phase for p in plan["phases"]):
        raise Err(f"phase {args.phase} not found")
    i = pick_id(plan, arch, "feature", args.id)
    plan["features"].append({"id": i, "phase": args.phase, "name": args.name})
    ok(f"add-feature {i}" + (f" (reopened phase {args.phase})" if reopened else ""), save(project, plan, arch))


def cmd_reopen_phase(args, project):
    plan, arch = load(project)
    do_reopen(plan, arch, args.phase)
    ok(f"reopen-phase {args.phase}", save(project, plan, arch))


def cmd_add_story(args, project):
    plan, arch = load(project)
    for f in arch["features"]:
        if f["id"] == args.feature:
            raise Err(f"feature {args.feature} is in archived phase {f['phase']}; use add-feature --phase "
                      f"{f['phase']} (reopens it) or reopen-phase {f['phase']}")
    if not any(f["id"] == args.feature for f in plan["features"]):
        raise Err(f"feature {args.feature} not found")
    i = pick_id(plan, arch, "story", args.id)
    crit = [{"t": t.strip(), "done": False} for t in (args.criteria or "").split("|") if t.strip()]
    story = {"id": i, "feature": args.feature, "name": args.name, "status": "not-started",
             "details": {"desc": args.desc or "", "criteria": crit, "log": [], "notes": ""}}
    if args.type and args.type != "story":
        story["type"] = args.type
    plan["stories"].append(story)
    ok(f"add-story {i}" + (f" ({args.type})" if story.get("type") else ""), save(project, plan, arch))


def cmd_log(args, project):
    plan, arch = load(project)
    s, where = find_story(plan, arch, args.story)
    when = args.when or today_short()
    if where == "plan" and s.get("status") != "done" and "details" in s:
        s["details"].setdefault("log", []).append({"when": when, "what": args.text})
        ok(f"log {args.story}", save(project, plan, arch))
    else:
        append_jsonl(rd(project) / "archive" / "story-logs.jsonl",
                     {"id": args.story, "ts": now_ts(), "log_entry": {"when": when, "what": args.text}})
        ok(f"log {args.story} (archived story)", ["archive/story-logs.jsonl"])


def cmd_criterion(args, project):
    plan, arch = load(project)
    s = active_story(plan, args.story)
    if "details" not in s:
        raise Err(f"story {args.story} has no details (it is done)")
    crit = s["details"].setdefault("criteria", [])
    if args.action == "add":
        crit.append({"t": args.text, "done": False})
    else:
        if args.text.isdigit():
            idx = int(args.text) - 1  # 1-based
            if not 0 <= idx < len(crit):
                raise Err(f"criterion index {args.text} out of range (1..{len(crit)})")
        else:
            m = [k for k, c in enumerate(crit) if c["t"].lower() == args.text.lower()]
            if not m:
                raise Err(f"no criterion with text {args.text!r}")
            idx = m[0]
        crit[idx]["done"] = True
    ok(f"criterion {args.story} {args.action}", save(project, plan, arch))


def cmd_agent_chip(args, project):
    plan, arch = load(project)
    chip = {"name": args.name, "initials": args.initials, "model": args.model, "modelLabel": args.label}
    if args.role:
        chip["role"] = args.role
    plan["agents"][args.id] = chip
    ok(f"agent-chip {args.id}", save(project, plan, arch))


def cmd_event(args, project):
    if args.state not in STATUSES:
        raise Err(f"unknown state {args.state!r}; use one of {', '.join(STATUSES)}")
    ev = {"ts": now_ts(), "story": args.story, "state": args.state, "note": args.note or ""}
    if getattr(args, "agent", None):
        ev["agent"] = args.agent
    append_jsonl(rd(project) / "ledger" / "events.jsonl", ev, compact=False)
    ok(f"event {args.story} {args.state}", ["ledger/events.jsonl"])
    agent_hint(args.state, ev.get("agent"))


def cmd_close_story(args, project):
    if not (args.outcome or "").strip():
        raise Err("--outcome is required")
    if args.date and not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
        raise Err("--date must be YYYY-MM-DD")
    plan, arch = load(project)
    s = active_story(plan, args.story)
    if s.get("status") == "done":
        raise Err(f"story {args.story} is already done")
    s["status"] = "done"
    s["completed"] = args.date or today_iso()
    s["outcome"] = args.outcome
    if args.obe:
        s["obe"] = True
    append_jsonl(rd(project) / "archive" / "story-logs.jsonl", log_row(s, "close-story", False))
    s.pop("details", None)
    append_jsonl(rd(project) / "ledger" / "events.jsonl",
                 {"ts": now_ts(), "story": args.story, "state": "done", "note": args.outcome}, compact=False)
    m = do_sweep(project, plan, arch)
    files = save(project, plan, arch, ["archive/story-logs.jsonl", "ledger/events.jsonl"])
    ok(f"close-story {args.story}" + moved_text(m), files)


def cmd_start(args, project):
    ns = argparse.Namespace(story=args.story, status="progress", agent=args.agent, critic=None,
                             loop=None, escalated=None, note=args.note)
    cmd_set_status(ns, project)


def find_next_story(plan, feature):
    """The first open (non-done, non-not-started) story, else the first not-started story of `feature`."""
    for s in plan["stories"]:
        if s.get("status") not in ("done", "not-started"):
            return s
    for s in plan["stories"]:
        if s["feature"] == feature and s.get("status") == "not-started":
            return s
    return None


def cmd_done(args, project):
    plan, arch = load(project)
    s = active_story(plan, args.story)
    if s.get("status") == "done":
        raise Err(f"story {args.story} is already done")
    feature = s["feature"]
    with contextlib.redirect_stdout(io.StringIO()):
        if args.agent is not None or args.critic is not None:
            cmd_set_story(argparse.Namespace(story=args.story, name=None, agent=args.agent, critic=args.critic,
                                              loop=None, escalated=None, desc=None, notes=None), project)
        if args.log:
            cmd_log(argparse.Namespace(story=args.story, text=args.log, when=None), project)
    cmd_close_story(argparse.Namespace(story=args.story, outcome=args.outcome, obe=args.obe, date=args.date), project)
    if args.publish:
        try:
            import rm_publish
        except ModuleNotFoundError as e:
            if e.name != "rm_publish":
                raise
            print("publish: rm_publish not built yet")
        else:
            rm_publish.cmd_refresh(argparse.Namespace(cmd="refresh"), project)
            rm_publish.cmd_publish_args(argparse.Namespace(cmd="publish-args", all=False), project)
    else:
        plan2, arch2 = load(project)
        nxt = find_next_story(plan2, feature)
        print("next: none" if nxt is None else f"next: {nxt['id']} {nxt['status']} {nxt['name'][:48]}")


def cmd_sweep(args, project):
    plan, arch = load(project)
    m = do_sweep(project, plan, arch)
    ok("sweep" + (moved_text(m) if any(m.values()) else "; nothing to move"), save(project, plan, arch))


def cmd_set_outcome(args, project):
    plan, arch = load(project)
    s, where = find_story(plan, arch, args.story)
    s["outcome"] = args.text
    ok(f"set-outcome {args.story}", save(project, plan, arch))


def cmd_rename(args, project):
    plan, arch = load(project)
    key = {"phase": "phases", "feature": "features", "story": "stories"}[args.kind]
    for coll in (plan[key], arch[key]):
        for it in coll:
            if it["id"] == args.id:
                it["name"] = args.name
                ok(f"rename {args.kind} {args.id}", save(project, plan, arch))
                return
    raise Err(f"{args.kind} {args.id} not found")


# ---------------------------------------------------------------- registry
def register(sub):
    def add(name, func, help_=""):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=func)
        return p

    p = add("status", cmd_status, "short project status")
    p.add_argument("--short", action="store_true", help="3 lines only: header, open stories, publish state")
    p = add("show", cmd_show, "show one story"); p.add_argument("story")
    add("next-ids", cmd_next_ids, "next free s/f/m ids")
    add("validate", cmd_validate, "check plan integrity")
    p = add("set-status", cmd_set_status, "set a story status (not done)")
    p.add_argument("story"); p.add_argument("status")
    for k in ("agent", "critic", "loop", "escalated", "note"):
        p.add_argument("--" + k)
    p = add("set-story", cmd_set_story, "edit story fields")
    p.add_argument("story")
    for k in ("name", "agent", "critic", "loop", "escalated", "desc", "notes"):
        p.add_argument("--" + k)
    p.add_argument("--type", choices=STORY_TYPES, help="story or bug")
    p = add("set-feature", cmd_set_feature, "set feature points/estTokens")
    p.add_argument("feature"); p.add_argument("--points"); p.add_argument("--estTokens", dest="est_tokens")
    p = add("add-phase", cmd_add_phase); p.add_argument("--name", required=True); p.add_argument("--id")
    p = add("add-feature", cmd_add_feature)
    p.add_argument("--phase", required=True); p.add_argument("--name", required=True); p.add_argument("--id")
    p = add("add-story", cmd_add_story)
    p.add_argument("--feature", required=True); p.add_argument("--name", required=True)
    p.add_argument("--id"); p.add_argument("--desc"); p.add_argument("--criteria", help='"a|b|c"')
    p.add_argument("--type", choices=STORY_TYPES, default="story", help="bug marks a defect fix (shows a BUG chip)")
    p = add("log", cmd_log, "append a log line")
    p.add_argument("story"); p.add_argument("text"); p.add_argument("--when")
    p = add("criterion", cmd_criterion, "add a criterion or tick one (index is 1-based)")
    p.add_argument("story"); p.add_argument("action", choices=["add", "done"]); p.add_argument("text")
    p = add("agent-chip", cmd_agent_chip)
    p.add_argument("id"); p.add_argument("--name", required=True); p.add_argument("--initials", required=True)
    p.add_argument("--model", required=True, choices=["a", "b", "c"]); p.add_argument("--label", required=True)
    p.add_argument("--role")
    p = add("event", cmd_event, "append a ledger event")
    p.add_argument("story"); p.add_argument("state"); p.add_argument("--note"); p.add_argument("--agent")
    p = add("close-story", cmd_close_story)
    p.add_argument("story"); p.add_argument("--outcome", required=True)
    p.add_argument("--obe", action="store_true"); p.add_argument("--date")
    p = add("start", cmd_start, "shorthand: set-status <story> progress --agent ID --note TXT")
    p.add_argument("story"); p.add_argument("--agent"); p.add_argument("--note")
    p = add("done", cmd_done, "close-story in one call: optional set-story/log first, optional refresh+publish-args after")
    p.add_argument("story"); p.add_argument("--outcome", required=True)
    p.add_argument("--agent"); p.add_argument("--critic"); p.add_argument("--obe", action="store_true")
    p.add_argument("--date"); p.add_argument("--log"); p.add_argument("--publish", action="store_true")
    add("sweep", cmd_sweep, "move finished phases (every story done) to the archive")
    p = add("reopen-phase", cmd_reopen_phase, "move an archived phase back into the plan"); p.add_argument("phase")
    p = add("set-outcome", cmd_set_outcome); p.add_argument("story"); p.add_argument("text")
    p = add("rename", cmd_rename, "rename a phase, feature or story")
    p.add_argument("kind", choices=["phase", "feature", "story"]); p.add_argument("id"); p.add_argument("name")


# ---------------------------------------------------------------- selftest
def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="rm_selftest_"))
    try:
        proj = tmp / "proj"
        (rd(proj) / "ledger").mkdir(parents=True)
        save(proj, empty_plan("selftest"), empty_archive())
        ap = argparse.ArgumentParser()
        sub = ap.add_subparsers(dest="cmd", required=True)
        register(sub)

        def run(*argv, fail=False):
            buf = io.StringIO()
            try:
                a = ap.parse_args(list(argv))
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                    a.func(a, proj)
            except (Err, SystemExit) as e:
                if not fail:
                    raise AssertionError(f"{argv} failed: {e}")
                return str(e)
            if fail:
                raise AssertionError(f"{argv} should have failed")
            return buf.getvalue()

        def check(c, msg):
            if not c:
                raise AssertionError(msg)

        run("add-phase", "--name", "P one")
        run("add-phase", "--name", "P two")
        run("add-feature", "--phase", "m1", "--name", "F one")
        run("add-feature", "--phase", "m1", "--name", "F two")
        run("add-feature", "--phase", "m2", "--name", "F three")
        check(run("next-ids").strip() == "story s1 feature f4 phase m3", "next-ids")
        run("add-story", "--feature", "f1", "--name", "S one", "--criteria", "a|b")
        run("add-story", "--feature", "f1", "--name", "S two")
        run("add-story", "--feature", "f2", "--name", "S three", "--id", "s10")
        run("add-story", "--feature", "f3", "--name", "S four")
        run("add-story", "--feature", "f9", "--name", "bad", fail=True)
        run("add-story", "--feature", "f1", "--name", "dup", "--id", "s1", fail=True)
        run("set-story", "s2", "--type", "bug")
        check('"type": "bug"' in run("show", "s2"), "set-story --type bug stores it")
        run("set-story", "s2", "--type", "story")
        check('"type"' not in run("show", "s2"), "set-story --type story clears it")
        run("add-story", "--feature", "f1", "--name", "bad type", "--type", "chore", fail=True)
        run("agent-chip", "implementer-1", "--name", "Impl-1", "--initials", "I1", "--model", "b", "--label", "Sonnet")
        run("criterion", "s1", "add", "c")
        run("criterion", "s1", "done", "2")
        run("criterion", "s1", "done", "c")
        run("criterion", "s1", "done", "9", fail=True)
        run("log", "s1", "did a thing", "--when", "Sep 21")
        for st in ("planning", "plan-review", "progress", "review", "approval"):
            run("set-status", "s1", st, "--agent", "implementer-1", "--note", "walk")
        run("set-status", "s1", "done", fail=True)
        run("set-status", "s1", "bogus", fail=True)
        run("set-status", "s99", "progress", fail=True)
        evs = read_jsonl(rd(proj) / "ledger" / "events.jsonl")
        check([e["state"] for e in evs] == ["planning", "plan-review", "progress", "review", "approval"], "events")
        check([e.get("agent") for e in evs] == ["implementer-1", None, "implementer-1", None, "implementer-1"],
              "set-status writes --agent on worker stages, --critic on plan-review and review: " + repr(evs))
        run("set-status", "s1", "review", "--agent", "a-x", "--critic", "crit-1")
        run("event", "s1", "progress", "--agent", "ev-agent")
        run("set-status", "s1", "approval")
        evs = read_jsonl(rd(proj) / "ledger" / "events.jsonl")
        check(evs[-3].get("agent") == "crit-1" and evs[-2].get("agent") == "ev-agent", "critic on review; event --agent")
        check("hint: no agent" in run("event", "s1", "planning"), "hint for a worker stage without an agent")
        check("agent" not in read_jsonl(rd(proj) / "ledger" / "events.jsonl")[-1], "no agent key when none given")
        run("set-story", "s2", "--name", "S two b", "--desc", "d", "--notes", "n", "--loop", "1 / 2")
        run("rename", "story", "s2", "S two c")
        run("event", "s2", "progress", "--note", "x")
        check("approval" in run("show", "s1"), "show")
        st = run("status")
        check(len(st.splitlines()) <= 26, "status length")
        check("unpublished: never published" in st, "status never published")
        (rd(proj) / "ledger" / "published.json").write_text(
            json.dumps({"url": "u", "at": "2000-01-01T00:00Z", "files": {"plan.json": "0"}}), encoding="utf-8")
        st = run("status")
        check("unpublished: " in st and "status events since 2000-01-01T00:00Z (changed files: plan.json, plan-archive.json)" in st, "status unpublished")
        (rd(proj) / "ledger" / "published.json").write_text(
            json.dumps({"url": "u", "at": "2999-01-01T00:00Z", "files": {n: sha(rd(proj) / n) for n in ("plan.json", "plan-archive.json")}}), encoding="utf-8")
        check("published 2999-01-01T00:00Z, up to date" in run("status"), "status up to date")
        (rd(proj) / "ledger" / "published.json").unlink()

        run("close-story", "s1", "--outcome", "", fail=True)
        out = run("close-story", "s1", "--outcome", "First done", "--date", "2026-01-02")
        check(out.startswith("ok close-story s1") and out.count("\n") == 1, "close-story one line")
        plan, arch = load(proj)
        s1 = [s for s in plan["stories"] if s["id"] == "s1"][0]
        check(s1["status"] == "done" and "details" not in s1 and s1["completed"] == "2026-01-02", "s1 closed")
        check(plan["counts"]["overall"] == {"done": 1, "total": 4}, "counts after s1")
        rows = read_jsonl(rd(proj) / "archive" / "story-logs.jsonl")
        check(rows[-1]["id"] == "s1" and rows[-1]["criteria"] and rows[-1]["log"], "story log row")
        run("log", "s1", "late note")
        check("log_entry" in read_jsonl(rd(proj) / "archive" / "story-logs.jsonl")[-1], "log_entry row")
        check("First done" in run("show", "s1"), "show closed")
        run("close-story", "s1", "--outcome", "again", fail=True)
        run("set-status", "s1", "progress", fail=True)
        out = run("close-story", "s2", "--outcome", "Second")
        check("moved" not in out, "f1 done but its phase is not: " + out)
        plan, arch = load(proj)
        check(not arch["phases"] and not arch["features"] and not arch["stories"], "nothing archived yet")
        check([f["id"] for f in plan["features"]] == ["f1", "f2", "f3"] and len(plan["stories"]) == 4, "f1 stays in plan")
        check(plan["counts"]["overall"] == {"done": 2, "total": 4}, "counts after f1")
        check(plan["counts"]["phases"]["m1"] == {"done": 2, "total": 3}, "phase m1 counts")
        check("archivedFeatures" not in plan["counts"], "no archivedFeatures")
        run("add-story", "--feature", "f1", "--name", "extra on done feature")
        run("close-story", "s12", "--outcome", "Extra")
        run("rename", "feature", "f1", "F one renamed")
        out = run("close-story", "s10", "--outcome", "Third", "--obe")
        check("moved phases m1" in out, "phase m1 archived: " + out)
        plan, arch = load(proj)
        check([p["id"] for p in arch["phases"]] == ["m1"] and plan["counts"]["archivedPhases"] == 1, "phase m1 archived")
        check([f["id"] for f in arch["features"]] == ["f1", "f2"] and len(arch["stories"]) == 4, "whole phase archived")
        check("m1" not in plan["counts"]["phases"], "m1 gone from active counts")
        check(any(s.get("obe") for s in arch["stories"]), "obe kept")
        check("archived phase m1" in run("add-story", "--feature", "f1", "--name", "late", fail=True), "archived-feature refusal")
        run("set-outcome", "s10", "Third b")
        run("validate")
        check("nothing to move" in run("sweep"), "sweep idempotent")
        run("add-phase", "--name", "Side track")
        check("a Side track phase exists (m3)" in run("add-phase", "--name", "side track - X", fail=True), "side track guard")
        out = run("add-feature", "--phase", "m1", "--name", "New feature")
        check("(reopened phase m1)" in out, "reopen on add-feature: " + out)
        plan, arch = load(proj)
        check("m1" in [p["id"] for p in plan["phases"]] and not arch["features"] and len(plan["stories"]) >= 4, "m1 reopened")
        check(all(s["status"] == "done" for s in plan["stories"] if s["feature"] in ("f1", "f2")), "reopened stories done")
        check("nothing to move" in run("sweep") and "m1" in [p["id"] for p in load(proj)[0]["phases"]], "empty feature keeps phase open")
        check(plan["counts"]["phases"]["m1"] == {"done": 4, "total": 4}, "reopened counts")
        run("add-story", "--feature", "f4", "--name", "on new feature")
        run("close-story", "s11", "--outcome", "Fourth")
        plan, arch = load(proj)
        check(sorted(p["id"] for p in plan["phases"]) == ["m1", "m3"] and [p["id"] for p in arch["phases"]] == ["m2"], "m2 archived")
        run("close-story", "s13", "--outcome", "Fifth")
        check([p["id"] for p in load(proj)[1]["phases"]] == ["m2", "m1"], "m1 archives once the new feature is done")
        run("reopen-phase", "m2")
        run("reopen-phase", "m2", fail=True)
        run("validate")

        # set-feature: points/estTokens set, validated, and survive archive/reopen (do_sweep/do_reopen fix)
        out = run("add-phase", "--name", "P feat-test")
        pid_ft = out.split()[2]
        out = run("add-feature", "--phase", pid_ft, "--name", "F feat-test")
        fid_ft = out.split()[2]
        run("set-feature", "f9999", "--points", "3", fail=True)
        run("set-feature", fid_ft, "--points", "7", fail=True)
        run("set-feature", fid_ft, "--estTokens", "-5", fail=True)
        run("set-feature", fid_ft, fail=True)
        out = run("set-feature", fid_ft, "--points", "8", "--estTokens", "12345")
        check(out.startswith(f"ok set-feature {fid_ft}"), "set-feature ok: " + out)
        plan, arch = load(proj)
        check(active_feature(plan, fid_ft).get("points") == 8 and active_feature(plan, fid_ft).get("estTokens") == 12345,
              "set-feature applied")
        out = run("add-story", "--feature", fid_ft, "--name", "S feat-test")
        sid_ft = out.split()[2]
        run("start", sid_ft, "--agent", "impl-ft")
        run("done", sid_ft, "--outcome", "feat-test story done")
        plan, arch = load(proj)
        check(fid_ft not in [f["id"] for f in plan["features"]], "feature archived with its phase")
        af = [f for f in arch["features"] if f["id"] == fid_ft][0]
        check(af.get("points") == 8 and af.get("estTokens") == 12345,
              "archived feature keeps points/estTokens (do_sweep fix)")
        check(pid_ft in [p["id"] for p in arch["phases"]], "phase feat-test archived")
        run("reopen-phase", pid_ft)
        plan, arch = load(proj)
        rf = active_feature(plan, fid_ft)
        check(rf.get("points") == 8 and rf.get("estTokens") == 12345,
              "reopened feature keeps points/estTokens (do_reopen fix)")
        run("set-feature", fid_ft, "--points", "", "--estTokens", "")
        plan, arch = load(proj)
        check("points" not in active_feature(plan, fid_ft) and "estTokens" not in active_feature(plan, fid_ft),
              "set-feature clears with empty string")
        run("validate")

        # bug stories: type is stored on add and reported
        out = run("add-story", "--feature", fid_ft, "--name", "S bugtype", "--type", "bug")
        check("(bug)" in out, "add-story --type bug reports it")
        check('"type": "bug"' in run("show", out.split()[2]), "add-story --type bug stores it")

        # status --short: exactly 3 lines
        st = run("status", "--short")
        lines = st.rstrip("\n").split("\n")
        check(len(lines) == 3, "status --short 3 lines: " + repr(lines))
        check(lines[1].startswith("open:") and lines[2].startswith("publish:"), "status --short shape: " + repr(lines))

        # start: shorthand for set-status progress --agent
        out = run("add-phase", "--name", "P done-test")
        pid = out.split()[2]
        out = run("add-feature", "--phase", pid, "--name", "F done-test")
        fid = out.split()[2]
        out = run("add-story", "--feature", fid, "--name", "S alpha")
        sid_a = out.split()[2]
        out = run("add-story", "--feature", fid, "--name", "S beta")
        sid_b = out.split()[2]
        out = run("start", sid_a, "--agent", "impl-done", "--note", "starting")
        check(out.startswith(f"ok set-status {sid_a} progress"), "start sets progress: " + out)
        plan, arch = load(proj)
        check(active_story(plan, sid_a)["agent"] == "impl-done", "start set agent")

        # done: set-story + log + close-story in one call, with the next: line
        out = run("done", sid_a, "--outcome", "Alpha done", "--agent", "impl-done2", "--log", "wrapped up")
        dlines = out.rstrip("\n").split("\n")
        check(dlines[0].startswith(f"ok close-story {sid_a}"), "done ok line: " + out)
        check(len(dlines) == 2 and dlines[1] == f"next: {sid_b} not-started S beta", "done next line: " + out)
        plan, arch = load(proj)
        s_a = active_story(plan, sid_a)
        check(s_a.get("agent") == "impl-done2" and s_a["status"] == "done", "done applied set-story before closing")
        rows = read_jsonl(rd(proj) / "archive" / "story-logs.jsonl")
        check(any(r.get("id") == sid_a and r.get("log") and r["log"][-1]["what"] == "wrapped up" for r in rows),
              "done applied log before closing")

        # done refuses an already-done story
        check("already done" in run("done", sid_a, "--outcome", "again", fail=True), "done refuses already-done")

        # done: clean error for a story that does not exist
        run("done", "s999", "--outcome", "x", fail=True)

        # done --publish: degrades cleanly when refresh's sub-modules are absent, prints valid JSON
        (rd(proj) / "index.html").write_text("<html></html>", encoding="utf-8")
        blocked = {"rm_tokens", "rm_git", "rm_map"}
        saved_mods = {n: sys.modules.pop(n, None) for n in blocked}
        orig_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name in blocked:
                raise ModuleNotFoundError(name=name)
            return orig_import(name, *a, **k)

        builtins.__import__ = fake_import
        try:
            out = run("done", sid_b, "--outcome", "Beta done", "--publish")
        finally:
            builtins.__import__ = orig_import
            for n, m in saved_mods.items():
                if m is not None:
                    sys.modules[n] = m
        obj = json.loads(out.rstrip("\n").split("\n")[-1])
        check("capabilities" in obj, "done --publish JSON has capabilities: " + out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest ok")
