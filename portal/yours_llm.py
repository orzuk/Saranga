"""'Your paper' with an LLM: the v7 agent extraction, run on the user's own Anthropic key.

This is the extraction that built the silver corpus: the v7 prompt
(scripts/opus_extract_prompt_v7.md) given to a Claude Code agent, which runs
latex_facts.py, writes and runs its own build script, calls finalize() until the
graph validates and writes the JSON. Here the agent is the Claude Agent SDK, with
the model the user picks and the key they paste.

The paper is untrusted input, and the agent runs code, so:
  - built-in tools are limited to Read/Write/Edit/Glob/Grep/Bash/TodoWrite;
  - a PreToolUse hook confines reads to the job folder and the repo's src/, and
    writes to the job folder;
  - Bash runs in the SDK sandbox with no network access and cannot leave it;
  - the agent's config dir is inside the job folder, so no host settings,
    credentials or transcripts are used or kept;
  - the key lives only in this job's memory and the agent's environment: it is
    never written to disk, logged, or returned.
Jobs run in background threads; the page polls /yours/llm/status.

Results: the viewer page is built standalone (libraries inlined), so the HTML the
user downloads works offline. If SMTP is configured (SARANGA_SMTP_HOST, _PORT,
_USER, _PASS, _FROM) the user may give an email address: the graph (HTML + JSON)
and the run details are sent there when the job ends, and the address is dropped.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import secrets
import shutil
import smtplib
import subprocess
import sys
import threading
import time
from email.message import EmailMessage
from pathlib import Path

import yours

REPO = yours.REPO
SRC = REPO / "src"
PROMPT = REPO / "scripts" / "opus_extract_prompt_v7.md"
MODELS = {                      # what the page offers; the first is the default
    "claude-opus-5-5": "Claude Opus 5.5 (the silver corpus model)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-haiku-5-5": "Claude Haiku 5.5",
}
MAX_BUDGET_USD = 20.0
MAX_JOBS = 2                    # concurrent LLM jobs per server
JOB_TIMEOUT = 60 * 60
TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"]
PLACEHOLDERS = ("BID", "TITLE", "AUTHORS", "YEAR", "TEX_SOURCE", "OUTPUT_JSON",
                "REPO", "MODEL", "EFFORT", "PROMPT_VERSION")

SMTP = {k: os.environ.get("SARANGA_SMTP_" + k.upper(), "") for k in ("host", "port", "user", "pass", "from")}
EMAIL_ENABLED = bool(SMTP["host"] and SMTP["from"])
MAX_ATTACH = 20 * 2**20
_EMAIL = re.compile(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}")
PRIVATE = ("t0", "email")      # never returned by status()

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _inside(path: str, roots: list[Path]) -> bool:
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return any(p == r or str(p).startswith(str(r) + os.sep) for r in roots)


def _commit() -> str:
    """The code version: git where there is a checkout, else the COMMIT file staging writes."""
    try:
        c = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10).stdout.strip()
        if c:
            return c
    except (OSError, subprocess.SubprocessError):
        pass
    f = REPO / "COMMIT"
    return f.read_text().strip() if f.is_file() else "portal"


def render_prompt(main_tex: Path, out_json: Path, paper_id: str, title: str, model: str) -> str:
    sys.path.insert(0, str(SRC))
    from schema_for_prompts import render_prompt as render   # noqa: E402
    import hashlib
    template = render(PROMPT.read_text())
    sha = hashlib.sha256(template.encode()).hexdigest()[:16]
    commit = _commit()
    values = {"BID": paper_id, "TITLE": title or "(see the source)", "AUTHORS": "(see the source)",
              "YEAR": "(see the source)", "TEX_SOURCE": str(main_tex), "OUTPUT_JSON": str(out_json),
              "REPO": str(REPO), "MODEL": model, "EFFORT": "default",
              "PROMPT_VERSION": f"v7-{sha}-{commit}"}
    text = template
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    left = [k for k in PLACEHOLDERS if "{" + k + "}" in text]
    if left:
        raise yours.YoursError(f"Prompt not fully rendered: {left}")
    return text


def _stage(job: dict, pct: int, text: str) -> None:
    job["pct"] = max(job["pct"], pct)
    job["stage"] = text


def _on_tool(job: dict, name: str, inp: dict, out_json: Path) -> None:
    """Map the agent's tool calls to progress milestones (the v7 workflow order)."""
    cmd = inp.get("command", "") if name == "Bash" else ""
    target = inp.get("file_path", "")
    if "latex_facts.py" in cmd:
        _stage(job, 10, "Reading the LaTeX structure")
    elif name == "Read" and target.endswith("facts.json"):
        _stage(job, 15, "Reading the paper")
    elif name in ("Write", "Edit") and target.endswith(".py"):
        _stage(job, 35, "Writing the graph (nodes, steps, edges)")
    elif name == "Bash" and re.search(r"python3?\s+\S+\.py", cmd):
        _stage(job, 60, "Checking the graph (finalize) and fixing errors")
    elif name == "Bash" and "python" in cmd:
        _stage(job, 20, "Reading the paper")
    elif name in ("Write", "Edit") and Path(target).resolve() == out_json.resolve():
        _stage(job, 85, "Writing the JSON")
    job["actions"] += 1


async def _run_agent(job: dict, key: str, model: str, budget: float, work: Path,
                     prompt: str, out_json: Path) -> dict:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, HookMatcher,
                                  ResultMessage, ToolUseBlock, query)
    read_roots = [work.resolve(), SRC.resolve()]
    write_roots = [work.resolve()]

    def deny(reason):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": reason}}

    def allow():
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "allow"}}

    async def guard(inp, tool_use_id, context):
        name, ti = inp.get("tool_name", ""), inp.get("tool_input", {}) or {}
        if name in ("Read", "Glob", "Grep"):
            path = ti.get("file_path") or ti.get("path") or str(work)
            return allow() if _inside(path, read_roots) else deny("Only the job folder and src/ can be read.")
        if name in ("Write", "Edit"):
            return allow() if _inside(ti.get("file_path", ""), write_roots) else deny("Write only inside the job folder.")
        if name == "Bash":
            return deny("Commands must run in the sandbox.") if ti.get("dangerouslyDisableSandbox") else allow()
        if name == "TodoWrite":
            return allow()
        return deny(f"{name} is not available here.")

    env = {"ANTHROPIC_API_KEY": key,
           "CLAUDE_CONFIG_DIR": str(work / ".agent"),       # no host settings, logins or transcripts
           "PYTHONDONTWRITEBYTECODE": "1"}
    options = ClaudeAgentOptions(
        model=model, cwd=str(work), env=env, tools=TOOLS, setting_sources=[],
        system_prompt={"type": "preset", "preset": "claude_code"},   # the harness of the in-session runs
        hooks={"PreToolUse": [HookMatcher(hooks=[guard])]},
        sandbox={"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False,
                 "failIfUnavailable": True, "network": {"allowedDomains": []}},
        max_budget_usd=budget, max_turns=400,
    )
    result = {}
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    _on_tool(job, b.name, b.input or {}, out_json)
        elif isinstance(msg, ResultMessage):
            result = {"subtype": msg.subtype, "is_error": msg.is_error, "turns": msg.num_turns,
                      "cost": msg.total_cost_usd, "errors": msg.errors}
    return result


def _details(job: dict, title: str, res: dict) -> dict:
    return {"paper": job["paper_id"], "title": title, "model": job["model"],
            "cost_usd": round(res["cost"], 4) if res.get("cost") is not None else None,
            "budget_usd": job["budget"], "agent_turns": res.get("turns"), "agent_actions": job["actions"],
            "minutes": round((time.time() - job["t0"]) / 60, 1),
            "nodes": job.get("n_nodes"), "edges": job.get("n_edges"),
            "prompt_version": job.get("prompt_version"),
            "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}


def send_email(to: str, det: dict, files: list[Path]) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"SARANGA graph: {det['title'] or det['paper']}"
    msg["From"], msg["To"] = SMTP["from"], to
    lines = [f"{k.replace('_', ' ')}: {v}" for k, v in det.items() if v is not None]
    msg.set_content("Your SARANGA LLM extraction has finished.\n\n" + "\n".join(lines) +
                    "\n\nAttached: the interactive graph (open the .html in a browser; it works offline, and math renders when online) "
                    "and the graph as JSON.\n\nThe cost was billed to your own Anthropic API key. "
                    "SARANGA does not keep your email address.\n")
    total = 0
    for f in files:
        data = f.read_bytes()
        total += len(data)
        if total > MAX_ATTACH:
            break
        sub = "html" if f.suffix == ".html" else "json"
        msg.add_attachment(data, maintype="text" if sub == "html" else "application", subtype=sub, filename=f.name)
    port = int(SMTP["port"] or 587)
    with (smtplib.SMTP_SSL(SMTP["host"], port, timeout=60) if port == 465
          else smtplib.SMTP(SMTP["host"], port, timeout=60)) as srv:
        if port != 465:
            srv.starttls()
        if SMTP["user"]:
            srv.login(SMTP["user"], SMTP["pass"])
        srv.send_message(msg)


def _worker(job: dict, key: str, model: str, budget: float, work: Path, paper_id: str, title: str) -> None:
    out_json = work / f"{paper_id}_llm.json"
    try:
        main = yours.find_main_tex(work / "source")
        title = title or yours._title_from_tex(main) or paper_id
        prompt = render_prompt(main, out_json, paper_id, title, model)
        m = re.search(r"v7-[0-9a-f]{16}-[0-9A-Za-z]+", prompt)
        job["prompt_version"] = m.group(0) if m else None
        _stage(job, 3, "Starting the agent")
        res = asyncio.run(asyncio.wait_for(
            _run_agent(job, key, model, budget, work, prompt, out_json), JOB_TIMEOUT))
        job["cost"] = res.get("cost")
        if not out_json.is_file():
            why = {"error_max_budget_usd": f"it reached the ${budget:g} budget",
                   "error_max_turns": "it ran out of turns"}.get(res.get("subtype"), "the agent stopped early")
            raise yours.YoursError(f"No graph was written: {why}.")
        d = json.loads(out_json.read_text())
        d.setdefault("metadata", {}).update({"title": title, "paper_id": paper_id,
                                             "extractor": f"LLM agent (v7 prompt, {model})"})
        out_json.write_text(json.dumps(d))
        _stage(job, 95, "Building the viewer page")
        r = subprocess.run([sys.executable, str(yours.GRAPH_BUILD), str(out_json), "-o", str(work),
                            "--suffix", "", "--standalone"],     # libraries inlined: the download works offline
                           capture_output=True, text=True, timeout=yours.BUILD_TIMEOUT)
        page = work / f"{out_json.stem}.html"
        if r.returncode != 0 or not page.is_file():
            raise yours.YoursError("Building the page failed: " + (r.stderr or "")[-300:])
        job.update(n_nodes=len(d.get("nodes", [])), n_edges=len(d.get("edges", [])))
        det = _details(job, title, res)
        (work / f"{paper_id}_llm_details.json").write_text(json.dumps(det, indent=1))
        if job.get("email"):
            _stage(job, 98, "Emailing the results")
            try:
                send_email(job["email"], det, [page, out_json])
                job["email_sent"] = True
            except Exception as e:                          # noqa: BLE001
                sys.stderr.write(f"[yours_llm] {job['id']} email failed: {type(e).__name__}\n")
                job["email_sent"] = False
        job.update(state="done", pct=100, stage="Done", details=det,
                   url=f"/yours_pages/{job['rid']}/{page.name}",
                   json_url=f"/yours_pages/{job['rid']}/{out_json.name}")
    except yours.YoursError as e:
        job.update(state="error", error=str(e))
    except asyncio.TimeoutError:
        job.update(state="error", error=f"Stopped after {JOB_TIMEOUT // 60} minutes.")
    except Exception as e:                                  # noqa: BLE001
        msg = str(e)
        if key and key in msg:
            msg = msg.replace(key, "[key]")
        if re.search(r"authenticat|invalid x-api-key|401", msg, re.I):
            msg = "The API key was rejected."
        elif re.search(r"credit|billing|402", msg, re.I):
            msg = "The API key has no credit left."
        elif re.search(r"sandbox", msg, re.I):
            msg = "The command sandbox is not available on this server."
        sys.stderr.write(f"[yours_llm] {job['id']} {type(e).__name__}\n")
        job.update(state="error", error=msg[:300] or type(e).__name__)
    finally:
        shutil.rmtree(work / ".agent", ignore_errors=True)
        job["seconds"] = round(time.time() - job["t0"], 1)
        job.pop("email", None)                              # the address is not kept
        del key


def check(key: str, model: str, email: str = "") -> None:
    """Reject a malformed key, unknown model or bad email before any download."""
    if email and (not EMAIL_ENABLED or not _EMAIL.fullmatch(email)):
        raise yours.YoursError("That email address does not look right." if EMAIL_ENABLED
                               else "Email delivery is not available on this server.")
    if not re.fullmatch(r"sk-ant-[A-Za-z0-9_\-]{20,}", key or ""):
        raise yours.YoursError("Paste an Anthropic API key (it starts with sk-ant-).")
    if model not in MODELS:
        raise yours.YoursError("Unknown model.")


def start(key: str, model: str, budget: float, work: Path, rid: str, paper_id: str, title: str,
          email: str = "") -> str:
    check(key, model, email)
    budget = min(max(float(budget or 5), 0.5), MAX_BUDGET_USD)
    with _LOCK:
        running = sum(j["state"] == "running" for j in JOBS.values())
        if running >= MAX_JOBS:
            raise yours.YoursError("The server is busy with other LLM extractions; try again in a few minutes.")
        jid = secrets.token_hex(8)
        job = {"id": jid, "rid": rid, "state": "running", "pct": 1, "stage": "Queued", "actions": 0,
               "model": model, "budget": budget, "t0": time.time(), "paper_id": paper_id,
               "email": email or None}
        JOBS[jid] = job
    threading.Thread(target=_worker, args=(job, key, model, budget, work, paper_id, title), daemon=True).start()
    return jid


def status(jid: str) -> dict | None:
    job = JOBS.get(jid)
    if not job:
        return None
    out = {k: v for k, v in job.items() if k not in PRIVATE}
    out["emailing"] = bool(job.get("email")) or "email_sent" in job
    out["elapsed"] = round(time.time() - job["t0"])
    return out
