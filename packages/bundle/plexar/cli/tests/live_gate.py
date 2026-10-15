import subprocess, sys, os, re, shutil, pathlib, tempfile
"""Live end-to-end gate for the plexar-harness CLI: drives the real harness against the rig (needs PLEXAR_HARNESS_KEY).
Usage: python packages/bundle/plexar/cli/tests/live_gate.py   (exit 0 = every check passed)"""
CLI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="plexar-cli-gate-")
SETTINGS = os.path.join(WORK, "gate-settings.json")
fails = []

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name, "" if cond else detail[-800:])
    cond or fails.append(name)

def run(args, stdin=None, cwd=None, t=500):
    env = {**os.environ, "PLEXAR_HARNESS_SETTINGS": SETTINGS}
    p = subprocess.run(["node", os.path.join(CLI, "plexar-harness.mjs"), *args], input=stdin, cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=t)
    return p.returncode, p.stdout, p.stderr

for f in ["acp.mjs", "render.mjs", "logo.mjs", "settings.mjs", "plexar-harness.mjs"]:
    r = subprocess.run(["node", "--check", os.path.join(CLI, f)], capture_output=True, text=True)
    check("syntax " + f, r.returncode == 0, r.stderr)
if os.path.exists(SETTINGS):
    os.remove(SETTINGS)
c, o, e = run(["--help"]); check("help", c == 0 and "Usage: plexar-harness" in o and "--mode" in o)
c, o, e = run(["-e", "bogus", "-p", "x"]); check("bad effort exits 1", c == 1 and "--effort" in e, e)
c, o, e = run(["-m", "bogus", "-p", "x"]); check("bad mode exits 1", c == 1 and "--mode" in e, e)
ws = pathlib.Path(WORK) / "ws"; shutil.rmtree(ws, ignore_errors=True); ws.mkdir()
c, o, e = run(["-p", "-e", "off", "Reply with exactly PLEXAR_OK."], cwd=ws)
check("one-shot answer", c == 0 and "PLEXAR_OK" in o and "ctx (" in o, o + e)
script = "\n".join([
    "/effort off",
    "Remember the word falcon. Reply with just OK.",
    "/rename Gate Title",
    "/mode ask",
    "Create a file named gate.txt containing the word knight. Use the write tool.",
    "1",
    "What word did I ask you to remember? Reply with just the word.",
    "/exit",
]) + "\n"
c, o, e = run([], stdin=script, cwd=ws)
check("header", "Plexar Harness v" in o and "auto-edit" in o, o)
check("rename sets the title", 'Renamed to "Gate Title"' in o, o)
check("mode switch in place", "permissions → ask mode" in o, o)
check("permission prompt shown", "Allow " in o, o)
check("tool line", "\u25cf " in o and "\u23bf" in o, o)
check("file written after approval", (ws / "gate.txt").exists() and "knight" in (ws / "gate.txt").read_text(), o + e)
check("memory survives mode switch", "falcon" in o.split("permissions → ask mode")[-1].lower(), o)
check("mode persisted", os.path.exists(SETTINGS) and '"mode": "ask"' in open(SETTINGS).read())
check("interactive exit 0", c == 0, e)
m = re.search(r"resume with: plexar-harness --resume ([0-9a-f-]{36})", o); check("resume hint", bool(m), o)
if m:
    c, o, e = run(["-p", "-r", m.group(1), "What single word did you write into gate.txt? Reply with just the word."], cwd=ws)
    check("resume keeps memory", c == 0 and "knight" in o.lower(), o + e)
c, o, e = run([], stdin="exit" + chr(10), cwd=ws); check("bare exit quits without a turn", c == 0 and "resume with:" in o and "ctx (" not in o, o)
c, o, e = run(["-p", "-c", "Reply with exactly CONT_OK."], cwd=ws); check("continue", c == 0 and "CONT_OK" in o, o + e)
if m:
    x = subprocess.run(["node", os.path.join(CLI, "plexar-harness.mjs"), "export", m.group(1)], capture_output=True, text=True, encoding="utf-8")
    t = x.stdout
    check("export transcript", x.returncode == 0 and t.startswith("# plexar-export-1") and "USER: Remember the word falcon" in t and "ASSISTANT:" in t and "/permission" not in t and "Current runtime context" not in t, t + x.stderr)
    x = subprocess.run(["node", os.path.join(CLI, "plexar-harness.mjs"), "export", m.group(1), "--tools"], capture_output=True, text=True, encoding="utf-8")
    check("export --tools", "TOOL: write" in x.stdout and "COMMAND: /permission" in x.stdout, x.stdout)
x = subprocess.run(["node", os.path.join(CLI, "plexar-harness.mjs"), "export", "no-such-session"], capture_output=True, text=True, encoding="utf-8")
check("export unknown id exits 1", x.returncode == 1 and "no session log" in x.stderr, x.stderr)
print("GATE", "FAIL " + ",".join(fails) if fails else "PASS")
sys.exit(1 if fails else 0)
