"""rm_git: git activity collector for the roadmap dashboard (git.json + archive/git-events.jsonl).

Command: git [--days N] [--max N]. Pure standard library. Git is always called with argument lists (no shell).
Retention: rows of the previous git.json older than the cutoff are appended to
archive/git-events.jsonl (deduplicated by key) before git.json is rewritten with in-window rows only.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rm_data
from rm_data import Err, rd

US = "\x1f"
SCAN = 1500   # most commits read when building the window (those committed inside it are kept, older ones dropped)
STAT_RE = re.compile(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?")
EVENT_PREFIXES = (("merge", "merge"), ("checkout: moving", "checkout"), ("branch: Created", "branch-created"),
                  ("pull", "pull"))


def git(project, *args, env=None):
    """Run git in project; return stdout text, or "" on any failure (never raises)."""
    try:
        r = subprocess.run(["git", "-C", str(project)] + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
    except OSError:
        return ""
    return r.stdout if r.returncode == 0 and r.stdout else ""


def parse_ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def get_max(project, arg):
    if arg is not None:
        return max(1, int(arg))
    try:
        v = rm_data.read_json(rd(project) / "ledger" / "config.json").get("git_max_commits")
        if isinstance(v, int) and v > 0:
            return v
    except Err:
        pass
    return 150


def get_days(project, arg):
    if arg is not None:
        return max(1, int(arg))
    try:
        v = rm_data.read_json(rd(project) / "ledger" / "config.json").get("git_days")
        if isinstance(v, int) and v > 0:
            return v
    except Err:
        pass
    return 14


def clean_refs(raw):
    """Decoration names for one commit: HEAD -> stripped, tags as tag:name, origin/HEAD dropped."""
    names = []
    for r in raw.split(","):
        r = r.strip()
        if r.startswith("HEAD -> "):
            r = r[8:]
        if r.startswith("tag: "):
            r = "tag:" + r[5:]
        if r and r != "HEAD" and r != "origin/HEAD":
            names.append(r)
    local = {r for r in names if not r.startswith("tag:") and not r.startswith("origin/")}
    names = [r for r in names if not (r.startswith("origin/") and r[7:] in local)]
    rank = lambda r: 2 if r.startswith("tag:") else (1 if r.startswith("origin/") else 0)
    return sorted(names, key=rank)  # stable: local branches, then remotes, then tags


def assign_lanes(commits):
    """Set lane and edges on commits (newest first, topological); return the max lane count."""
    active, top = [], 0
    for c in commits:
        mine = [i for i, e in enumerate(active) if e == c["id"]]
        if mine:
            lane = mine[0]
        elif None in active:
            lane = active.index(None)
        else:
            active.append(None)
            lane = len(active) - 1
        for i in mine[1:]:
            active[i] = None
        edges = []
        for n, p in enumerate(c["parents"]):
            if p in active:
                j = active.index(p)
                edges.append([p, j])
                if n == 0:
                    active[lane] = None
            elif n == 0:
                active[lane] = p
                edges.append([p, lane])
            else:
                if None in active:
                    k = active.index(None)
                else:
                    active.append(None)
                    k = len(active) - 1
                active[k] = p
                edges.append([p, k])
        if not c["parents"]:
            active[lane] = None
        top = max(top, len(active), lane + 1)
        while active and active[-1] is None:
            active.pop()
        c["lane"], c["edges"] = lane, edges
    return top


MERGE_NAME_RE = re.compile(r"Merge (?:remote-tracking )?branch '([^']+)'|Merge pull request #\d+ from [^/\s]+/(\S+)"
                           r"|Merge ((?:feature|fix|hotfix|bugfix)/[\w.-]+)")
TRUNKS = ("main", "master", "dev")


def label_branches(commits):
    """Set c["branch"] (a branch name) on every commit that can be attributed to one, so the page can print the
    name beside the graph. Long-lived branches (main, master, dev, phase/*) claim their first-parent chain first,
    then other branches from the oldest tip to the newest (so stacked branches split correctly), then branches
    that were merged and deleted are named from their merge commit subject. A commit already named is never renamed."""
    by_id = {c["id"]: c for c in commits}

    def claim(name, cid):
        while cid in by_id and "branch" not in by_id[cid]:
            by_id[cid]["branch"] = name
            ps = by_id[cid]["parents"]
            cid = ps[0] if ps else None

    tips = []
    for i, c in enumerate(commits):
        for r in c["refs"]:
            if r.startswith("tag:"):
                continue
            name = r[7:] if r.startswith("origin/") else r
            trunk = name in TRUNKS or name.startswith("phase/")
            tips.append((0 if trunk else 1, -i, name, c["id"]))
    for _, _, name, cid in sorted(tips):
        claim(name, cid)
    for c in commits:
        if len(c["parents"]) > 1:
            m = MERGE_NAME_RE.match(c["subject"])
            if m:
                claim(m.group(1) or m.group(2) or m.group(3), c["parents"][1])


def collect_commits(project, days, cap):
    """Newest-first commits of the window. Branch names are worked out over EVERY commit in the window (so a branch
    whose first-parent chain runs past the cap is still named correctly); only the newest `cap` are kept and laid
    out. Returns (kept, lanes, all_commits); all_commits keep no lane data and feed the active-branch links."""
    # No --since: git stops walking at the first old-looking commits, and a branch started long ago that merged
    # recently (out-of-order dates) would lose commits. Walk up to SCAN commits and keep those committed in the window.
    out = git(project, "log", "--all", "--topo-order", f"--max-count={SCAN}",
              "--date=iso-strict", "--pretty=format:%H%x1f%h%x1f%aI%x1f%an%x1f%P%x1f%D%x1f%cI%x1f%s", "--shortstat")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    commits, plist, keep = [], [], []
    for line in out.splitlines():
        if US in line:
            f = (line.split(US) + [""] * 8)[:8]
            commits.append({"sha": f[0], "short": f[1], "ts": f[2], "author": f[3], "subject": f[7],
                            "refs": clean_refs(f[5]), "files": 0, "ins": 0, "del": 0})
            plist.append(f[4].split())
            d = parse_ts(f[6])
            keep.append(d is None or d >= cutoff)
        elif commits:
            m = STAT_RE.search(line)
            if m:
                c = commits[-1]
                c["files"], c["ins"], c["del"] = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
    commits = [c for c, k in zip(commits, keep) if k]
    plist = [p for p, k in zip(plist, keep) if k]
    n = 8
    if len({c["sha"][:8] for c in commits}) < len(commits):
        n = 10
    for c, ps in zip(commits, plist):
        c["id"] = c["sha"][:n]
        c["parents"] = [p[:n] for p in ps]
    label_branches(commits)
    kept = commits[:cap]
    lanes = assign_lanes(kept)
    order = ("id", "sha", "short", "ts", "author", "subject", "parents", "edges", "lane", "branch", "refs", "files",
             "ins", "del")
    return [{k: c[k] for k in order if k in c} for c in kept], lanes, commits


def collect_branches(project):
    out = git(project, "for-each-ref", "--format=%(refname)%1f%(objectname:short)%1f%(committerdate:iso-strict)",
              "refs/heads", "refs/remotes/origin")
    has_dev = bool(git(project, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/dev").strip())
    branches = []
    for line in out.splitlines():
        f = (line.split(US) + ["", "", ""])[:3]
        full = f[0]
        if full.endswith("/HEAD"):
            continue
        remote = full.startswith("refs/remotes/")
        name = full[len("refs/remotes/"):] if remote else full[len("refs/heads/"):]
        b = {"name": name, "tip": f[1], "ts": f[2], "remote": remote}
        if has_dev:
            cnt = git(project, "rev-list", "--left-right", "--count", f"refs/remotes/origin/dev...{full}").split()
            if len(cnt) == 2:
                b["behind_dev"], b["ahead_dev"] = int(cnt[0]), int(cnt[1])
        branches.append(b)
    return branches


# ---------------------------------------------------------------- active branches (Git tab, top section)
SID_RE = re.compile(r"\bs(\d{1,4})(?:\s*[-–]\s*s?(\d{1,4}))?\b")
FID_RE = re.compile(r"\bf(\d{1,3})\b")
PR_RE = re.compile(r"Merge pull request #(\d+) from [^/\s]+/(\S+)")
NAME_STOP = {"feature", "bugfix", "hotfix", "fix", "and", "the", "for", "impl", "wip", "tmp", "new", "update", "add"}
MAX_LINKS = 10          # links stored per branch (the page shows a few and the rest as "+N more")
MAX_OWN = 30            # newest own commits read for story ids
NEAR_SECONDS = 600      # a status event this long before one of the branch's own commits counts as "near" it
VIA_ORDER = {"subject": 0, "ledger": 1, "name": 2, "plan": 3}


def trunc(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def is_integration(name):
    return name in TRUNKS or name.startswith("phase/")


def plan_lookup(project):
    """{stories: {id: (name, feature)}, features: {id: (name, branch-or-list)}} from plan.json and plan-archive.json."""
    stories, features = {}, {}
    for fn in ("plan.json", "plan-archive.json"):
        try:
            doc = rm_data.read_json(rd(project) / fn)
        except Err:
            continue
        for f in doc.get("features") or []:
            if isinstance(f, dict) and f.get("id"):
                features[f["id"]] = (str(f.get("name") or f["id"]), f.get("branch"))
        for s in doc.get("stories") or []:
            if isinstance(s, dict) and s.get("id"):
                stories[s["id"]] = (str(s.get("name") or ""), s.get("feature") or "")
    return {"stories": stories, "features": features}


def stem(w):
    for suf in ("ations", "ation", "ions", "ion", "ing", "ers", "er", "ed", "es", "s", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def name_tokens(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in NAME_STOP]


def tok_match(a, b):
    return a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))


def name_matches(branch, name):
    """True when every meaningful word of the branch name (feature/, dashes and stop words dropped) appears, after a
    crude stem, in the plan name."""
    bt = name_tokens(branch.split("/", 1)[1] if "/" in branch else branch)
    nt = name_tokens(name)
    return bool(bt) and all(any(tok_match(b, n) for n in nt) for b in bt)


def ids_in(subject, stories):
    """Story ids named in a commit subject (s114, s119-s121, 'Close s124, s125'); only ids that exist in the plan."""
    out = []
    for m in SID_RE.finditer(subject):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if b < a or b - a > 12:
            b = a
        for n in range(a, b + 1):
            if f"s{n}" in stories and f"s{n}" not in out:
                out.append(f"s{n}")
    return out


def reflog_checkouts(project):
    """Chronological [(datetime, branch-checked-out)] from the HEAD reflog."""
    rows = []
    out = git(project, "reflog", "--date=iso-strict", "--format=%gd%x1f%gs")
    for line in out.splitlines():
        sel, _, gs = line.partition(US)
        m = re.search(r"@\{(.*)\}", sel)
        d = parse_ts(m.group(1)) if m else None
        mm = re.match(r"checkout: moving from .+ to (.+)$", gs)
        if d and mm:
            rows.append((d, mm.group(1)))
    rows.sort(key=lambda r: r[0])
    return rows


def open_prs(project):
    """{branch: number} of open pull requests from `gh pr list` (refresh time only). Any problem (no gh, no network,
    no login, not a GitHub remote, ledger/config.json git_prs false) gives {} and the page falls back to the numbers
    in merge-commit subjects."""
    try:
        if rm_data.read_json(rd(project) / "ledger" / "config.json").get("git_prs") is False:
            return {}
    except Err:
        pass
    if not shutil.which("gh") or "github.com" not in git(project, "remote", "get-url", "origin"):
        return {}
    try:
        r = subprocess.run(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", "number,headRefName"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, cwd=str(project))
        if r.returncode != 0:
            return {}
        return {p["headRefName"]: p["number"] for p in json.loads(r.stdout) if "number" in p and "headRefName" in p}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def is_ancestor(project, a, b):
    r = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", a, b], capture_output=True)
    return r.returncode == 0


def collect_active(project, window, days, head, now, prs=None):
    """The branches a reader should look at: not merged into an integration branch (main, master, dev, phase/*), or
    with a tip committed on in the last `days` days. Each gets its base, ahead/behind, PR number and the
    features/stories it supports, with how every link was derived (subject, ledger, name, plan)."""
    from concurrent.futures import ThreadPoolExecutor
    out = git(project, "for-each-ref", "--format=%(refname)%1f%(objectname)%1f%(committerdate:iso-strict)",
              "refs/heads", "refs/remotes/origin")
    refs = {}   # full ref -> (name, sha, ts, remote)
    for line in out.splitlines():
        f = (line.split(US) + ["", "", ""])[:3]
        if f[0].endswith("/HEAD"):
            continue
        remote = f[0].startswith("refs/remotes/")
        refs[f[0]] = (f[0][len("refs/remotes/origin/"):] if remote else f[0][len("refs/heads/"):], f[1], f[2], remote)
    if not refs:
        return {"base": "", "days": days, "branches": []}
    by_name = {}
    for full, (name, sha, ts, remote) in refs.items():
        b = by_name.setdefault(name, {"name": name, "local": False, "remote": False, "sha": sha, "ts": ts})
        b["remote" if remote else "local"] = True
        if not remote:
            b["sha"] = sha
        if (parse_ts(ts) or now) > (parse_ts(b["ts"]) or now):
            b["ts"] = ts
    names = set(by_name)
    # base of everything that is not itself an integration branch: the newest phase branch, else dev, main, master
    phases = sorted((n for n in names if n.startswith("phase/")), key=lambda n: parse_ts(by_name[n]["ts"]) or now, reverse=True)
    default_base = phases[0] if phases else next((n for n in ("dev", "main", "master") if n in names), "")

    def base_of(name):
        if not is_integration(name):
            return default_base
        if name.startswith("phase/") or name == "dev":
            if name != "dev" and "dev" in names:
                return "dev"
            return next((n for n in ("main", "master") if n in names), "")
        return ""

    def best_ref(name):
        """The ref to measure against: origin's copy when the local one is an ancestor of it (PRs merge on GitHub)."""
        loc, rem = f"refs/heads/{name}", f"refs/remotes/origin/{name}"
        if loc in refs and rem in refs and refs[loc][1] != refs[rem][1]:
            return rem if is_ancestor(project, loc, rem) else loc
        return loc if loc in refs else rem

    contained = {}   # name -> integration branch names (other than itself) whose refs contain its tip
    for full in [f for f, v in refs.items() if is_integration(v[0])]:
        iname = refs[full][0]
        for line in git(project, "for-each-ref", f"--merged={full}", "--format=%(refname)", "refs/heads", "refs/remotes/origin").splitlines():
            if line in refs and refs[line][0] != iname:
                contained.setdefault(refs[line][0], set()).add(iname)
    cutoff = now - timedelta(days=days)
    pr_open = prs or {}
    pr_merged = {}
    for c in window:
        m = PR_RE.match(c["subject"])
        if m and m.group(2) not in pr_merged:
            pr_merged[m.group(2)] = int(m.group(1))
    plan = plan_lookup(project)
    try:
        events = [(parse_ts(e.get("ts")), e.get("story"), e.get("state")) for e in rm_data.read_jsonl(rd(project) / "ledger" / "events.jsonl")]
        events = [e for e in events if e[0] and e[1] in plan["stories"]]
    except Err:
        events = []
    co = reflog_checkouts(project)
    spans = {}   # branch -> [(start, end)] while it was checked out
    for i, (d, to) in enumerate(co):
        spans.setdefault(to, []).append((d, co[i + 1][0] if i + 1 < len(co) else now))

    todo = []
    for n, b in by_name.items():
        merged_into = sorted(contained.get(n, ()))
        recent = (parse_ts(b["ts"]) or now) >= cutoff
        if n != head and ((merged_into and not recent) or (is_integration(n) and not recent)):
            continue
        todo.append((n, b, merged_into))

    def one(item):
        n, b, merged_into = item
        base = base_of(n)
        row = {"name": n, "head": n == head, "tip": b["sha"][:7], "ts": b["ts"], "local": b["local"], "remote": b["remote"],
               "base": base, "kind": "base" if is_integration(n) else "feature", "merged": bool(merged_into),
               "merged_into": merged_into}
        if base and base != n:
            cnt = git(project, "rev-list", "--left-right", "--count", f"{best_ref(base)}...{b['sha']}").split()
            if len(cnt) == 2:
                row["behind"], row["ahead"] = int(cnt[0]), int(cnt[1])
        if n in pr_open:
            row["pr"] = {"n": pr_open[n], "state": "open"}
        elif n in pr_merged:
            row["pr"] = {"n": pr_merged[n], "state": "merged"}
        if is_integration(n):
            return row
        # refs that do not contain the tip bound this branch's own commits (stacked branches split correctly)
        cont = set(git(project, "for-each-ref", f"--contains={b['sha']}", "--format=%(refname)", "refs/heads", "refs/remotes/origin").splitlines())
        others = sorted({v[1] for full, v in refs.items() if full not in cont})
        own = []
        if others:
            for line in git(project, "log", b["sha"], "--not", *others, f"--max-count={MAX_OWN}", "--date=iso-strict",
                            "--format=%h" + US + "%aI" + US + "%s").splitlines():
                f = (line.split(US) + ["", "", ""])[:3]
                own.append({"short": f[0], "ts": parse_ts(f[1]), "subject": f[2]})
            total = git(project, "rev-list", "--count", b["sha"], "--not", *others).strip()
            row["own"] = int(total) if total.isdigit() else len(own)
        same = sorted({v[0] for v in refs.values() if v[1] == b["sha"] and v[0] != n and not is_integration(v[0])})
        if same:
            row["same_tip"] = same
        row["_own"] = own
        return row

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, todo))

    # stack: the nearest other unmerged feature branch whose tip is an ancestor of this tip
    sha_of = {r["name"]: by_name[r["name"]]["sha"] for r in rows}
    live = [r["name"] for r in rows if r["kind"] == "feature" and not r["merged"]]
    for r in rows:
        if r["kind"] != "feature":
            continue
        mine = sha_of[r["name"]]
        anc = [m for m in live if m != r["name"] and sha_of[m] != mine and is_ancestor(project, sha_of[m], mine)]
        if anc:
            r["stack"] = min(anc, key=lambda m: int(git(project, "rev-list", "--count", f"{sha_of[m]}..{mine}").strip() or 0))

    stories, fdefs = plan["stories"], plan["features"]
    for r in rows:
        own = r.pop("_own", [])
        if r["kind"] != "feature":
            continue
        links, feats = {}, {}    # id -> {via: tip text}

        def add_story(sid, via, tip):
            links.setdefault(sid, {}).setdefault(via, tip)

        def add_feat(fid, via, tip):
            if fid in fdefs:
                feats.setdefault(fid, {}).setdefault(via, tip)

        for c in own:   # 1. story and feature ids in the branch's own commit subjects
            for sid in ids_in(c["subject"], stories):
                add_story(sid, "subject", f"{c['short']} {trunc(c['subject'], 70)}")
            for m in FID_RE.finditer(c["subject"]):
                add_feat("f" + m.group(1), "subject", f"{c['short']} {trunc(c['subject'], 70)}")
        spans_b = spans.get(r["name"], [])   # 2. the ledger: status changes while checked out, or just before an own commit
        for d, sid, state in events:
            when = d.astimezone().strftime("%b %d %H:%M")
            hit = next((f"{state} {when}, checked out" for a, z in spans_b if a <= d < z), None)
            if not hit:
                for c in own:
                    if c["ts"] and 0 <= (c["ts"] - d).total_seconds() <= NEAR_SECONDS:
                        hit = f"{state} {when}, just before {c['short']}"
                        break
            if hit:
                add_story(sid, "ledger", hit)
        if not r["name"].startswith("worktree-agent"):   # 3. the branch name against feature and story names
            for fid, (fname, _) in fdefs.items():
                if name_matches(r["name"], fname):
                    add_feat(fid, "name", trunc(fname, 70))
            hits = [sid for sid, (sname, _) in stories.items() if name_matches(r["name"], sname)]
            if 0 < len(hits) <= 6:
                for sid in hits:
                    add_story(sid, "name", trunc(stories[sid][0], 70))
        for fid, (_, fb) in fdefs.items():   # 4. the plan's own branch field, when a feature carries one
            if fb and r["name"] in ([fb] if isinstance(fb, str) else fb if isinstance(fb, list) else []):
                add_feat(fid, "plan", "feature branch field")
        ranked = sorted(links.items(), key=lambda kv: (min(VIA_ORDER[v] for v in kv[1]), -int(kv[0][1:])))
        out_links = []
        for sid, vias in ranked:
            via = min(vias, key=lambda v: VIA_ORDER[v])
            if len(out_links) < MAX_LINKS:
                out_links.append({"s": sid, "n": trunc(stories[sid][0], 60), "f": stories[sid][1], "via": via, "why": vias[via]})
            if stories[sid][1]:
                add_feat(stories[sid][1], via, f"story {sid}")
        if len(ranked) > MAX_LINKS:
            r["more"] = len(ranked) - MAX_LINKS
        r["links"] = out_links
        r["features"] = [{"id": fid, "n": fdefs[fid][0], "via": min(vias, key=lambda v: VIA_ORDER[v]),
                          "why": vias[min(vias, key=lambda v: VIA_ORDER[v])]}
                         for fid, vias in sorted(feats.items(), key=lambda kv: (min(VIA_ORDER[v] for v in kv[1]), kv[0]))]
    rows.sort(key=lambda r: (r["kind"] == "base", r["merged"], -(parse_ts(r["ts"]) or now).timestamp()))
    return {"base": default_base, "days": days, "branches": rows}


def collect_events(project, commits, cutoff):
    events = []
    out = git(project, "reflog", "--date=iso-strict", "--format=%gd%x1f%gs")
    for line in out.splitlines():
        sel, _, gs = line.partition(US)
        m = re.search(r"@\{(.*)\}", sel)
        ts = m.group(1) if m else ""
        d = parse_ts(ts)
        if not d or d < cutoff:
            continue
        for prefix, kind in EVENT_PREFIXES:
            if gs.startswith(prefix):
                ref = ""
                if kind == "checkout":
                    mm = re.search(r" to (.+)$", gs)
                    ref = mm.group(1) if mm else ""
                elif kind == "merge":
                    ref = gs[len("merge"):].split(":", 1)[0].strip()
                events.append({"ts": ts, "kind": kind, "ref": ref, "text": gs})
                break
    for c in commits:
        if len(c["parents"]) > 1:
            events.append({"ts": c["ts"], "kind": "merge", "ref": c["refs"][0] if c["refs"] else c["short"],
                           "text": c["subject"]})
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events


def commit_key(c):
    return "c:" + c["sha"]


def event_key(e):
    h = hashlib.sha1(f"{e['ts']}|{e['kind']}|{e['text']}".encode("utf-8")).hexdigest()[:16]
    return "e:" + h


def archive_old(project, prev, cutoff):
    """Append rows of the previous git.json older than cutoff to the archive; return rows added."""
    path = rd(project) / "archive" / "git-events.jsonl"
    seen = {r.get("key") for r in rm_data.read_jsonl(path)}
    added = 0
    for kind, rows, keyf in (("commit", prev.get("commits", []), commit_key), ("event", prev.get("events", []), event_key)):
        for row in rows:
            d = parse_ts(row.get("ts", ""))
            if not d or d >= cutoff:
                continue
            k = keyf(row)
            if k in seen:
                continue
            seen.add(k)
            out = {"key": k, "kind": kind, "ts": row.get("ts")}
            for kk, vv in row.items():
                if kk not in out:
                    out[kk] = vv
                elif kk == "kind":
                    out["event_kind"] = vv  # the row's own kind must not clobber "commit|event"
            rm_data.append_jsonl(path, out)
            added += 1
    return added


def run_git(project, days_arg=None, max_arg=None):
    d = rd(project)
    days = get_days(project, days_arg)
    cap = get_max(project, max_arg)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    prev = {}
    if (d / "git.json").exists():
        try:
            prev = rm_data.read_json(d / "git.json")
        except Err:
            prev = {}
    archived = archive_old(project, prev, cutoff)
    commits, lanes, window = collect_commits(project, days, cap)
    branches = collect_branches(project)
    events = collect_events(project, commits, cutoff)
    head = git(project, "rev-parse", "--abbrev-ref", "HEAD").strip()
    active = collect_active(project, window, days, head, now, open_prs(project))
    doc = {"schema": 2, "generated": rm_data.now_minute(), "days": days,
           "since": (now - timedelta(days=days)).strftime("%Y-%m-%d"), "head": head,
           "branches": branches, "commits": commits, "events": events,
           "totals": {"commits": len(commits), "merges": sum(1 for c in commits if len(c["parents"]) > 1)},
           "window_commits": len(window), "lanes": lanes, "max_commits": cap, "active": active}
    rm_data.write_json(d / "git.json", doc)
    return doc, archived


def cmd_git(args, project):
    doc, archived = run_git(project, getattr(args, "days", None), getattr(args, "max", None))
    rm_data.ok(f"git {len(doc['commits'])} commits, {len(doc['events'])} events, {len(doc['branches'])} branches "
               f"(days {doc['days']}); archived {archived} rows", ["git.json"])


def refresh(project):
    cmd_git(argparse.Namespace(days=None, max=None, cmd="git"), project)


def register(sub):
    p = sub.add_parser("git", help="collect recent git activity into git.json (older rows go to archive/git-events.jsonl)")
    p.add_argument("--days", type=int, default=None, help="window in days (default: ledger/config.json git_days, else 14)")
    p.add_argument("--max", type=int, default=None,
                   help="cap on in-window commits kept (default: ledger/config.json git_max_commits, else 150)")
    p.set_defaults(func=cmd_git)


# ---------------------------------------------------------------- selftest
def selftest():
    if not shutil.which("git"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="rm_git_selftest_"))
    try:
        def check(c, msg):
            if not c:
                raise AssertionError(msg)

        def g(*a, when=None):
            env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="T",
                       GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
            if when:
                env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
            r = subprocess.run(["git", "-C", str(tmp)] + list(a), capture_output=True, text=True, env=env,
                               encoding="utf-8", errors="replace")
            check(r.returncode == 0, f"git {a} failed: {r.stderr}")

        def commit(name, when=None):
            (tmp / name).write_text(name + "\n", encoding="utf-8")
            g("add", name)
            g("commit", "-m", f"add {name}", when=when)

        g("init", "-q", "-b", "main")
        old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        commit("old.txt", old)
        commit("b.txt")
        g("checkout", "-q", "-b", "feat")
        commit("c.txt")
        g("checkout", "-q", "main")
        g("merge", "--no-ff", "-m", "merge feat", "feat")
        rm_data.write_json(rd(tmp) / "ledger" / "config.json", {"git_days": 14})
        arch = rd(tmp) / "archive" / "git-events.jsonl"

        doc, n = run_git(tmp, 60)
        check(len(doc["commits"]) == 4 and doc["totals"] == {"commits": 4, "merges": 1}, f"60d counts {doc['totals']}")
        check(n == 0 and not arch.exists(), "nothing archived first run")
        check(doc["head"] == "main" and {b["name"] for b in doc["branches"]} == {"main", "feat"}, "head/branches")
        check(any(e["kind"] == "merge" for e in doc["events"]) and any(e["kind"] == "checkout" for e in doc["events"]),
              "events")
        check(all(c["files"] >= 1 and c["ins"] >= 1 for c in doc["commits"] if len(c["parents"]) == 1), "shortstat")
        doc, n = run_git(tmp, None)  # config.json -> 14 days
        check(doc["days"] == 14 and len(doc["commits"]) == 3 and n == 1, f"14d run {len(doc['commits'])} archived {n}")
        check(len(arch.read_text(encoding="utf-8").splitlines()) == 1, "one archive line")
        run_git(tmp, 14)
        check(len(arch.read_text(encoding="utf-8").splitlines()) == 1, "no duplicates on re-run")
        doc, n = run_git(tmp, 60)
        check(len(doc["commits"]) == 4 and n == 0, "60d run restores old commit")
        doc, n = run_git(tmp, 14)
        check(n == 0 and len(arch.read_text(encoding="utf-8").splitlines()) == 1, "re-archive is deduped")
        row = json.loads(arch.read_text(encoding="utf-8").splitlines()[0])
        check(row["kind"] == "commit" and row["key"].startswith("c:") and row["subject"] == "add old.txt", "archive row")
        # branch graph: side branch (2 commits), --no-ff merge, more main, second side branch after the merge
        g("checkout", "-q", "-b", "side1")
        commit("s1.txt")
        commit("s2.txt")
        g("checkout", "-q", "main")
        commit("m1.txt")
        g("merge", "--no-ff", "-m", "merge side1", "side1")
        commit("m2.txt")
        g("checkout", "-q", "-b", "side2")
        commit("t1.txt")
        g("checkout", "-q", "main")
        commit("m3.txt")
        doc, n = run_git(tmp, 14)
        cs = doc["commits"]
        ids = {c["id"] for c in cs}
        check(doc["schema"] == 2 and doc["max_commits"] == 150, "schema 2 / max_commits")
        check(all(isinstance(c["lane"], int) and c["id"] == c["sha"][:8] for c in cs), "lane int / id")
        mg = [c for c in cs if c["subject"] == "merge side1"][0]
        check(len(mg["edges"]) == 2 and mg["edges"][0][1] != mg["edges"][1][1], f"merge edges {mg['edges']}")
        s1 = [c for c in cs if c["subject"] == "add s1.txt"][0]
        t1 = [c for c in cs if c["subject"] == "add t1.txt"][0]
        check(s1["lane"] != 0 and t1["lane"] == s1["lane"], f"lane reuse {s1['lane']} {t1['lane']}")
        check(doc["lanes"] == max(max(c["lane"] for c in cs), max(e[1] for c in cs for e in c["edges"])) + 1,
              f"lanes {doc['lanes']}")
        check(all(len(p) == 8 for c in cs for p in c["parents"]), "parent ids are 8 chars")
        m3 = [c for c in cs if c["subject"] == "add m3.txt"][0]
        check(m3.get("branch") == "main" and mg.get("branch") == "main", f"main commits labelled {m3.get('branch')}")
        check(s1.get("branch") == "side1" and t1.get("branch") == "side2", f"side branch labels {s1.get('branch')} {t1.get('branch')}")
        check(sum(1 for c in cs for p in c["parents"] if p not in ids) == 1, "one stub (old commit outside window)")
        check(len(arch.read_text(encoding="utf-8").splitlines()) == 1, "archive still one row, no duplicates")
        doc, n = run_git(tmp, 14, 3)
        check(len(doc["commits"]) == 3 and doc["max_commits"] == 3, "cap keeps newest 3")
        check(len(arch.read_text(encoding="utf-8").splitlines()) == 1, "cap does not archive")
        # empty repo / not a repo: never raises
        empty = Path(tempfile.mkdtemp(prefix="rm_git_empty_"))
        try:
            doc, n = run_git(empty, 14)
            check(doc["commits"] == [] and doc["branches"] == [], "non-repo is empty")
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _selftest_history()


def _selftest_history():
    """A small fixture history pinned against `git log --graph`: a side branch and a --no-ff merge, a stacked branch
    (built on another branch's tip), a merge INTO a feature branch, then the active-branch derivation on top of it."""
    if not shutil.which("git"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="rm_git_history_"))
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        t0 = now - timedelta(days=5)
        tick = [0]

        def check(c, msg):
            if not c:
                raise AssertionError(msg)

        def iso(dt):
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        def g(*a, when=None):
            env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="T",
                       GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
            if when:
                env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = iso(when)
            r = subprocess.run(["git", "-C", str(tmp)] + list(a), capture_output=True, text=True, env=env,
                               encoding="utf-8", errors="replace")
            check(r.returncode == 0, f"git {a} failed: {r.stderr}")

        def at():
            tick[0] += 1
            return t0 + timedelta(hours=tick[0])

        def commit(msg, when=None):
            name = msg.split()[0] + ".txt"
            (tmp / name).write_text(msg + "\n", encoding="utf-8")
            g("add", name)
            g("commit", "-q", "-m", msg, when=when or at())

        g("init", "-q", "-b", "main")
        commit("root")
        g("checkout", "-q", "-b", "old-merged", when=at())
        commit("o1 long ago", when=now - timedelta(days=30))
        g("checkout", "-q", "main", when=at())
        g("merge", "-q", "--no-ff", "-m", "merge old-merged", "old-merged", when=at())
        g("checkout", "-q", "-b", "old-open", when=at())
        commit("o2 long ago and unmerged", when=now - timedelta(days=31))
        g("checkout", "-q", "main", when=at())
        commit("main-2")
        g("checkout", "-q", "-b", "feat", when=at())
        commit("f1 feat one")
        commit("f2 feat two")
        g("checkout", "-q", "main", when=at())
        commit("main-3")
        g("merge", "-q", "--no-ff", "-m", "merge feat", "feat", when=at())
        g("checkout", "-q", "-b", "stackA", when=at())
        commit("a1 stack a (s7)")
        g("checkout", "-q", "-b", "stackB", when=at())
        commit("b1 stack b")
        g("checkout", "-q", "main", when=at())
        g("checkout", "-q", "-b", "side", when=at())
        commit("s1 side")
        g("checkout", "-q", "main", when=at())
        g("checkout", "-q", "-b", "inner", when=at())
        commit("i1 inner")
        g("checkout", "-q", "side", when=at())
        g("merge", "-q", "--no-ff", "-m", "merge inner into side", "inner", when=at())
        g("checkout", "-q", "main", when=at())
        g("checkout", "-q", "-b", "feature/gizmo", when=at())
        commit("g1 first pass")
        g("checkout", "-q", "main", when=at())
        g("checkout", "-q", "-b", "wip-x", when=at())
        commit("x1 misc")
        g("checkout", "-q", "main", when=at())
        # a branch worked on while a story changed status in the ledger (no story id anywhere in its commit)
        led_from = now - timedelta(hours=3)
        g("checkout", "-q", "-b", "ledger-b", when=led_from)
        commit("l1 ledger work", when=led_from + timedelta(minutes=45))
        g("checkout", "-q", "main", when=led_from + timedelta(hours=1))
        commit("main-4", when=led_from + timedelta(hours=2))
        rm_data.write_json(rd(tmp) / "plan.json", {
            "features": [{"id": "f1", "name": "Pipeline"}, {"id": "f2", "name": "Gizmo"}],
            "stories": [{"id": "s7", "feature": "f1", "name": "Seven pipeline"}, {"id": "s8", "feature": "f1", "name": "Ledger step"},
                        {"id": "s9", "feature": "f2", "name": "Gizmo builder"}]})
        rm_data.write_json(rd(tmp) / "ledger" / "config.json", {"git_days": 14})
        ev = {"ts": (led_from + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "story": "s8", "state": "progress", "note": ""}
        (rd(tmp) / "ledger" / "events.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")

        doc, _ = run_git(tmp, 14)
        cs = doc["commits"]
        by = {c["subject"]: c for c in cs}
        ids = {c["id"] for c in cs}
        # invariants that hold for any history: edges are the parents in order; an edge ends in its parent's lane
        for c in cs:
            check([e[0] for e in c["edges"]] == c["parents"], f"edges are the parents of {c['subject']}")
            for e in c["edges"]:
                if e[0] in ids:
                    check(next(x for x in cs if x["id"] == e[0])["lane"] == e[1], f"edge lane of {c['subject']}")
        check(all(len({e[1] for e in c["edges"]}) == len(c["edges"]) for c in cs), "a merge's edges use distinct lanes")
        # pinned against `git log --graph --topo-order`: diverging lanes and the merges
        mf, mi = by["merge feat"], by["merge inner into side"]
        check([e[1] for e in mf["edges"]] == [0, 1] and mf["lane"] == 0, f"merge feat lanes {mf['lane']} {mf['edges']}")
        check(by["f1 feat one"]["lane"] == 1 and by["f2 feat two"]["lane"] == 1 and by["main-3"]["lane"] == 0,
              "feat diverges to lane 1, main stays in lane 0")
        check(by["main-3"]["edges"][0][1] == 1, "main-3 converges into the lane f1 was waiting on")
        check(mi["edges"][0][1] == mi["lane"] == by["s1 side"]["lane"] and mi["edges"][1][1] > mi["lane"],
              f"merge into a feature branch {mi['lane']} {mi['edges']}")
        check(by["i1 inner"]["lane"] == mi["edges"][1][1] and by["i1 inner"]["edges"][0][1] == 0,
              "inner branch has its own lane and rejoins the trunk lane")
        check(by["a1 stack a (s7)"]["lane"] == by["b1 stack b"]["lane"], "stacked branches share a lane (linear in git too)")
        check(doc["lanes"] >= 3, f"lanes {doc['lanes']}")
        check(sum(1 for c in cs if len(c["parents"]) > 1) == doc["totals"]["merges"] == 3, f"three merges {[c['subject'] for c in cs if len(c['parents']) > 1]}")
        # branch labels (printed beside the graph)
        want = {"f1 feat one": "feat", "a1 stack a (s7)": "stackA", "b1 stack b": "stackB", "s1 side": "side", "i1 inner": "inner",
                "main-3": "main", "merge feat": "main", "g1 first pass": "feature/gizmo"}
        for subj, name in want.items():
            check(by[subj].get("branch") == name, f"{subj} labelled {by[subj].get('branch')} not {name}")
        # the cap keeps the newest commits, while totals still cover the whole window
        small, _ = run_git(tmp, 14, 4)
        check(len(small["commits"]) == 4 and small["window_commits"] == doc["window_commits"] > 4, "cap vs window_commits")
        # active branches
        act = {b["name"]: b for b in doc["active"]["branches"]}
        check(doc["active"]["base"] == "main", "base is main without dev or phase branches")
        check("old-merged" not in act, "merged and older than the window: not active")
        check(act["old-open"]["merged"] is False, "unmerged old branch stays active")
        check(act["feat"]["merged"] and act["feat"]["merged_into"] == ["main"] and act["feat"]["ahead"] == 0, "merged branch is flagged")
        check(act["stackB"]["stack"] == "stackA" and act["stackB"]["own"] == 1 and act["stackB"]["ahead"] == 2, f"stack {act['stackB']}")
        check(act["stackB"]["behind"] >= 1 and act["stackB"]["base"] == "main", "behind base")
        check(act["main"]["head"] and act["main"]["kind"] == "base", "HEAD is marked and main is a base branch")
        la = {lk["s"]: lk for lk in act["stackA"]["links"]}
        check(la["s7"]["via"] == "subject" and [f["id"] for f in act["stackA"]["features"]] == ["f1"], f"subject link {act['stackA']['links']}")
        gz = act["feature/gizmo"]
        check({(f["id"], f["via"]) for f in gz["features"]} == {("f2", "name")} and [(lk["s"], lk["via"]) for lk in gz["links"]] == [("s9", "name")],
              f"name link {gz['links']} {gz['features']}")
        lb = act["ledger-b"]
        check([(lk["s"], lk["via"]) for lk in lb["links"]] == [("s8", "ledger")], f"ledger link {lb['links']}")
        check(act["wip-x"]["links"] == [] and act["wip-x"]["features"] == [], "no link: the page prints unlinked")
        names = [b["name"] for b in doc["active"]["branches"]]
        check(names[-1] == "main", "base branches sort last")
        # a plan that names a branch on a feature links it as well (lowest priority)
        pl = json.loads((rd(tmp) / "plan.json").read_text(encoding="utf-8"))
        pl["features"][0]["branch"] = "wip-x"
        rm_data.write_json(rd(tmp) / "plan.json", pl)
        doc, _ = run_git(tmp, 14)
        wx = [b for b in doc["active"]["branches"] if b["name"] == "wip-x"][0]
        check([(f["id"], f["via"]) for f in wx["features"]] == [("f1", "plan")], f"plan branch field {wx['features']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
