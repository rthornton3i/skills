"""rm_activity: recent-activity collector for the roadmap dashboard (activity.json).

Command: activity [--days N] [--max-recent N]. Pure standard library.
Builds a small, capped view of what finished recently: day buckets, features that finished
in the window, and a newest-first list of recent story/feature completions. Token totals are
never duplicated here -- tokens.json already has them and the page looks them up live.
"""
import argparse
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rm_data
from rm_data import Err, rd


def get_days(project, arg):
    if arg is not None:
        return max(1, int(arg))
    try:
        v = rm_data.read_json(rd(project) / "ledger" / "config.json").get("activity_days")
        if isinstance(v, int) and v > 0:
            return v
    except Err:
        pass
    return 30


def get_max_recent(project, arg):
    if arg is not None:
        return max(1, int(arg))
    try:
        v = rm_data.read_json(rd(project) / "ledger" / "config.json").get("activity_max_recent")
        if isinstance(v, int) and v > 0:
            return v
    except Err:
        pass
    return 100


def collect_completions(plan, arch, since_date):
    """Stories completed on/after since_date, resolved to their feature and phase.
    Returns a list of {story, feature, phase} dicts, skipping anything that cannot resolve."""
    feats = {f["id"]: f for f in plan.get("features", []) + arch.get("features", [])}
    phases = {p["id"]: p for p in plan.get("phases", []) + arch.get("phases", [])}
    out = []
    for s in plan.get("stories", []) + arch.get("stories", []):
        status = s.get("status", "done")  # archived light-rows carry no status: treat as done
        if status != "done":
            continue
        completed = s.get("completed")
        if not completed or completed < since_date:
            continue
        feature = feats.get(s.get("feature"))
        if not feature:
            continue
        phase = phases.get(feature.get("phase"))
        if not phase:
            continue
        out.append({"story": s, "feature": feature, "phase": phase})
    return out


def feat_last(completions):
    """{feature_id: latest completed date} across a list of collect_completions() rows."""
    out = {}
    for c in completions:
        fid = c["feature"]["id"]
        d = c["story"].get("completed")
        if d and (fid not in out or d > out[fid]):
            out[fid] = d
    return out


def build_buckets(completions, since, days):
    counts = {}
    for c in completions:
        d = c["story"].get("completed")
        if d:
            counts.setdefault(d, {"stories": 0, "features": set()})
            counts[d]["stories"] += 1
            counts[d]["features"].add(c["feature"]["id"])
    buckets = []
    for i in range(days):
        d = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        c = counts.get(d)
        buckets.append({"date": d, "stories": c["stories"] if c else 0,
                        "features": len(c["features"]) if c else 0})
    return buckets


def build_features(completions):
    last = feat_last(completions)
    seen = {}
    for c in completions:
        f, p = c["feature"], c["phase"]
        fid = f["id"]
        if fid in seen:
            continue
        seen[fid] = {"id": fid, "name": f.get("name"), "phase": f.get("phase"), "phaseName": p.get("name"),
                     "points": f.get("points"), "estTokens": f.get("estTokens"),
                     "completed": last[fid]}
    rows = list(seen.values())
    rows.sort(key=lambda r: r["completed"], reverse=True)
    return rows


def build_recent(completions, cap):
    rows = []
    for c in completions:
        s, f, p = c["story"], c["feature"], c["phase"]
        row = {"date": s.get("completed"), "kind": "story", "id": s["id"], "name": s.get("name"),
               "feature": f["id"], "phase": p["id"], "phaseName": p.get("name")}
        agents = [a for a in (s.get("agent"), s.get("critic")) if a]
        if agents:
            row["agents"] = agents
        if s.get("obe"):
            row["obe"] = True
        rows.append(row)
    rows.sort(key=lambda r: (r["date"] or "", r["id"]), reverse=True)
    return rows[:cap]


def build_tree(completions, last):
    """Nested phase -> feature -> story view, newest-first at every level.
    `last` is the feat_last(completions) mapping (latest completed date per feature)."""
    phases = {}
    order = {}
    for c in completions:
        s, f, p = c["story"], c["feature"], c["phase"]
        pid, fid = p["id"], f["id"]
        if pid not in phases:
            phases[pid] = {"id": pid, "name": p.get("name"), "completed": None, "features": {}}
        pnode = phases[pid]
        if fid not in pnode["features"]:
            pnode["features"][fid] = {"id": fid, "name": f.get("name"), "completed": last.get(fid),
                                       "points": f.get("points"), "stories": []}
        fnode = pnode["features"][fid]
        fnode["stories"].append({"id": s["id"], "name": s.get("name"), "completed": s.get("completed")})
        completed = s.get("completed")
        if completed and (pnode["completed"] is None or completed > pnode["completed"]):
            pnode["completed"] = completed

    tree = []
    for pnode in phases.values():
        feats = list(pnode["features"].values())
        for fnode in feats:
            fnode["stories"].sort(key=lambda r: (r["completed"] or "", r["id"]), reverse=True)
        feats.sort(key=lambda r: (r["completed"] or "", r["id"]), reverse=True)
        pnode["features"] = feats
        tree.append(pnode)
    tree.sort(key=lambda r: (r["completed"] or "", r["id"]), reverse=True)
    return tree


def run_activity(project, days_arg=None, max_recent_arg=None):
    d = rd(project)
    days = get_days(project, days_arg)
    cap = get_max_recent(project, max_recent_arg)
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=days)
    since_date = since_dt.strftime("%Y-%m-%d")
    plan, arch = rm_data.load(project)
    completions = collect_completions(plan, arch, since_date)
    last = feat_last(completions)
    doc = {"schema": 1, "generated": rm_data.now_minute(), "window": {"days": days, "since": since_date},
           "buckets": build_buckets(completions, since_dt, days),
           "features": build_features(completions),
           "recent": build_recent(completions, cap),
           "tree": build_tree(completions, last)}
    rm_data.write_json(d / "activity.json", doc)
    return doc


def cmd_activity(args, project):
    doc = run_activity(project, getattr(args, "days", None), getattr(args, "max_recent", None))
    rm_data.ok(f"activity {len(doc['buckets'])} day buckets, {len(doc['features'])} features, "
               f"{len(doc['recent'])} recent rows (days {doc['window']['days']})", ["activity.json"])


def refresh(project):
    cmd_activity(argparse.Namespace(days=None, max_recent=None, cmd="activity"), project)


def register(sub):
    p = sub.add_parser("activity", help="collect recent activity into activity.json")
    p.add_argument("--days", type=int, default=None,
                   help="window in days (default: ledger/config.json activity_days, else 30)")
    p.add_argument("--max-recent", type=int, default=None, dest="max_recent",
                   help="cap on recent rows kept (default: ledger/config.json activity_max_recent, else 100)")
    p.set_defaults(func=cmd_activity)


# ---------------------------------------------------------------- selftest
def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="rm_activity_selftest_"))
    try:
        def check(c, msg):
            if not c:
                raise AssertionError(msg)

        proj = tmp / "proj"
        (rd(proj) / "ledger").mkdir(parents=True)

        # empty plan still produces a valid document
        rm_data.save(proj, rm_data.empty_plan("selftest"), rm_data.empty_archive())
        doc = run_activity(proj, 30, 100)
        check(doc["schema"] == 1 and doc["window"] == {"days": 30, "since": doc["window"]["since"]}, "empty schema/window")
        check(len(doc["buckets"]) == 30 and all(b["stories"] == 0 for b in doc["buckets"]), "empty buckets")
        check(doc["features"] == [] and doc["recent"] == [], "empty features/recent")

        now = datetime.now(timezone.utc)
        in_window = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        in_window2 = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        out_window = (now - timedelta(days=40)).strftime("%Y-%m-%d")

        plan = rm_data.empty_plan("selftest")
        plan["phases"] = [{"id": "m1", "name": "P1"}]
        plan["features"] = [
            {"id": "f1", "phase": "m1", "name": "F one", "points": 3, "estTokens": 1000},
            {"id": "f2", "phase": "m1", "name": "F two"},
        ]
        plan["stories"] = [
            {"id": "s1", "feature": "f1", "name": "S one", "status": "done", "completed": in_window,
             "agent": "impl-1"},
            {"id": "s2", "feature": "f1", "name": "S two", "status": "done", "completed": in_window2,
             "agent": "impl-2"},
            {"id": "s3", "feature": "f2", "name": "S three (obe)", "status": "done", "completed": in_window,
             "obe": True, "outcome": "overtaken"},
            {"id": "s4", "feature": "f2", "name": "S four (old)", "status": "done", "completed": out_window},
            {"id": "s5", "feature": "f2", "name": "S five (open)", "status": "progress"},
        ]
        rm_data.save(proj, plan, rm_data.empty_archive())

        doc = run_activity(proj, 30, 100)
        check(len(doc["buckets"]) == 30, "30 buckets")
        b_in = next(b for b in doc["buckets"] if b["date"] == in_window)
        check(b_in["stories"] == 2 and b_in["features"] == 2, f"bucket in-window {b_in}")
        b_in2 = next(b for b in doc["buckets"] if b["date"] == in_window2)
        check(b_in2["stories"] == 1 and b_in2["features"] == 1, f"bucket in-window2 {b_in2}")
        check(all(b["stories"] == 0 for b in doc["buckets"] if b["date"] not in (in_window, in_window2)),
              "no other bucket has counts (out-of-window story excluded)")

        fids = {f["id"] for f in doc["features"]}
        check(fids == {"f1", "f2"}, f"features only finished-in-window: {fids}")
        f1 = next(f for f in doc["features"] if f["id"] == "f1")
        check(f1["points"] == 3 and f1["estTokens"] == 1000 and f1["completed"] == in_window2, f"f1 row {f1}")
        f2 = next(f for f in doc["features"] if f["id"] == "f2")
        check(f2["points"] is None and f2["estTokens"] is None, f"f2 no points/estTokens {f2}")
        check(doc["features"][0]["completed"] >= doc["features"][1]["completed"], "features newest-first")

        check(len(doc["recent"]) == 3, f"recent count {len(doc['recent'])}")  # s4/s5 excluded
        dates = [r["date"] for r in doc["recent"]]
        check(dates == sorted(dates, reverse=True), f"recent newest-first {dates}")
        rec_ids = {r["id"] for r in doc["recent"]}
        check("s4" not in rec_ids, "old story excluded from recent")
        s3row = next(r for r in doc["recent"] if r["id"] == "s3")
        check(s3row.get("obe") is True, "obe flag carried")
        s1row = next(r for r in doc["recent"] if r["id"] == "s1")
        check(s1row.get("agents") == ["impl-1"], f"agents carried {s1row}")

        # cap
        doc = run_activity(proj, 30, 2)
        check(len(doc["recent"]) == 2, "max_recent caps rows")
        check(doc["recent"][0]["date"] >= doc["recent"][1]["date"], "capped rows still newest-first")

        # no token totals anywhere in the document
        blob = rm_data.dumps(doc)
        check("estTokens" in blob, "estTokens still present (feature-level only)")
        for bad in ("\"total\"", "\"totals\"", "\"fresh\"", "\"orch_fresh\"", "\"sub_fresh\""):
            check(bad not in blob, f"no token totals field {bad} in activity.json")

        # config.json drives defaults
        rm_data.write_json(rd(proj) / "ledger" / "config.json", {"activity_days": 7, "activity_max_recent": 3})
        doc = run_activity(proj, None, None)
        check(doc["window"]["days"] == 7 and len(doc["buckets"]) == 7, "config activity_days used")
        check(len(doc["recent"]) <= 3, "config activity_max_recent used")

        # archived stories/features (light rows, no status) also contribute
        arch = rm_data.empty_archive()
        arch["phases"] = [{"id": "m2", "name": "P2 (archived)", "completed": in_window}]
        arch["features"] = [{"id": "f3", "phase": "m2", "name": "F three (archived)", "completed": in_window}]
        arch["stories"] = [{"id": "s6", "feature": "f3", "name": "S six (archived)", "completed": in_window}]
        rm_data.write_json(rd(proj) / "plan-archive.json", arch)
        doc = run_activity(proj, 30, 100)
        check(any(r["id"] == "s6" for r in doc["recent"]), "archived light-row story counted as done")
        check(any(f["id"] == "f3" for f in doc["features"]), "archived feature included when finished in window")

        # phaseName is baked in server-side for rows whose phase is archived (client never loads
        # plan-archive.json for the Activity/Tree views, so the name must already be resolved)
        s6row = next(r for r in doc["recent"] if r["id"] == "s6")
        check(s6row.get("phase") == "m2" and s6row.get("phaseName") == "P2 (archived)",
              f"recent row phaseName resolved for archived phase {s6row}")
        f3row = next(f for f in doc["features"] if f["id"] == "f3")
        check(f3row.get("phase") == "m2" and f3row.get("phaseName") == "P2 (archived)",
              f"features row phaseName resolved for archived phase {f3row}")
        f1row = next(f for f in doc["features"] if f["id"] == "f1")
        check(f1row.get("phaseName") == "P1", f"features row phaseName resolved for live phase {f1row}")

        # tree nests phase -> feature -> story, newest-first at every level
        tree = doc["tree"]
        pids = [p["id"] for p in tree]
        check(set(pids) == {"m1", "m2"}, f"tree phases {pids}")
        check(pids == sorted(pids, key=lambda pid: next(p["completed"] for p in tree if p["id"] == pid), reverse=True),
              f"tree phases newest-first {pids}")
        for p in tree:
            fcompleted = [f["completed"] for f in p["features"]]
            check(fcompleted == sorted(fcompleted, reverse=True), f"tree features newest-first in {p['id']}: {fcompleted}")
            for f in p["features"]:
                scompleted = [s["completed"] for s in f["stories"]]
                check(scompleted == sorted(scompleted, reverse=True), f"tree stories newest-first in {f['id']}: {scompleted}")
                for s in f["stories"]:
                    check("points" not in s, f"points must not leak onto story nodes: {s}")
        m1 = next(p for p in tree if p["id"] == "m1")
        f1_node = next(f for f in m1["features"] if f["id"] == "f1")
        check(f1_node["points"] == 3, f"points present on feature node {f1_node}")
        f1_story_ids = {s["id"] for s in f1_node["stories"]}
        check(f1_story_ids == {"s1", "s2"}, f"f1 tree stories {f1_story_ids}")
        m2 = next(p for p in tree if p["id"] == "m2")
        f3_node = next(f for f in m2["features"] if f["id"] == "f3")
        check(f3_node["points"] is None, f"archived feature has no points recorded {f3_node}")
        check(any(s["id"] == "s6" for s in f3_node["stories"]), "archived story present in tree")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
