"""rm_flow: execution-flow collector for the roadmap dashboard (flow.json).

Command: flow [--days N] [--max-events N]. Pure standard library, reads only the local ledger
(ledger/events.jsonl, and ledger/runs.jsonl to name the agent), never Claude.
Turns the story status events of the last days into rows for the Plan tab's "Execution flow" view:
each story is a branch off the main line with one row per step (planning = planner, plan-review = plan
critic, progress = implementer, review = review critic, approval, done = merge back to main). A stage
that comes round again is a loop (`loop` 2, 3, ...). Lanes are assigned here so parallel stories never
share a lane while both are open. A row carries `agent` (the run's agent type; the page always prints it) and `chg` = 1 only when
that agent differs from the one that last worked the same stage of the story (the page emphasises it), and `tok` = the fresh
tokens (input + cache write + output, like tokens.json) of the subagent runs attributed to that step. A run belongs to the one step
of its story whose stage matches the run's role and whose time span (event time until the next event, plus a small slack)
contains the run's start, the closest start winning; runs of the orchestrator are not steps and are not counted. A run whose
task is not a story id but whose description names a range (s114-s116) is shared evenly across those stories.
A row's `agent` is taken in this order, and `asrc` says which: "event" (the status event's own `agent`), "run" (the matched
run), "story" (the story record's agent or critic, only when run_stage(name) equals the row's state). orchestrator/claude are
never filled in. A story carries `tokm`/`toku` (fresh tokens of its subagent runs matched / not matched to any step) and, when
it has spend but no step shows tokens, `unattr` (the reason).
The file also carries `phases` and a `phase` id per feature, so the page can show Phase and Feature columns.
The file is capped by days and by event count and is loaded lazily.
"""
import argparse
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rm_data
from rm_data import Err, rd
from rm_git import parse_ts

# a run's agent type -> the story status it works in (first prefix that matches wins)
RUN_STAGE = (("plan-critic", "plan-review"), ("planner", "planning"), ("implementer", "progress"),
             ("review-critic", "review"), ("critic", "review"), ("approver", "approval"))
STORY_RE = re.compile(r"\bs\d+\b")
RANGE_RE = re.compile(r"\bs(\d+)\s*[-–]\s*s?(\d+)\b")  # 's114-s116' or 's6-8'
SLACK = timedelta(minutes=2)
NOT_AGENTS = ("orchestrator", "claude", "main-session")  # never shown as a step's agent
RESETS = ("done", "not-started")  # after these a story starts a fresh cycle (loop counts restart)


def cfg_int(project, key, arg, default):
    if arg is not None:
        return max(1, int(arg))
    try:
        v = rm_data.read_json(rd(project) / "ledger" / "config.json").get(key)
        if isinstance(v, int) and v > 0:
            return v
    except Err:
        pass
    return default


def run_stage(agent_type):
    for prefix, stage in RUN_STAGE:
        if str(agent_type).startswith(prefix):
            return stage
    return None


def run_stories(r):
    """Story ids a subagent run worked on: its task when that is a story id; else the description's ids, where a range
    'sN-sM' (up to 12 stories) means every story in it, plus every other id named (at most 12 in all). The run's tokens
    are shared evenly across them."""
    if STORY_RE.fullmatch(str(r.get("task", ""))):
        return [r["task"]]
    d = str(r.get("description", ""))
    ids = []
    m = RANGE_RE.search(d)
    if m and 0 < int(m.group(2)) - int(m.group(1)) < 12:
        ids = ["s%d" % i for i in range(int(m.group(1)), int(m.group(2)) + 1)]
    for x in STORY_RE.findall(d):
        if x not in ids:
            ids.append(x)
    return ids[:12]


def load_runs(project):
    """({story id: [(start, stage, agent_type, fresh tokens)]} for subagent runs that name a story,
    {story id: fresh tokens of the orchestrator's own rows}). A run with no known stage or start is listed with stage None
    (it never matches a step but counts as spend)."""
    out, orch = {}, {}
    for r in rm_data.read_jsonl(rd(project) / "ledger" / "runs.jsonl"):
        if r.get("role") == "orchestrator":
            if STORY_RE.fullmatch(str(r.get("task", ""))):
                orch[r["task"]] = orch.get(r["task"], 0) + sum(int(r.get(k) or 0) for k in ("input", "cache_write", "output"))
            continue
        stage = run_stage(r.get("agent_type", ""))
        start = parse_ts(r.get("start", ""))
        sids = run_stories(r)
        if sids:
            fresh = sum(int(r.get(k) or 0) for k in ("input", "cache_write", "output")) // len(sids)
            for sid in sids:
                out.setdefault(sid, []).append((start, stage if start else None, r.get("agent_type"), fresh))
    return out, orch


def match_runs(story_runs, steps):
    """steps: [(ts, state)] of one story, oldest first. Returns [(agent type or None, fresh tokens or None)] per step.
    Each run goes to the one step whose stage equals the run's stage and whose span [ts, next ts] (plus slack) holds the
    run's start; the closest start wins. A step's agent is the closest run's; its tokens are the sum of its runs'."""
    span = []
    for k, (ts, state) in enumerate(steps):
        span.append((state, parse_ts(ts), parse_ts(steps[k + 1][0]) if k + 1 < len(steps) else None))
    got = [[None, None] for _ in steps]  # per step: [(gap, agent), tokens]
    for rs, stage, atype, fresh in story_runs:
        best = None
        for k, (state, start, end) in enumerate(span):
            if state != stage or rs < start - SLACK or (end and rs > end + SLACK):
                continue
            gap = abs((rs - start).total_seconds())
            if best is None or gap < best[0]:
                best = (gap, k)
        if best is None:
            continue
        g = got[best[1]]
        if g[0] is None or best[0] < g[0][0]:
            g[0] = (best[0], atype)
        g[1] = (g[1] or 0) + fresh
    return [(g[0][1] if g[0] else None, g[1]) for g in got]


def short_phase(name):
    """A short label for a phase column: 'Phase 2 - Trust the Backtester' -> 'Phase 2'; other names are cut to 18 characters."""
    name = str(name).strip()
    m = re.match(r"(?i)(phase\s*\d+|m\d+)", name)
    return m.group(1) if m else name[:18]


def story_events(project):
    """{story id: [(ts, file order, state, agent)]} oldest first, with back-to-back repeats of a state collapsed
    (the latest agent named within the repeats is kept)."""
    per = {}
    for i, e in enumerate(rm_data.read_jsonl(rd(project) / "ledger" / "events.jsonl")):
        ts, sid, state = e.get("ts"), e.get("story"), e.get("state")
        if not (ts and sid and state) or parse_ts(ts) is None:
            continue
        per.setdefault(sid, []).append((str(ts), i, str(state), str(e.get("agent") or "")))
    for sid, lst in per.items():
        lst.sort()
        out = []
        for row in lst:
            if out and out[-1][2] == row[2]:
                if row[3]:
                    out[-1] = out[-1][:3] + (row[3],)
                continue
            out.append(row)
        per[sid] = out
    return per


def assign_lanes(stories, n):
    """stories: {sid: {"top": row, "bottom": row}} (row 0 = newest). Sets "lane" (1..); the main line is lane 0.
    A lane is reused only when the earlier story is completely finished (rows do not overlap). A story that is
    not closed stays open up to the top edge, so it keeps its lane to row 0."""
    frontier = []  # per lane: the top (newest) row of the last story placed in it
    for sid in sorted(stories, key=lambda k: (-stories[k]["bottom"], k)):  # oldest start first
        st = stories[sid]
        top_occ = st["top"] if st["closed"] else 0
        for i, top in enumerate(frontier):
            if st["bottom"] < top:
                frontier[i] = top_occ
                st["lane"] = i + 1
                break
        else:
            frontier.append(top_occ)
            st["lane"] = len(frontier)
    return len(frontier)


def build_flow(project, days=None, max_events=None, now=None):
    days = cfg_int(project, "flow_days", days, 14)
    cap = cfg_int(project, "flow_max_events", max_events, 250)
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    plan, arch = rm_data.load(project)
    feats = {f["id"]: f for f in arch.get("features", []) + plan.get("features", [])}
    phase_names = {p["id"]: p.get("name") or p["id"] for p in arch.get("phases", []) + plan.get("phases", [])}
    plan_stories = {s["id"]: s for s in arch.get("stories", []) + plan.get("stories", [])}
    runs, orch = load_runs(project)
    per = story_events(project)
    unattr, tokstat = {}, {}

    flat = []  # (ts, order, story, state, loop, agent or None, agent changed within the stage, fresh tokens or None, agent source)
    for sid, lst in per.items():
        seen, last_agent = {}, {}
        matched = match_runs(runs.get(sid, []), [(ts, state) for ts, _, state, _ in lst])
        got = sum(m[1] or 0 for m in matched)
        sub = sum(x[3] for x in runs.get(sid, []))
        tokstat[sid] = (got, max(sub - got, 0))
        if not got and (sub or orch.get(sid)):
            if sub:
                unattr[sid] = (f"{len(runs[sid])} subagent run(s), {sub:,} tokens, match no step of this story "
                               "(role, time or tag do not fit its status events)")
            else:
                unattr[sid] = f"only orchestrator work ({orch[sid]:,} tokens), which is not a step"
        rec = plan_stories.get(sid, {})
        for k, (ts, order, state, ev_agent) in enumerate(lst):
            seen[state] = seen.get(state, 0) + 1
            agent, tok = matched[k]
            asrc = "run" if agent else ""
            if ev_agent:
                agent, asrc = ev_agent, "event"
            if not agent:
                for name in (rec.get("agent"), rec.get("critic")):
                    if name and run_stage(name) == state:
                        agent, asrc = str(name), "story"
                        break
            if agent and str(agent).lower() in NOT_AGENTS:
                agent, asrc = None, ""
            # runs are matched to a stage by their role (implementer -> progress, ...), so the usual agent of a stage is
            # simply the role's own; an agent is worth showing only when it differs from the one that last worked this
            # same stage of the story (an escalation, e.g. a different implementer)
            chg = bool(agent) and state in last_agent and last_agent[state] != agent
            if agent:
                last_agent[state] = agent
            flat.append((ts, order, sid, state, seen[state], agent, chg, tok, asrc))
            if state in RESETS:
                seen = {}
    flat = [r for r in flat if r[0] >= since]
    flat.sort(key=lambda r: (r[0], r[1]), reverse=True)
    flat = flat[:cap]
    rows = []
    for ts, order, sid, state, loop, agent, chg, tok, asrc in flat:
        row = {"ts": ts[:19], "story": sid, "state": state}
        if loop > 1:
            row["loop"] = loop
        if agent:
            row["agent"] = agent  # the page always prints it; "chg" marks an agent that differs from the stage's previous one
            row["asrc"] = asrc  # where it came from: event, run or story
            if chg:
                row["chg"] = 1
        if tok:
            row["tok"] = tok
        rows.append(row)

    info = {}
    for i, r in enumerate(rows):
        st = info.setdefault(r["story"], {"top": i, "bottom": i})
        st["bottom"] = i
    for sid, st in info.items():
        st["closed"] = rows[st["top"]]["state"] == "done"
    n = len(rows)
    for sid, st in info.items():
        oldest = flat[st["bottom"]]
        st["cut"] = (oldest[0], oldest[1]) != (per[sid][0][0], per[sid][0][1])
        if st["cut"]:
            st["bottom"] = n  # the lane runs off the bottom edge (older history is not loaded)
    lanes = assign_lanes(info, n)

    order = []
    for r in reversed(rows):  # features in order of first appearance, oldest first
        f = plan_stories.get(r["story"], {}).get("feature")
        if f and f not in order:
            order.append(f)
    stories = {}
    for sid, st in sorted(info.items(), key=lambda kv: kv[1]["lane"]):
        ps = plan_stories.get(sid, {})
        s = {"name": str(ps.get("name") or sid)[:90], "feature": ps.get("feature") or "", "lane": st["lane"]}
        if st["cut"]:
            s["cut"] = True
        if sid in tokstat and (tokstat[sid][0] or tokstat[sid][1]):
            s["tokm"], s["toku"] = tokstat[sid]
        if sid in unattr:
            s["unattr"] = unattr[sid]
        stories[sid] = s
    fl = [{"id": f, "name": (feats.get(f) or {}).get("name") or f, "phase": (feats.get(f) or {}).get("phase") or ""} for f in order]
    used = []
    for f in fl:
        if f["phase"] and f["phase"] not in used:
            used.append(f["phase"])
    phases = [{"id": p, "name": str(phase_names.get(p) or p), "short": short_phase(phase_names.get(p) or p)} for p in used]
    return {"schema": 1, "generated": rm_data.now_minute(), "days": days, "since": since[:10], "max_events": cap,
            "lanes": lanes, "phases": phases, "features": fl, "stories": stories, "rows": rows}


def run_flow(project, days=None, max_events=None):
    doc = build_flow(project, days, max_events)
    rm_data.write_json(rd(project) / "flow.json", doc)
    return doc


def cmd_flow(args, project):
    doc = run_flow(project, getattr(args, "days", None), getattr(args, "max_events", None))
    rm_data.ok(f"flow {len(doc['rows'])} rows, {len(doc['stories'])} stories, {doc['lanes']} lanes "
               f"(days {doc['days']}, cap {doc['max_events']})", ["flow.json"])


def refresh(project):
    cmd_flow(argparse.Namespace(days=None, max_events=None, cmd="flow"), project)


def register(sub):
    p = sub.add_parser("flow", help="collect the Plan tab execution flow from the ledger into flow.json")
    p.add_argument("--days", type=int, default=None, help="window in days (default: ledger/config.json flow_days, else 14)")
    p.add_argument("--max-events", type=int, default=None, dest="max_events",
                   help="cap on events kept, newest first (default: ledger/config.json flow_max_events, else 250)")
    p.set_defaults(func=cmd_flow)


# ---------------------------------------------------------------- selftest
def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="rm_flow_selftest_"))
    try:
        def check(c, msg):
            if not c:
                raise AssertionError(msg)

        proj = tmp / "proj"
        (rd(proj) / "ledger").mkdir(parents=True)
        plan = rm_data.empty_plan("selftest")
        plan["phases"] = [{"id": "m1", "name": "P1"}]
        plan["features"] = [{"id": "f1", "phase": "m1", "name": "F one"}, {"id": "f2", "phase": "m1", "name": "F two"}]
        plan["stories"] = [{"id": "s1", "feature": "f1", "name": "S one", "status": "done"},
                           {"id": "s2", "feature": "f2", "name": "S two", "status": "review"},
                           {"id": "s3", "feature": "f1", "name": "S three", "status": "progress"}]
        rm_data.save(proj, plan, rm_data.empty_archive())
        doc = run_flow(proj)
        check(doc["rows"] == [] and doc["stories"] == {} and doc["lanes"] == 0, "empty ledger gives an empty flow")

        now = datetime.now(timezone.utc)

        def at(minutes):
            return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        ev = rd(proj) / "ledger" / "events.jsonl"
        seq = [(100, "s1", "planning"), (95, "s1", "plan-review"), (90, "s1", "progress"), (90, "s1", "progress"),
               (85, "s1", "review"), (80, "s1", "progress"), (75, "s1", "review"), (70, "s1", "done"),
               (92, "s2", "progress"), (60, "s2", "review"),          # s2 overlaps s1 and stays open
               (50, "s3", "progress"),                                  # starts after s1 closed, overlaps s2
               (40, "s3", "done"), (30, "s3", "not-started"),
               (60 * 24 * 40, "s4", "done")]                            # far outside the window
        for m, sid, state in seq:
            rm_data.append_jsonl(ev, {"ts": at(m), "story": sid, "state": state, "note": ""})
        rm_data.append_jsonl(rd(proj) / "ledger" / "runs.jsonl",
                             {"task": "unattributed", "role": "plan-critic", "agent_type": "plan-critic-opus-high",
                              "description": "Critique s1 plan", "start": at(95),
                              "input": 5, "cache_write": 100, "cache_read": 99999, "output": 45})
        rm_data.append_jsonl(rd(proj) / "ledger" / "runs.jsonl",
                             {"task": "s1", "role": "orchestrator", "agent_type": "main-session", "start": at(95)})
        for m, atype, toks in ((90, "implementer-sonnet-high", (10, 1000, 500)), (89, "implementer-sonnet-high", (1, 200, 100)),
                               (80, "implementer-opus-high", (20, 2000, 1000))):
            rm_data.append_jsonl(rd(proj) / "ledger" / "runs.jsonl",
                                 {"task": "s1", "role": "impl", "agent_type": atype, "start": at(m), "input": toks[0],
                                  "cache_write": toks[1], "cache_read": 5000, "output": toks[2]})
        doc = run_flow(proj)
        rows = doc["rows"]
        pr = [r for r in rows if r["story"] == "s1" and r["state"] == "progress"]  # newest first: loop 2, then loop 1
        check([r.get("agent") for r in pr] == ["implementer-opus-high", "implementer-sonnet-high"], f"progress agents {pr}")
        check([bool(r.get("chg")) for r in pr] == [True, False], "agent flagged only when it changed within the stage")
        check(not any(r.get("chg") for r in rows if r["state"] == "plan-review"), "usual agent is not flagged")
        check(len(rows) == 12, f"12 rows (duplicate and out-of-window events dropped), got {len(rows)}")
        check([r["ts"] for r in rows] == sorted((r["ts"] for r in rows), reverse=True), "rows newest first")
        s1 = [r for r in rows if r["story"] == "s1"]
        check([r["state"] for r in reversed(s1)] == ["planning", "plan-review", "progress", "review", "progress", "review", "done"],
              "s1 sequence keeps the loop")
        check([r.get("loop") for r in reversed(s1)] == [None, None, None, None, 2, 2, None], f"loop numbers {s1}")
        check(next(r for r in s1 if r["state"] == "plan-review").get("agent") == "plan-critic-opus-high", "agent from runs.jsonl")
        # tokens: fresh = input + cache write + output (cache reads excluded); two runs in one step add up; steps without runs have no tok
        check([r.get("tok") for r in pr] == [3020, 1811], f"progress tokens {pr}")
        check(next(r for r in s1 if r["state"] == "plan-review").get("tok") == 150, "runs.jsonl story from the description, cache reads not counted")
        check(not any("tok" in r for r in s1 if r["state"] in ("planning", "review", "done")), "no tok without a matching run")
        check(sum(r.get("tok", 0) for r in rows) == 3020 + 1811 + 150, "orchestrator runs and other stories add nothing")
        check(doc["phases"] == [{"id": "m1", "name": "P1", "short": "P1"}], f"phases {doc['phases']}")
        check(all(f["phase"] == "m1" for f in doc["features"]), "features carry their phase")
        check(rm_data.dumps(doc).count('"tok"') == 3, "tok only on rows that have one")
        check(run_stories({"task": "s6", "description": "Review s6-s7"}) == ["s6"], "a story task wins")
        check(run_stories({"task": "unattributed", "description": "Build s114-s116 (x)"}) == ["s114", "s115", "s116"], "range expands")
        check(run_stories({"task": "unattributed", "description": "Plan s111 sweep"}) == ["s111"], "single id")
        check(run_stories({"task": "unattributed", "description": "no id"}) == [], "no id")
        check(not any(r.get("agent") for r in s1 if r["state"] == "planning"), "no agent when no run matches")
        check("cut" not in doc["stories"]["s1"], "s1 starts inside the window")

        def span(sid):
            idx = [i for i, r in enumerate(rows) if r["story"] == sid]
            return min(idx), max(idx)

        st = doc["stories"]
        check(st["s1"]["lane"] != st["s2"]["lane"], "overlapping stories get different lanes")
        check(st["s3"]["lane"] != st["s2"]["lane"], "s3 overlaps s2")
        a, b = span("s1"), span("s3")
        check(st["s1"]["lane"] == st["s3"]["lane"] or a[0] < b[1] and b[0] < a[1], "lane reuse only without overlap")
        for x in st:
            for y in st:
                if x < y and st[x]["lane"] == st[y]["lane"]:
                    ax, ay = span(x), span(y)
                    check(ax[1] < ay[0] or ay[1] < ax[0], f"{x} and {y} share lane {st[x]['lane']} but overlap")
        check([f["id"] for f in doc["features"]] == ["f1", "f2"], f"features {doc['features']}")
        # cap keeps the newest rows and marks a story whose start is not loaded
        small = run_flow(proj, 14, 5)
        check(len(small["rows"]) == 5, "cap on events")
        check(any(s.get("cut") for s in small["stories"].values()), "cut story marked")
        check(len(rm_data.dumps(doc)) < 20000, "small file")
        check(next(r for r in s1 if r["state"] == "plan-review").get("asrc") == "run", "run agent is labelled run")
        check(run_stories({"task": "unattributed", "description": "Plan s5 and s9 (also s5)"}) == ["s5", "s9"], "all ids, no repeats")
        check(len(run_stories({"task": "unattributed", "description": " ".join("s%d" % i for i in range(1, 30))})) == 12, "cap 12")
        check("tokm" in doc["stories"]["s1"] and doc["stories"]["s1"]["toku"] == 0 and "unattr" not in doc["stories"]["s1"],
              f"story token counts {doc['stories']['s1']}")

        # second project: event agents, story-record fallback, unattributed spend
        p2 = tmp / "proj2"
        (rd(p2) / "ledger").mkdir(parents=True)
        plan2 = rm_data.empty_plan("selftest2")
        plan2["phases"] = [{"id": "m1", "name": "P1"}]
        plan2["features"] = [{"id": "f1", "phase": "m1", "name": "F one"}]
        plan2["stories"] = [{"id": "s1", "feature": "f1", "name": "A", "status": "review", "agent": "implementer-sonnet-high",
                             "critic": "review-critic-opus-medium"},
                            {"id": "s2", "feature": "f1", "name": "B", "status": "progress", "agent": "orchestrator"},
                            {"id": "s3", "feature": "f1", "name": "C", "status": "progress"}]
        rm_data.save(p2, plan2, rm_data.empty_archive())
        ev2 = rd(p2) / "ledger" / "events.jsonl"
        for m, sid, state, who in ((50, "s1", "planning", "planner-sonnet-max"), (49, "s1", "planning", ""),
                                   (40, "s1", "progress", ""), (30, "s1", "review", ""), (25, "s1", "approval", ""),
                                   (45, "s2", "progress", "claude"), (44, "s3", "progress", "")):
            e = {"ts": at(m), "story": sid, "state": state, "note": ""}
            if who:
                e["agent"] = who
            rm_data.append_jsonl(ev2, e)
        rd_runs = rd(p2) / "ledger" / "runs.jsonl"
        rm_data.append_jsonl(rd_runs, {"task": "s3", "role": "orchestrator", "agent_type": "main-session", "start": at(44),
                                       "input": 1, "cache_write": 2, "output": 3})
        rm_data.append_jsonl(rd_runs, {"task": "s2", "role": "x", "agent_type": "implementer-sonnet-high", "start": at(300),
                                       "input": 4, "cache_write": 5, "output": 6})
        d2 = run_flow(p2)
        r2 = {(r["story"], r["state"]): r for r in d2["rows"]}
        check(r2[("s1", "planning")].get("agent") == "planner-sonnet-max" and r2[("s1", "planning")]["asrc"] == "event",
              "event agent wins; the latest agent within collapsed repeats is kept")
        check(sum(1 for r in d2["rows"] if r["story"] == "s1" and r["state"] == "planning") == 1, "repeat collapsed")
        check(r2[("s1", "progress")]["agent"] == "implementer-sonnet-high" and r2[("s1", "progress")]["asrc"] == "story",
              "story record fills a progress step")
        check(r2[("s1", "review")]["agent"] == "review-critic-opus-medium" and r2[("s1", "review")]["asrc"] == "story",
              "story critic fills a review step")
        check("agent" not in r2[("s1", "approval")], "story agent does not fill a stage its role does not work")
        check("agent" not in r2[("s2", "progress")] and "agent" not in r2[("s3", "progress")], "orchestrator/claude never filled")
        check("unattr" in d2["stories"]["s3"] and "orchestrator" in d2["stories"]["s3"]["unattr"], "orchestrator-only spend is flagged")
        check("match no step" in d2["stories"]["s2"]["unattr"] and d2["stories"]["s2"]["toku"] == 15, f"{d2['stories']['s2']}")
        check("unattr" not in d2["stories"]["s1"] and "tokm" not in d2["stories"]["s1"], "no spend, no marker")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
