"""rm_tokens: token totals per story, feature and phase from Claude Code transcripts.

  tokens                    collect transcripts -> ledger/runs.jsonl and tokens.json; print totals and a reconcile line
  tokens --compare-legacy   per story old (archive/legacy/legacy-story-usage.json) vs new fresh; exit 0 only if
                            every difference is a story with events after the old stamp (2026-09-21T16:39Z)

The collection functions are originally from the retired model-usage-tracking skill; only the paths changed
(ledger/ under .claude/roadmap/) and the config is the trimmed ledger/config.json.
Subagent runs are attributed by tagging the Agent description "[s7/implement] text"; the orchestrator by events.
"""
import collections
import datetime as dt
import json
import re
import shutil
import tempfile
from pathlib import Path

import rm_data
from rm_data import Err, rd

DEFAULT_CONFIG = {"agent_effort": {}, "orchestrator_effort": "unspecified", "idle_cap_seconds": 120, "git_days": 14}
TAG = re.compile(r"\[\s*([A-Za-z0-9_.-]+)\s*(?:/\s*([A-Za-z0-9_-]+))?\s*\]")
DONE_STATES = {"done", "not-started", "abandoned", "retired"}
LEGACY_STAMP = "2026-09-21T16:39:00+00:00"


# ---------------------------------------------------------------- originally from the retired model-usage-tracking skill
def slugify(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def family(model):
    m = (model or "").lower()
    for f in ("haiku", "sonnet", "opus", "fable"):
        if f in m:
            return f
    return model or "unknown"


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def dedupe_requests(rows):
    """One API response is logged as several rows with the same requestId and growing output_tokens.
    Keep the final (largest-output) row per request; skip synthetic messages."""
    best = {}
    for r in rows:
        if r.get("type") != "assistant":
            continue
        m = r.get("message") or {}
        u = m.get("usage")
        if not u or m.get("model") == "<synthetic>":
            continue
        key = r.get("requestId") or r.get("uuid")
        if key not in best or u.get("output_tokens", 0) >= best[key]["message"]["usage"].get("output_tokens", 0):
            best[key] = r
    return sorted(best.values(), key=lambda r: r.get("timestamp", ""))


def count_tool_uses(rows):
    ids = set()
    for r in rows:
        if r.get("type") != "assistant":
            continue
        content = (r.get("message") or {}).get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    ids.add(b.get("id"))
    return len(ids)


def tokens(reqs):
    t = collections.Counter()
    for r in reqs:
        u = r["message"]["usage"]
        t["input"] += u.get("input_tokens", 0)
        t["cache_write"] += u.get("cache_creation_input_tokens", 0)
        t["cache_read"] += u.get("cache_read_input_tokens", 0)
        t["output"] += u.get("output_tokens", 0)
    return {k: t[k] for k in ("input", "cache_write", "cache_read", "output")}


def load_config(ledger_dir):
    p = ledger_dir / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def load_events(ledger_dir):
    p = ledger_dir / "events.jsonl"
    return sorted(read_jsonl(p), key=lambda e: e["ts"]) if p.exists() else []


def active_story_at(events, ts):
    """Story most recently started (progress/review) and not yet closed at time ts."""
    active = {}
    for e in events:
        if e["ts"] > ts:
            break
        if e["state"] in DONE_STATES:
            active.pop(e["story"], None)
        else:
            active[e["story"]] = e["ts"]
    if not active:
        return None
    return max(active.items(), key=lambda kv: kv[1])[0]


def find_session_files(project, root=None):
    home = Path(root or Path.home() / ".claude" / "projects") / slugify(Path(project).resolve())
    if not home.exists():
        raise Err(f"No transcript folder found at {home}")
    return home, sorted(home.glob("*.jsonl"))


def collect(project, root=None):
    project = Path(project).resolve()
    ledger_dir = rd(project) / "ledger"
    cfg = load_config(ledger_dir)
    events = load_events(ledger_dir)
    attr_path = ledger_dir / "attribution.json"
    attribution = json.loads(attr_path.read_text(encoding="utf-8")) if attr_path.exists() else {}
    home, sessions = find_session_files(project, root)
    runs = []

    for sess in sessions:
        sid = sess.stem
        # ---- subagent runs
        sub_dir = home / sid / "subagents"
        if sub_dir.exists():
            for tf in sorted(sub_dir.glob("agent-*.jsonl")):
                agent_id = tf.stem.replace("agent-", "")
                meta_p = tf.with_suffix(".meta.json")
                meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
                rows = read_jsonl(tf)
                reqs = dedupe_requests(rows)
                if not reqs:
                    continue
                desc = meta.get("description", "")
                story, role = "unattributed", meta.get("agentType", "agent")
                m = TAG.search(desc)
                if m:
                    story, role = m.group(1), (m.group(2) or role)
                if agent_id in attribution:
                    story = attribution[agent_id].get("story", story)
                    role = attribution[agent_id].get("role", role)
                start, end = reqs[0]["timestamp"], reqs[-1]["timestamp"]
                model = reqs[-1]["message"].get("model") or meta.get("model")
                atype = meta.get("agentType", "agent")
                runs.append({
                    "run_id": f"sub:{agent_id}", "session": sid, "task": story, "role": role,
                    "agent_type": atype, "description": desc, "model": model, "family": family(model),
                    "effort": cfg["agent_effort"].get(atype, "unspecified"),
                    "mode": meta.get("requestShape", "unknown"),
                    "start": start, "end": end,
                    "seconds": round((parse_ts(end) - parse_ts(start)).total_seconds(), 1),
                    "requests": len(reqs), "tool_uses": count_tool_uses(rows),
                    **tokens(reqs), "source": "subagent-transcript",
                })
        # ---- orchestrator (main session), attributed by story events
        reqs = dedupe_requests(read_jsonl(sess))
        buckets = collections.defaultdict(list)
        for r in reqs:
            ts = r["timestamp"]
            story = active_story_at(events, ts) or "unattributed"
            model = r["message"].get("model")
            key = (story, model, ts[:10] if story == "unattributed" else "")
            buckets[key].append(r)
        for (story, model, day), rs in buckets.items():
            start, end = rs[0]["timestamp"], rs[-1]["timestamp"]
            # Active time: sum of gaps between consecutive requests, each capped, so time the user
            # spent away (hours) does not count as model working time.
            cap = cfg.get("idle_cap_seconds", 120)
            stamps = [parse_ts(r["timestamp"]) for r in rs]
            active = sum(min((b - a).total_seconds(), cap) for a, b in zip(stamps, stamps[1:]))
            runs.append({
                "run_id": f"orch:{sid[:8]}:{story}:{family(model)}" + (f":{day}" if day else ""),
                "session": sid, "task": story, "role": "orchestrator", "agent_type": "main-session",
                "description": "", "model": model, "family": family(model),
                "effort": cfg["orchestrator_effort"], "mode": "interactive",
                "start": start, "end": end,
                "seconds": round(active, 1),
                "requests": len(rs), "tool_uses": 0, **tokens(rs), "source": "session-transcript",
            })
    # Retention: the desktop app can delete old transcripts. Keep every old row whose session has no transcript
    # now. Rows above are built only from sessions found now (subagents and orchestrator segments alike), so a
    # kept row never has a rebuilt twin and nothing is counted twice.
    out = ledger_dir / "runs.jsonl"
    found = {s.stem for s in sessions}
    if out.exists():
        runs.extend(r for r in read_jsonl(out) if r.get("session") not in found)
    runs.sort(key=lambda r: r["start"])
    ledger_dir.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")
    return runs, cfg, ledger_dir


def summarize_by_story(runs):
    """Token totals per story (and for rows tied to no story), split into orchestrator and subagent work."""
    def blank():
        return {"fresh": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "requests": 0,
                "seconds": 0.0, "orch_fresh": 0, "sub_fresh": 0, "models": []}
    stories, un, total = {}, blank(), blank()
    for r in runs:
        fresh = r["input"] + r["cache_write"] + r["output"]
        targets = [total, un if r["task"] == "unattributed" else stories.setdefault(r["task"], blank())]
        for t in targets:
            for k in ("input", "cache_write", "cache_read", "output", "requests"):
                t[k] += r[k]
            t["fresh"] += fresh
            t["seconds"] = round(t["seconds"] + r["seconds"], 1)
            t["orch_fresh" if r["role"] == "orchestrator" else "sub_fresh"] += fresh
            if r["family"] not in t["models"]:
                t["models"].append(r["family"])
    return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z"),
            "stories": stories, "unattributed": un, "total": total}


# ---------------------------------------------------------------- new: structure and rollup
def blank_node():
    return {"fresh": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "requests": 0,
            "seconds": 0.0, "orch_fresh": 0, "sub_fresh": 0, "models": []}


def add_row(node, r):
    fresh = r["input"] + r["cache_write"] + r["output"]
    for k in ("input", "cache_write", "cache_read", "output", "requests"):
        node[k] += r[k]
    node["fresh"] += fresh
    node["seconds"] = round(node["seconds"] + r["seconds"], 1)
    node["orch_fresh" if r["role"] == "orchestrator" else "sub_fresh"] += fresh
    if r["family"] not in node["models"]:
        node["models"].append(r["family"])


def load_structure(project):
    """story -> feature -> phase from plan.json and plan-archive.json."""
    plan, arch = rm_data.load(project)
    phases = [p["id"] for p in plan["phases"] + arch["phases"]]
    feature_phase = {f["id"]: f["phase"] for f in plan["features"] + arch["features"]}
    story_feature = {s["id"]: s["feature"] for s in plan["stories"] + arch["stories"]}
    return {"phases": phases, "features": list(feature_phase), "feature_phase": feature_phase,
            "story_feature": story_feature}


def rollup(runs, structure):
    """Every row goes to its story, feature and phase, or to 'unattributed' (no story) or 'unmapped'
    (a story the plan does not list). phases + unattributed + unmapped must equal the total fresh."""
    phases = {p: blank_node() for p in structure["phases"]}
    features = {f: blank_node() for f in structure["features"]}
    stories, un, gone, total = {}, blank_node(), blank_node(), blank_node()
    gone_ids = set()
    for r in runs:
        add_row(total, r)
        task = r["task"]
        if task == "unattributed":
            add_row(un, r)
            continue
        add_row(stories.setdefault(task, blank_node()), r)
        feat = structure["story_feature"].get(task)
        ph = structure["feature_phase"].get(feat)
        if feat in features and ph in phases:
            add_row(features[feat], r)
            add_row(phases[ph], r)
        else:
            add_row(gone, r)
            gone_ids.add(task)
    gone["stories"] = sorted(gone_ids)
    in_phases = sum(p["fresh"] for p in phases.values())
    assert in_phases + un["fresh"] + gone["fresh"] == total["fresh"], (
        f"reconcile failed: {in_phases} + {un['fresh']} + {gone['fresh']} != {total['fresh']}")
    return {"schema": 1, "generated": rm_data.now_minute(), "total": total["fresh"], "totals": total,
            "unattributed": un, "unmapped": gone, "stories": stories, "features": features, "phases": phases}


def reconcile_line(t):
    in_phases = sum(p["fresh"] for p in t["phases"].values())
    return (f"reconcile ok: phases {in_phases:,} + unattributed {t['unattributed']['fresh']:,} + unmapped "
            f"{t['unmapped']['fresh']:,} = {in_phases + t['unattributed']['fresh'] + t['unmapped']['fresh']:,}; "
            f"total {t['total']:,}")


def compare_legacy(new_stories, old_stories, late):
    """Per story (old fresh, new fresh) for every story that differs, and the differing ones not in `late`."""
    diffs = {}
    for sid in sorted(set(new_stories) | set(old_stories)):
        o = (old_stories.get(sid) or {}).get("fresh", 0)
        n = (new_stories.get(sid) or {}).get("fresh", 0)
        if o != n:
            diffs[sid] = (o, n)
    return diffs, sorted(s for s in diffs if s not in late)


def cmd_tokens(args, project):
    runs, _, ledger_dir = collect(project)
    if args.compare_legacy:
        return do_compare(project, runs)
    structure = load_structure(project)
    t = rollup(runs, structure)
    rm_data.write_json(rd(project) / "tokens.json", t)
    workers = [r for r in runs if r["role"] != "orchestrator"]
    orch = [r for r in runs if r["role"] == "orchestrator"]
    fresh = lambda rs: sum(r["input"] + r["cache_write"] + r["output"] for r in rs)  # noqa: E731
    print(f"wrote ledger/runs.jsonl ({len(runs)} rows: {len(workers)} subagent runs, {len(orch)} orchestrator segments)"
          f" and tokens.json ({len(t['stories'])} stories, {len(t['features'])} features, {len(t['phases'])} phases)")
    print(f"fresh tokens (input + cache write + output): workers {fresh(workers):,}  orchestrator {fresh(orch):,}  "
          f"total {t['total']:,}; cache reads {sum(r['cache_read'] for r in runs):,}")
    un, gone = t["unattributed"], t["unmapped"]
    print(f"unattributed {un['fresh']:,} fresh; unmapped {gone['fresh']:,} fresh"
          + (f" (stories not in the plan: {', '.join(gone['stories'])})" if gone["stories"] else ""))
    print(reconcile_line(t))


def do_compare(project, runs):
    d = rd(project)
    old = rm_data.read_json(d / "archive" / "legacy" / "legacy-story-usage.json").get("stories", {})
    new = summarize_by_story(runs)["stories"]
    cutoff = parse_ts(LEGACY_STAMP)
    late = {e["story"] for e in load_events(d / "ledger") if parse_ts(e["ts"]) > cutoff}
    diffs, bad = compare_legacy(new, old, late)
    same = len(set(new) | set(old)) - len(diffs)
    print(f"compare-legacy: {same} stories equal, {len(diffs)} differ")
    for sid, (o, n) in diffs.items():
        print(f"  {sid}: old {o:,} new {n:,} ({'events after the stamp' if sid in late else 'NO later events'})")
    if bad:
        raise Err("differences for stories without events after 2026-09-21T16:39Z: " + ", ".join(bad))
    print("compare-legacy ok: all differences are stories with later events")


def register(sub):
    p = sub.add_parser("tokens", help="collect transcripts and write ledger/runs.jsonl and tokens.json")
    p.add_argument("--compare-legacy", action="store_true", help="compare per-story fresh with the old stamped usage")
    p.set_defaults(func=cmd_tokens)


# ---------------------------------------------------------------- selftest
def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="rm_tokens_selftest_"))
    try:
        proj = tmp / "proj"
        (rd(proj) / "ledger").mkdir(parents=True)
        plan = rm_data.empty_plan("t")
        plan["phases"] = [{"id": "m1", "name": "P"}]
        plan["features"] = [{"id": "f1", "phase": "m1", "name": "F"}]
        plan["stories"] = [{"id": "s1", "feature": "f1", "name": "S", "status": "progress"}]
        rm_data.save(proj, plan, rm_data.empty_archive())
        ev = [{"ts": "2026-01-01T10:00:00.000Z", "story": "s1", "state": "progress"},
              {"ts": "2026-01-01T10:10:00.000Z", "story": "s9", "state": "progress"}]
        (rd(proj) / "ledger" / "events.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n", encoding="utf-8")

        def row(ts, rid, inp, out, model="claude-sonnet-5"):
            return json.dumps({"type": "assistant", "timestamp": ts, "requestId": rid, "uuid": rid,
                               "message": {"model": model, "usage": {"input_tokens": inp, "output_tokens": out,
                                                                     "cache_creation_input_tokens": 5,
                                                                     "cache_read_input_tokens": 100}}})
        root = tmp / "projects"
        home = root / slugify(proj.resolve())
        (home / "sess1" / "subagents").mkdir(parents=True)
        (home / "sess1.jsonl").write_text("\n".join([
            row("2026-01-01T09:00:00.000Z", "a", 1, 1),      # before any event: unattributed
            row("2026-01-01T10:01:00.000Z", "b", 10, 20),    # s1
            row("2026-01-01T10:01:00.000Z", "b", 10, 30),    # same request, larger output wins
            row("2026-01-01T10:11:00.000Z", "c", 7, 8),      # s9, not in the plan: unmapped
        ]) + "\n", encoding="utf-8")
        (home / "sess1" / "subagents" / "agent-x1.jsonl").write_text(row("2026-01-01T10:02:00.000Z", "d", 2, 3) + "\n", encoding="utf-8")
        (home / "sess1" / "subagents" / "agent-x1.meta.json").write_text(
            json.dumps({"description": "[s1/implement] work", "agentType": "implementer"}), encoding="utf-8")
        runs, _, _ = collect(proj, root)
        assert len(runs) == 4, len(runs)
        # a deleted session: its old rows survive a second collect, and nothing is doubled
        gone_row = dict(runs[0], run_id="orch:gone0000:s1:sonnet", session="gone0000", start="2025-12-31T00:00:00.000Z")
        with open(rd(proj) / "ledger" / "runs.jsonl", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(gone_row) + "\n")
        runs, _, _ = collect(proj, root)
        assert len(runs) == 5 and sum(r["session"] == "gone0000" for r in runs) == 1, len(runs)
        runs, _, _ = collect(proj, root)
        assert len(runs) == 5, len(runs)
        runs = [r for r in runs if r["session"] != "gone0000"]
        t = rollup(runs, load_structure(proj))
        assert t["stories"]["s1"]["fresh"] == (10 + 5 + 30) + (2 + 5 + 3), t["stories"]["s1"]
        assert t["stories"]["s1"]["sub_fresh"] == 10 and t["stories"]["s1"]["orch_fresh"] == 45
        assert t["features"]["f1"]["fresh"] == t["phases"]["m1"]["fresh"] == 55
        assert t["unattributed"]["fresh"] == 1 + 5 + 1 and t["unmapped"]["stories"] == ["s9"]
        assert t["unmapped"]["fresh"] == 7 + 5 + 8
        assert t["total"] == 55 + 7 + 20 and t["totals"]["fresh"] == t["total"]
        assert reconcile_line(t).startswith("reconcile ok")
        diffs, bad = compare_legacy({"s1": {"fresh": 5}, "s2": {"fresh": 1}}, {"s1": {"fresh": 4}, "s2": {"fresh": 1}}, {"s1"})
        assert diffs == {"s1": (4, 5)} and bad == []
        assert compare_legacy({"s1": {"fresh": 5}}, {}, set())[1] == ["s1"]
        assert active_story_at(load_events(rd(proj) / "ledger"), "2026-01-01T10:20:00.000Z") == "s9"
        assert TAG.search("[s7/implement] x").group(2) == "implement"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
