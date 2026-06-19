#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SHA-bound review cycles for the PR-mode review profile.

A review means "reviewer R examined tree SHA X". That fact is stored as machine-readable
markers in PR comments (GitHub is the canonical event store), never inferred from filenames.
Identity of a review is (reviewer, review_cycle, reviewed_sha). A marker is only believed if
its provenance binds on TWO axes: the logical reviewer it claims AND the GitHub actor who
posted it. A result must come from a trusted operator (`_author` ∈ review.operators ∪ owner),
name a configured reviewer, be the latest cycle, at the current head, with a merge-compatible
verdict and no unresolved decision. Findings/freeze markers are likewise only believed from a
trusted operator; an approval only from a trusted approver whose claimed `by` equals who posted
it. Codex is bound differently: a formal Codex review whose `commit_id` equals the head, or the
SHA the Codex bot names in its own review comment (timing is irrelevant once the tree is pinned).
Markers in fenced code blocks are ignored.

Markers (HTML comments embedded in PR comment bodies):
  jw-review-cycle  : a freeze — {round_id, cycle, target_sha, base_sha, reviewers}
  jw-review-result : an external reviewer reply footer — {reviewer, review_cycle, reviewed_sha, verdict, decision_required}
  jw-findings      : adjudication outcome for a cycle — {cycle, resolved}
  jw-approval      : SHA-bound human approval — {sha, by}

Subcommands (also `jw review <sub>`):
  freeze --pr N [--round ID] [root]   stamp the current PR head as a new review cycle + post request
  status [--pr N] [root]              show per-cycle review status (PR mode) or packet pairs (packet mode)
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml  # noqa: E402

from jw_common import find_project_root, git_full_sha, load_config  # noqa: E402

CODEX_BOT = "chatgpt-codex-connector[bot]"  # REST `user.login` form


def is_codex(login: str | None) -> bool:
    """Codex bot author match, robust to the `[bot]` suffix: GraphQL (`gh pr view`) drops it
    (`chatgpt-codex-connector`), REST keeps it (`chatgpt-codex-connector[bot]`)."""
    return (login or "").removesuffix("[bot]") == "chatgpt-codex-connector"


MARKER_RE = re.compile(r"<!--\s*jw-([a-z-]+):v1\s*\n(.*?)\n\s*-->", re.DOTALL)
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
MERGE_OK_VERDICTS = {"shipped", "shipped-with-risk", "approved", "approve", "lgtm"}


# ---- pure marker logic -------------------------------------------------------
def emit_marker(kind: str, fields: dict) -> str:
    lines = [f"<!-- jw-{kind}:v1"]
    for k, v in fields.items():
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        lines.append(f"{k}: {v}")
    lines.append("-->")
    return "\n".join(lines)


def parse_markers(text: str, kind: str | None = None) -> list[dict]:
    """Extract jw-*:v1 markers from a blob. Markers inside ``` fenced blocks are ignored
    (a quoted example must not be read as live state)."""
    out = []
    clean = FENCE_RE.sub("", text or "")
    for m in MARKER_RE.finditer(clean):
        k, body = m.group(1), m.group(2)
        if kind and k != kind:
            continue
        try:
            d = yaml.safe_load(body) or {}
        except yaml.YAMLError:
            d = {}
        if not isinstance(d, dict):
            d = {}
        d["_kind"] = k
        out.append(d)
    return out


def parse_bodies(bodies: list[dict]) -> list[dict]:
    """Parse markers per comment, preserving the comment author/timestamp as _author/_at."""
    out = []
    for b in bodies:
        for m in parse_markers(b.get("body", "")):
            m["_author"] = b.get("author", "")
            m["_at"] = b.get("at", "")
            out.append(m)
    return out


def latest_cycle(markers: list[dict], operators: tuple = ()) -> dict | None:
    """The freeze marker with the highest cycle number. When `operators` is given, only freeze
    markers POSTED by a trusted operator count — an untrusted actor can't inject a higher cycle
    to hijack the frozen target."""
    cycles = [m for m in markers if m.get("_kind") == "review-cycle" and isinstance(m.get("cycle"), int)
              and (not operators or m.get("_author") in operators)]
    return max(cycles, key=lambda m: m["cycle"]) if cycles else None


def next_cycle_number(markers: list[dict]) -> int:
    lc = latest_cycle(markers)
    return (lc["cycle"] + 1) if lc else 1


def classify(markers: list[dict], current_head: str, macro_reviewers: tuple = (),
             approvers: tuple = (), operators: tuple = (), current_base: str | None = None,
             codex_signal_at: str | None = None) -> dict:
    """Strict, provenance-bound classification of PR review state vs the current head/base.

    A marker's GitHub author (`_author`, the actor who posted it) is a separate provenance from
    the logical `reviewer`/`by` it claims. When `operators`/`approvers` are given, cycle/result/
    findings markers are only believed from a trusted operator, and an approval only from a
    trusted approver whose `by` matches who actually posted it.

    Each fact is the LATEST trusted state, never "one past success": every configured macro
    reviewer must have a latest merge-compatible result (a later not-shipped cancels an earlier
    shipped); findings use the latest resolution. A cycle is fresh only if BOTH the frozen head
    and the frozen base equal the current head/base (`current_base` given) — base drift means the
    merged tree differs from what was reviewed. When `codex_signal_at` is given, findings and the
    human approval must POST-DATE the newest Codex signal at this head, so a new Codex finding
    re-blocks a stale resolution/approval. Conflicting freeze markers for the latest cycle fail
    closed."""
    trusted_cycles = [m for m in markers if m.get("_kind") == "review-cycle"
                      and isinstance(m.get("cycle"), int)
                      and (not operators or m.get("_author") in operators)]
    lc = max(trusted_cycles, key=lambda m: m["cycle"]) if trusted_cycles else None
    cyc = lc["cycle"] if lc else None
    frozen = (lc or {}).get("target_sha")
    frozen_base = (lc or {}).get("base_sha")
    # two operator freeze markers for the SAME latest cycle but different SHA → ambiguous, block
    conflict = lc is not None and any(
        m is not lc and m["cycle"] == cyc and str(m.get("target_sha")) != str(frozen)
        for m in trusted_cycles)
    base_ok = current_base is None or str(frozen_base) == current_base
    head_matches = bool(lc) and not conflict and str(frozen) == current_head and base_ok

    def newer_than_codex(at: str) -> bool:
        return codex_signal_at is None or (at or "") >= codex_signal_at

    # results: per macro reviewer, the LATEST trusted result must be merge-compatible (all-of)
    results = [m for m in markers if m.get("_kind") == "review-result"
               and str(m.get("reviewed_sha")) == current_head and m.get("review_cycle") == cyc
               and (not operators or m.get("_author") in operators)]

    def reviewer_ok(reviewer: str) -> bool:
        rs = [r for r in results if r.get("reviewer") == reviewer]
        if not rs:
            return False
        latest = max(rs, key=lambda r: r.get("_at") or "")
        return (str(latest.get("verdict", "")).lower() in MERGE_OK_VERDICTS
                and not latest.get("decision_required"))

    pro_ok = all(reviewer_ok(rv) for rv in macro_reviewers) if macro_reviewers else True

    def approval_ok(a: dict) -> bool:
        author = a.get("_author", "")
        return (str(a.get("sha")) == current_head
                and bool(author) and not author.endswith("[bot]")
                and (not approvers or author in approvers)
                and str(a.get("by", "")) == author  # claimed approver must equal who posted it
                and newer_than_codex(a.get("_at", "")))

    approvals = [m for m in markers if m.get("_kind") == "approval"]
    # findings: only this cycle, only from trusted operators; the LATEST state must be resolved
    # AND post-date the newest Codex signal (a later 'resolved: false' or a fresh Codex finding
    # re-blocks).
    cyc_findings = [m for m in markers if m.get("_kind") == "findings" and m.get("cycle") == cyc
                    and (not operators or m.get("_author") in operators)]
    latest_finding = max(cyc_findings, key=lambda f: f.get("_at") or "") if cyc_findings else None
    findings_resolved = (bool(latest_finding) and latest_finding.get("resolved") is True
                         and newer_than_codex(latest_finding.get("_at", "")))
    return {
        "current_head": current_head,
        "latest_cycle": cyc,
        "frozen_sha": frozen,
        "frozen_base": frozen_base,
        "cycle_conflict": conflict,
        "cycle_fresh": head_matches,
        "pro_result_at_head": pro_ok,
        "approved_at_head": any(approval_ok(a) for a in approvals),
        "findings_resolved": findings_resolved,
        "n_results": len(results),
        "n_approvals": len(approvals),
    }


# ---- gh I/O (isolated) -------------------------------------------------------
def _gh(root: Path, *args: str) -> tuple[int, str]:
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30, cwd=str(root))
    except (OSError, subprocess.TimeoutExpired) as e:
        return (127, str(e))
    return (out.returncode, out.stdout.strip() if out.returncode == 0 else out.stderr.strip())


def resolve_repo(root: Path) -> str | None:
    rc, out = _gh(root, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    return out if rc == 0 and out else None


def file_at_ref(root: Path, repo: str, path: str, ref: str) -> str | None:
    """Read a file's contents from the PR head SHA on GitHub (decouples the gate from the local
    checkout, which may be a different/dirty tree). `--method GET` is mandatory: a bare `-f`
    flips `gh api` to POST, which the read-only contents endpoint rejects (404)."""
    rc, out = _gh(root, "api", "--method", "GET", f"repos/{repo}/contents/{path}",
                  "-f", f"ref={ref}", "-q", ".content")
    if rc != 0 or not out:
        return None
    try:
        return base64.b64decode(out).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def rest_reviews(root: Path, repo: str, pr: int) -> list[dict]:
    """Formal PR reviews via REST — the only source that carries `commit_id`, the SHA a review
    was submitted against (`gh pr view --json reviews` omits it). `--slurp` is required with
    `--paginate`: without it gh concatenates one JSON array per page (invalid combined JSON), so a
    PR with >30 reviews would fail to parse and silently drop reviews. Empty on any failure."""
    rc, out = _gh(root, "api", "--method", "GET", f"repos/{repo}/pulls/{pr}/reviews",
                  "--paginate", "--slurp")
    if rc != 0 or not out:
        return []
    try:
        pages = json.loads(out)
    except json.JSONDecodeError:
        return []
    flat = []
    for page in (pages if isinstance(pages, list) else []):
        flat.extend(page if isinstance(page, list) else [page])
    return [{"id": r.get("id"), "author": (r.get("user") or {}).get("login", ""),
             "body": r.get("body", ""), "state": r.get("state", ""),
             "commit_id": r.get("commit_id", ""), "at": r.get("submitted_at", "")}
            for r in flat if isinstance(r, dict)]


def pr_bundle(root: Path, pr: int, repo: str | None = None) -> dict | None:
    rc, out = _gh(root, "pr", "view", str(pr), "--json",
                  "headRefOid,baseRefOid,comments,statusCheckRollup,mergeStateStatus,state,isDraft,baseRefName,headRefName")
    if rc != 0:
        print(f"jw_review: gh pr view {pr} failed: {out}", file=sys.stderr)
        return None
    j = json.loads(out)
    bodies = []
    for c in j.get("comments", []):
        bodies.append({"id": c.get("id"), "body": c.get("body", ""),
                       "author": (c.get("author") or {}).get("login", ""), "at": c.get("createdAt", "")})
    if repo is None:
        repo = resolve_repo(root)
    reviews = rest_reviews(root, repo, pr) if repo else []
    # a marker could also live in a formal review body — parse those too (operator-author
    # filtering still gates whether they're believed)
    for r in reviews:
        bodies.append({"id": r["id"], "body": r["body"], "author": r["author"],
                       "at": r["at"], "state": r["state"]})
    return {
        "head": j.get("headRefOid", ""), "base_sha": j.get("baseRefOid", ""),
        "bodies": bodies, "reviews": reviews,
        "checks": j.get("statusCheckRollup", []) or [],
        "merge_state": j.get("mergeStateStatus", ""), "state": j.get("state", ""),
        "is_draft": bool(j.get("isDraft")), "base": j.get("baseRefName", ""), "head_ref": j.get("headRefName", ""),
    }


# Codex prints exactly "**Reviewed commit:** `<sha>`" — parse that one field, never a loose
# substring (a body like "I did NOT review <sha>" must not register as a review of <sha>).
REVIEWED_COMMIT_RE = re.compile(r"reviewed\s+commit:\**\s*`?([0-9a-f]{7,40})`?", re.IGNORECASE)


def _codex_comment_reviews(body: str, target_sha: str) -> bool:
    return any(target_sha.startswith(h.lower()) for h in REVIEWED_COMMIT_RE.findall(body or ""))


def codex_signals_at_head(reviews: list[dict], comment_bodies: list[dict],
                          target_sha: str | None) -> list[dict]:
    """Every Codex signal bound to the EXACT target tree, as {kind, id, at}. Two recordings count:
      (1) a formal Codex review whose `commit_id == target_sha`, or
      (2) a Codex-bot COMMENT whose `Reviewed commit:` field names target_sha (the connector's
          normal no-issue path posts a comment, not a formal review object).
    Only the GitHub-verified Codex bot login is trusted (un-spoofable). A bare 👍 reaction can't be
    SHA-bound and is not a signal — re-request a textual `@codex review`."""
    if not target_sha:
        return []
    out = []
    for r in reviews:
        if (is_codex(r.get("author")) and r.get("commit_id") == target_sha
                and r.get("state") in ("APPROVED", "COMMENTED", "CHANGES_REQUESTED")):
            out.append({"kind": "review", "id": r.get("id"), "at": r.get("at") or ""})
    for b in comment_bodies:
        if is_codex(b.get("author")) and _codex_comment_reviews(b.get("body") or "", target_sha):
            out.append({"kind": "comment", "id": b.get("id"), "at": b.get("at") or ""})
    return out


def codex_fresh(reviews: list[dict], comment_bodies: list[dict], target_sha: str | None) -> bool:
    return bool(codex_signals_at_head(reviews, comment_bodies, target_sha))


def ci_state(bundle: dict) -> str:
    """Strict: only SUCCESS counts as passing. Unknown/neutral/skipped/action-required are
    treated as non-passing (fail-closed under require_ci)."""
    checks = bundle.get("checks", [])
    if not checks:
        return "none"
    states = [(c.get("conclusion") or c.get("state") or "").upper() for c in checks]
    if any(s in ("", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "WAITING", "REQUESTED") for s in states):
        return "pending"
    # Only a SUCCESS *conclusion* passes. COMPLETED is a run *status* (it finished), not a verdict;
    # NEUTRAL/SKIPPED/ACTION_REQUIRED and any unknown enum fail closed.
    if all(s == "SUCCESS" for s in states):
        return "passing"
    return "failing"


def pr_facts(root: Path, pr: int, cfg: dict, repo: str | None) -> dict | None:
    bundle = pr_bundle(root, pr, repo)
    if bundle is None:
        return None
    return facts_from_bundle(bundle, cfg, repo)


def facts_from_bundle(bundle: dict, cfg: dict, repo: str | None) -> dict:
    owner = (repo.split("/", 1)[0] if repo else "")
    approvers = tuple({owner, *cfg["review"].get("approvers", [])} - {""})
    operators = tuple({owner, *cfg["review"].get("operators", [])} - {""})
    macro = tuple(r for r in cfg["review"]["reviewers"] if r != "codex")
    markers = parse_bodies(bundle["bodies"])
    # Codex signals bound to the exact head we'd merge — a formal review (commit_id) or its
    # no-issue comment naming the head. The newest one's timestamp gates findings/approval
    # freshness so a late Codex finding re-blocks a stale resolution/approval.
    signals = codex_signals_at_head(bundle.get("reviews", []), bundle.get("bodies", []), bundle["head"])
    codex_at = max((s["at"] for s in signals), default=None) if signals else None
    cls = classify(markers, bundle["head"], macro_reviewers=macro, approvers=approvers,
                   operators=operators, current_base=bundle.get("base_sha") or None,
                   codex_signal_at=codex_at)
    cls["codex_fresh"] = bool(signals)
    cls["ci"] = ci_state(bundle)
    cls["pr_state"] = bundle["state"]
    cls["is_draft"] = bundle["is_draft"]
    cls["base"] = bundle["base"]
    cls["merge_state"] = bundle["merge_state"]
    return cls


# ---- CLI ---------------------------------------------------------------------
def _opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i < len(argv) - 1:
            return argv[i + 1]
    return None


def _root(argv: list[str]) -> Path | None:
    flags = ("--pr", "--round", "--sha", "--commit")
    positional = [a for i, a in enumerate(argv)
                  if not a.startswith("--") and (i == 0 or argv[i - 1] not in flags)]
    if positional:
        return Path(positional[-1]).resolve()
    return find_project_root(Path.cwd())


def freeze(root: Path, pr: int, round_id: str | None) -> int:
    cfg = load_config(root)
    if cfg["review"]["mode"] != "pr":
        print("jw_review freeze: review.mode is 'packet'; freeze is for PR mode.", file=sys.stderr)
        return 1
    bundle = pr_bundle(root, pr)
    if bundle is None:
        return 1
    head = bundle["head"] or git_full_sha(root, "HEAD")
    base_sha = bundle.get("base_sha", "")
    markers = parse_bodies(bundle["bodies"])
    n = next_cycle_number(markers)
    reviewers = cfg["review"]["reviewers"]
    marker = emit_marker("review-cycle", {
        "round_id": round_id or "(unset)", "cycle": n, "target_sha": head,
        "base_sha": base_sha, "reviewers": reviewers,
    })
    body = (f"## Review cycle {n} — frozen at `{head[:12]}` (base `{base_sha[:12]}`)\n\n"
            f"Immutable review target for cycle {n}. A new push — or a base advance — makes this "
            f"cycle stale.\n\n"
            + ("@codex review\n\n" if "codex" in reviewers else "")
            + (f"Macro reviewer: review at the SHA above; end your reply with a `jw-review-result` "
               f"footer carrying `reviewed_sha: {head}` and `review_cycle: {n}`.\n\n"
               if any("gpt" in r or "pro" in r for r in reviewers) else "")
            + marker + "\n")
    rc, out = _gh(root, "pr", "comment", str(pr), "--body", body)
    if rc != 0:
        print(f"jw_review freeze: gh pr comment failed: {out}", file=sys.stderr)
        return 1
    print(f"review cycle {n} frozen at {head[:12]} on PR #{pr} (reviewers: {', '.join(reviewers)})")
    return 0


def status(root: Path, pr: int | None) -> int:
    cfg = load_config(root)
    if pr is not None:
        facts = pr_facts(root, pr, cfg, resolve_repo(root))
        if facts is None:
            return 1
        print(f"PR #{pr} review status ({facts['pr_state']}{', DRAFT' if facts['is_draft'] else ''}):")
        print(f"  current head:   {facts['current_head'][:12]}")
        print(f"  latest cycle:   {facts['latest_cycle']} (frozen {str(facts['frozen_sha'])[:12]})")
        print(f"  cycle fresh:    {facts['cycle_fresh']}  (False = push after freeze → re-freeze)")
        print(f"  codex fresh:    {facts['codex_fresh']}")
        print(f"  CI:             {facts['ci']}")
        print(f"  pro result@head:{facts['pro_result_at_head']}  ({facts['n_results']} result(s))")
        print(f"  findings resolved: {facts['findings_resolved']}")
        print(f"  approved@head:  {facts['approved_at_head']}  ({facts['n_approvals']} approval(s))")
        return 0
    rdir = root / cfg["reviews_dir"]
    if not rdir.is_dir():
        print("no reviews dir yet")
        return 0
    reqs = sorted(p.stem[: -len("-request")] for p in rdir.glob("*-request.md"))
    fbs = {p.stem[: -len("-feedback")] for p in rdir.glob("*-feedback.md")}
    pending = [r for r in reqs if r not in fbs]
    print(f"packet reviews: {len(reqs)} requested, {len(pending)} awaiting feedback")
    for r in pending:
        print(f"  pending: {r}")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("freeze", "status"):
        print(__doc__, file=sys.stderr)
        return 1
    sub, rest = argv[0], argv[1:]
    root = _root(rest)
    if root is None:
        print("jw_review: no initialized project (missing .jahns-workflow.yml)", file=sys.stderr)
        return 1
    pr_s = _opt(rest, "--pr")
    if sub == "freeze":
        if not pr_s:
            print("jw_review freeze: --pr N is required", file=sys.stderr)
            return 1
        return freeze(root, int(pr_s), _opt(rest, "--round"))
    return status(root, int(pr_s) if pr_s else None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
