"""rm_publish: shell sync, publish arguments, local server and refresh for the roadmap dashboard.

Commands: sync-shell, init, add-tab, publish-args, mark-published, serve, refresh.
Pure standard library. Command functions are func(args, project); failures raise rm_data.Err.
"""
import argparse
import contextlib
import http.server
import io
import json
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import rm_data
from rm_data import Err, rd

SHELL_DIR = Path(__file__).resolve().parent.parent / "assets" / "shell"
SHELL_COPY = ["index.html", "styles.css", "app.js", "tab-plan.js", "tab-flow.js", "tab-map.js", "tab-git.js", "tab-commands.js",
              "tab-tasks.js"]
PROJECT_OWNED = "tabs.json"
# every published file except the page itself (index.html is passed as file_path)
PUBLISHED = ["styles.css", "app.js", "tabs.json", "tab-plan.js", "tab-flow.js", "tab-map.js", "tab-git.js", "tab-commands.js",
             "tab-tasks.js", "plan.json", "tokens.json", "plan-archive.json", "map.json", "git.json", "activity.json"]
LAZY_GLOB_RE = re.compile(r"^[A-Za-z0-9_-]*\*[A-Za-z0-9_-]*\.json$")
DEFAULT_CONFIG = {"agent_effort": {}, "orchestrator_effort": "unspecified", "idle_cap_seconds": 120, "git_days": 14,
                   "activity_days": 30, "activity_max_recent": 100}

WRAP_HEAD = ('<!doctype html><html><head><meta charset=utf-8>'
             '<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
             '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);'
             'padding-bottom:env(safe-area-inset-bottom,0px)}'
             'body{margin:0;font:14px system-ui,sans-serif;background:#f7f7f5}img{max-width:100%}'
             '[hidden]{display:none!important}</style></head><body>')
WRAP_TAIL = '</body></html>'


# ---------------------------------------------------------------- sync-shell / init / add-tab
def do_sync(project, force):
    d = rd(project)
    d.mkdir(parents=True, exist_ok=True)
    copied, same, differs = [], [], []
    for name in SHELL_COPY:
        src = SHELL_DIR / name
        if not src.exists():
            raise Err(f"shell source missing: {src}")
        dst = d / name
        if not dst.exists():
            shutil.copyfile(src, dst); copied.append(name)
        elif dst.read_bytes() == src.read_bytes():
            same.append(name)
        elif force:
            shutil.copyfile(src, dst); copied.append(name)
        else:
            differs.append(name)
    tabs = d / PROJECT_OWNED
    if tabs.exists():
        tabs_note = f"{PROJECT_OWNED} kept"
    else:
        src = SHELL_DIR / PROJECT_OWNED
        if not src.exists():
            raise Err(f"shell source missing: {src}")
        shutil.copyfile(src, tabs)
        copied.append(PROJECT_OWNED); tabs_note = f"{PROJECT_OWNED} created"
    what = "sync-shell copied " + (",".join(copied) if copied else "nothing")
    what += f"; unchanged {len(same)}; {tabs_note}"
    if differs:
        what += "; differs from skill (use --force to overwrite): " + ",".join(differs)
    return what


def cmd_sync_shell(args, project):
    rm_data.ok(do_sync(project, args.force))


def cmd_init(args, project):
    d = rd(project)
    made = []
    cfg = d / "ledger" / "config.json"
    if not cfg.exists():
        rm_data.write_json(cfg, DEFAULT_CONFIG); made.append("ledger/config.json")
    if not (d / "plan.json").exists():
        rm_data.save(project, rm_data.empty_plan(Path(project).resolve().name), rm_data.empty_archive())
        made.append("plan.json"); made.append("plan-archive.json")
    shell = do_sync(project, False)
    rm_data.ok("init " + (",".join(made) if made else "nothing new (already initialised)") + "; " + shell)


def cmd_add_tab(args, project):
    d = rd(project)
    path = d / PROJECT_OWNED
    cfg = rm_data.read_json(path)
    if not re.match(r"^[a-z][a-z0-9-]*$", args.id):
        raise Err("tab id must be lowercase letters, digits or dashes")
    if any(t.get("id") == args.id for t in cfg.get("tabs", [])):
        raise Err(f"tab {args.id} already exists in tabs.json")

    def pairs(items, flag):
        out = {}
        for it in items or []:
            if "=" not in it:
                raise Err(f"{flag} needs key=file.json, got {it!r}")
            k, v = it.split("=", 1)
            if not k or not v.endswith(".json") or "/" in v or "\\" in v:
                raise Err(f"{flag} {it!r}: use key=file.json with a flat file name")
            out[k] = v
        return out

    if not args.script.endswith(".js") or "/" in args.script or "\\" in args.script:
        raise Err("--script must be a flat .js file name")
    tab = {"id": args.id, "title": args.title, "script": args.script, "data": pairs(args.data, "--data")}
    if not tab["data"]:
        raise Err("give at least one --data key=file.json")
    lazy = pairs(args.lazy, "--lazy")
    if lazy:
        tab["lazy"] = lazy
    if args.lazy_glob:
        if not LAZY_GLOB_RE.match(args.lazy_glob):
            raise Err("--lazy-glob must be a flat pattern like 'tasks-archive-*.json' (one *, no slashes)")
        tab["lazyGlob"] = args.lazy_glob
    cfg.setdefault("tabs", []).append(tab)
    rm_data.write_json(path, cfg)
    rm_data.ok(f"add-tab {args.id}", [PROJECT_OWNED])


# ---------------------------------------------------------------- publish-args / mark-published
def published_names(d):
    """PUBLISHED plus the script, data and lazy files of any tab listed in tabs.json (project-owned tabs)."""
    names = list(PUBLISHED)
    try:
        tabs = json.loads((d / PROJECT_OWNED).read_text(encoding="utf-8")).get("tabs", [])
    except Exception:
        tabs = []
    for tab in tabs:
        for n in [tab.get("script")] + list((tab.get("data") or {}).values()) + list((tab.get("lazy") or {}).values()):
            if not n or n in names:
                continue
            # only flat .js/.json files next to index.html: a hand-edited tabs.json must not publish anything else
            if Path(n).name != n or n.startswith(".") or Path(n).suffix not in (".js", ".json"):
                raise Err(f"tabs.json names {n!r}; tab files must be flat .js or .json names in .claude/roadmap")
            names.append(n)
        glob = tab.get("lazyGlob")
        if glob:
            if not LAZY_GLOB_RE.match(glob):
                raise Err(f"tabs.json lazyGlob {glob!r}; must be a flat pattern like 'tasks-archive-*.json'")
            for p in sorted(d.glob(glob)):
                if p.name not in names:
                    names.append(p.name)
    return names


def published_json(project):
    p = rd(project) / "ledger" / "published.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def cmd_publish_args(args, project):
    d = rd(project)
    if not (d / "index.html").exists():
        raise Err("index.html missing: run sync-shell first")
    pub = published_json(project)
    old = (pub or {}).get("files", {})
    listed = published_names(d)
    existing = [n for n in listed if (d / n).exists()]
    missing = [n for n in listed if not (d / n).exists()]
    if args.all or pub is None:
        names = existing
    else:
        names = [n for n in existing if old.get(n) != rm_data.sha(d / n)]
    changed = list(names)
    if pub is None or args.all or old.get("index.html") != rm_data.sha(d / "index.html"):
        changed = ["index.html"] + changed
    out = {"url": (pub or {}).get("url"), "file_path": str((d / "index.html").resolve()),
           "files": {n: {"from": str((d / n).resolve())} for n in names},
           "changed": changed, "missing": missing, "capabilities": {"comments": {}, "db": {}}}
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))


def set_manifest_url(project, url):
    """Set artifact_url of the roadmap dashboard in .claude/project-manifest.json (text edit, that one field)."""
    mp = Path(project) / ".claude" / "project-manifest.json"
    if not mp.exists():
        return "no project-manifest.json (skipped)"
    text = mp.read_text(encoding="utf-8")
    try:
        dash = [x for x in json.loads(text).get("dashboards", []) if x.get("kind") == "roadmap"]
    except Exception:
        raise Err("project-manifest.json does not parse")
    if not dash:
        return "manifest has no roadmap dashboard (skipped)"
    m = re.search(r'"kind"\s*:\s*"roadmap"', text)
    # the field may sit before or after "kind" inside the same object: bound the search to that object
    start = text.rfind("{", 0, m.start())
    end = text.find("}", m.end())
    obj = text[start:end + 1]
    pat = re.compile(r'("artifact_url"\s*:\s*)"[^"]*"')
    if pat.search(obj):
        new_obj = pat.sub(lambda mm: mm.group(1) + json.dumps(url), obj, count=1)
    else:
        indent = re.search(r'\n([ \t]+)"kind"', obj)
        pad = indent.group(1) if indent else "  "
        new_obj = re.sub(r'("kind"\s*:\s*"roadmap"\s*,?)', lambda mm: mm.group(1).rstrip(",") +
                         f',\n{pad}"artifact_url": {json.dumps(url)}' + ("," if mm.group(1).endswith(",") else ""),
                         obj, count=1)
    mp.write_text(text[:start] + new_obj + text[end + 1:], encoding="utf-8", newline="")
    return "manifest artifact_url set"


def cmd_mark_published(args, project):
    d = rd(project)
    url = args.url
    if url is None:
        pub = published_json(project)
        url = (pub or {}).get("url")
        if not url:
            raise Err("no stored url: pass --url")
    names = ["index.html"] + published_names(d)
    files = {n: rm_data.sha(d / n) for n in names if (d / n).exists()}
    rm_data.write_json(d / "ledger" / "published.json", {"url": url, "at": rm_data.now_minute(), "files": files})
    note = set_manifest_url(project, url)
    rm_data.ok(f"mark-published {len(files)} files; {note}", ["ledger/published.json"])


# ---------------------------------------------------------------- serve
def make_handler(root):
    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".js": "text/javascript", ".json": "application/json", ".css": "text/css",
                          ".html": "text/html"}

        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def do_GET(self):
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path in ("/", "/index.html"):
                stub = Path(root, "index.html")
                if not stub.exists():
                    self.send_error(404, "index.html missing: run sync-shell")
                    return
                body = (WRAP_HEAD + stub.read_text(encoding="utf-8") + WRAP_TAIL).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def end_headers(self):
            if self.path.split("?", 1)[0].endswith(".json"):
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def log_message(self, *a):
            pass

    return H


def cmd_serve(args, project):
    d = rd(project)
    if not d.exists():
        raise Err(f"{d} not found")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(d))
    print(f"serving {d} at http://localhost:{srv.server_address[1]}/ (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


# ---------------------------------------------------------------- refresh
def cmd_refresh(args, project):
    try:
        import rm_tokens
        rm_tokens.cmd_tokens(argparse.Namespace(compare_legacy=False, cmd="tokens"), project)
    except ModuleNotFoundError as e:
        if e.name != "rm_tokens":
            raise
        print("tokens: rm_tokens not built yet")
    for name in ("rm_git", "rm_activity", "rm_flow", "rm_map"):
        try:
            mod = __import__(name)
        except ModuleNotFoundError as e:
            if e.name != name:
                raise
            print({"rm_git": "git: rm_git not built yet", "rm_activity": "activity: rm_activity not built yet",
                   "rm_flow": "flow: rm_flow not built yet",
                   "rm_map": "map: not built yet"}[name])
            continue
        if hasattr(mod, "refresh"):
            mod.refresh(project)
        else:
            print(f"{name}: no refresh() yet, skipped")
    rm_data.cmd_validate(argparse.Namespace(cmd="validate"), project)


# ---------------------------------------------------------------- registry
def register(sub):
    def add(name, func, help_=""):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=func)
        return p

    p = add("sync-shell", cmd_sync_shell, "copy the shell from the skill into .claude/roadmap (tabs.json is never overwritten)")
    p.add_argument("--force", action="store_true", help="overwrite shell files that differ from the skill copy")
    add("init", cmd_init, "set up an empty project: config, empty plan, tabs.json, shell")
    p = add("add-tab", cmd_add_tab, "add a tab to tabs.json")
    p.add_argument("--id", required=True); p.add_argument("--title", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--data", action="append", metavar="key=file.json")
    p.add_argument("--lazy", action="append", metavar="key=file.json")
    p.add_argument("--lazy-glob", metavar="PATTERN", help="a growable set of files a tab may fetch one at a time by "
                    "exact name (ctx.load falls back to any name not declared in --lazy); flat pattern with one *, "
                    "e.g. tasks-archive-*.json")
    p = add("publish-args", cmd_publish_args, "print the JSON arguments for the Artifact publish call")
    p.add_argument("--all", action="store_true", help="every published file, not only the changed ones")
    p = add("mark-published", cmd_mark_published, "record a publish: file hashes, url, manifest artifact_url")
    p.add_argument("--url", help="defaults to the url already stored in ledger/published.json")
    p = add("serve", cmd_serve, "serve .claude/roadmap locally, wrapping index.html like the publisher")
    p.add_argument("--port", type=int, default=8765)
    add("refresh", cmd_refresh, "tokens, git, activity, flow, map (when built), then validate")


# ---------------------------------------------------------------- selftest
def selftest():
    tmp = Path(tempfile.mkdtemp(prefix="rm_publish_selftest_"))
    try:
        proj = tmp / "proj"
        proj.mkdir()
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

        d = rd(proj)
        check(run("init").startswith("ok init"), "init")
        for n in SHELL_COPY + [PROJECT_OWNED, "plan.json", "plan-archive.json", "ledger/config.json"]:
            check((d / n).exists(), f"init made {n}")
        rm_data.load(proj)  # empty plan is valid
        check("copied nothing" in run("sync-shell"), "sync idempotent")
        check(run("init").count("\n") == 1, "init one line")
        (d / "tabs.json").write_text('{"title":"mine","tabs":[]}', encoding="utf-8")
        (d / "app.js").write_text("// local edit", encoding="utf-8")
        out = run("sync-shell")
        check("differs" in out and (d / "app.js").read_text() == "// local edit", "no overwrite without --force")
        out = run("sync-shell", "--force")
        check("app.js" in out and (d / "app.js").read_bytes() == (SHELL_DIR / "app.js").read_bytes(), "force overwrites")
        check(json.loads((d / "tabs.json").read_text())["title"] == "mine", "tabs.json never overwritten")
        run("add-tab", "--id", "x", "--title", "X", "--script", "tab-x.js", "--data", "x=x.json", "--lazy", "y=y.json")
        run("add-tab", "--id", "x", "--title", "X", "--script", "tab-x.js", "--data", "x=x.json", fail=True)
        run("add-tab", "--id", "z", "--title", "Z", "--script", "sub/tab.js", "--data", "z=z.json", fail=True)
        t = json.loads((d / "tabs.json").read_text())["tabs"][0]
        check(t["lazy"] == {"y": "y.json"} and t["data"] == {"x": "x.json"}, "add-tab content")

        pa = json.loads(run("publish-args", "--all"))
        check(pa["url"] is None and Path(pa["file_path"]).is_absolute() and pa["file_path"].endswith("index.html"), "args base")
        check("index.html" not in pa["files"] and "styles.css" in pa["files"], "index excluded from files")
        check(all(Path(v["from"]).is_absolute() for v in pa["files"].values()), "absolute paths")
        check(pa["capabilities"] == {"comments": {}, "db": {}}, "capabilities field")
        check("map.json" in pa["missing"] and "plan.json" not in pa["missing"], "missing list")
        check("tab-x.js" in pa["missing"] and "x.json" in pa["missing"] and "y.json" in pa["missing"], "project tab files are listed")
        (d / "tab-x.js").write_text("//", encoding="utf-8")
        pa = json.loads(run("publish-args", "--all"))
        check("tab-x.js" in pa["files"], "project tab script is published")

        run("add-tab", "--id", "growable", "--title", "Growable", "--script", "tab-x.js",
            "--data", "x=x.json", "--lazy-glob", "grow-*.json")
        pa = json.loads(run("publish-args", "--all"))
        check("grow-1.json" not in pa["files"], "lazyGlob matches nothing yet")
        (d / "grow-1.json").write_text("{}", encoding="utf-8")
        (d / "grow-2.json").write_text("{}", encoding="utf-8")
        pa = json.loads(run("publish-args", "--all"))
        check("grow-1.json" in pa["files"] and "grow-2.json" in pa["files"], "lazyGlob discovers new files")
        check(run("add-tab", "--id", "bad", "--title", "Bad", "--script", "tab-x.js", "--data", "x=x.json",
                  "--lazy-glob", "../evil.json", fail=True), "lazy-glob path traversal refused")
        cfg_path = d / "tabs.json"
        good = cfg_path.read_text(encoding="utf-8")
        cfg = json.loads(good)
        cfg["tabs"][0]["data"]["evil"] = "../../.env"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        check("flat" in run("publish-args", "--all", fail=True), "unsafe tab file name refused")
        cfg_path.write_text(good, encoding="utf-8")

        (proj / ".claude").mkdir(exist_ok=True)
        man = proj / ".claude" / "project-manifest.json"
        man.write_text('{\n  "dashboards": [\n    {\n      "name": "a",\n      "kind": "usage",\n      "artifact_url": "old-usage"\n    },\n'
                       '    {\n      "name": "b",\n      "kind": "roadmap",\n      "artifact_url": "old"\n    }\n  ]\n}\n', encoding="utf-8")
        run("mark-published", "--url", "https://example.test/a")
        m = json.loads(man.read_text())["dashboards"]
        check(m[1]["artifact_url"] == "https://example.test/a" and m[0]["artifact_url"] == "old-usage", "manifest only roadmap")
        pj = json.loads((d / "ledger" / "published.json").read_text())
        check(pj["url"] == "https://example.test/a" and "index.html" in pj["files"], "published.json")

        pub_path = d / "ledger" / "published.json"
        saved_pub = pub_path.read_text(encoding="utf-8")
        pub_path.unlink()
        check("no stored url" in run("mark-published", fail=True), "mark-published errors without url or stored")
        pub_path.write_text(saved_pub, encoding="utf-8")
        out = run("mark-published")
        check(out.startswith("ok mark-published"), "mark-published uses stored url: " + out)
        pj = json.loads(pub_path.read_text())
        check(pj["url"] == "https://example.test/a", "stored url reused")

        pa = json.loads(run("publish-args"))
        check(pa["files"] == {} and pa["changed"] == [] and pa["url"] == "https://example.test/a", "nothing changed")
        (d / "plan.json").write_text((d / "plan.json").read_text().replace("selftest", "proj2") + " ", encoding="utf-8")
        pa = json.loads(run("publish-args"))
        check(list(pa["files"]) == ["plan.json"] and pa["changed"] == ["plan.json"], "only changed file")

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(d))
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            with urllib.request.urlopen(base + "/") as r:
                body = r.read().decode("utf-8")
            check(body.startswith("<!doctype html><html><head>") and "<script src=\"app.js\">" in body
                  and body.endswith("</body></html>"), "wrapped index")
            with urllib.request.urlopen(base + "/tabs.json") as r:
                check(r.headers.get("Cache-Control") == "no-cache", "json no-cache")
        finally:
            srv.shutdown(); srv.server_close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
