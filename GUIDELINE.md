# Guidelines for agentic coding

Best-practice rules for repositories where AI coding agents do much of the
work. They are tool-agnostic: "hook" means any mechanism that runs before or
after an agent action (Claude Code hooks, Codex hooks, pre-commit, CI), and
"skill" means any reusable, versioned task instruction (skills, slash
commands, prompt files).

The principle behind all of them: **write down what matters, then make the
machine enforce it.** An agent follows text most of the time; a check
follows it every time.

---

## 1. Instructions

1. **Keep one authoritative rule file.** Put the rules in one file (for
   example `AGENTS.md`). Tool-specific files (`CLAUDE.md`,
   `copilot-instructions.md`, …) point to it first and add only what that
   tool needs. Never maintain the same rule in two places by hand.
2. **Keep the entry file short and practical.** It should hold the commands
   that build, test and lint the project, the traps that cost time ("tests
   only run under X", "linter Y must run from directory Z", "never run the
   formatter"), the architecture in a few lines, and the conventions that are
   easy to get wrong.
3. **Put local rules next to the code they govern.** A short instruction file
   in `tests/`, `frontend/`, etc. loads only when the agent works there.
4. **State invariants, not just style.** "End of life always rates
   worst-possible" or "a request chooses what to do, never how hard" guide
   decisions the author never anticipated. "Write clean code" does not.
5. **Give the reason for each rule.** An agent that knows *why* a rule exists
   handles the edge case correctly; one that only knows the rule
   pattern-matches and misses it.
6. **Name the decisions that belong to humans.** List them explicitly:
   releasing, bumping versions, publishing security advisories, approving
   dependencies, merging to the default branch, deleting data, widening an
   allowlist. Say "never do this yourself; ask."
7. **Say what to do when a guard refuses.** "A refusal is final: report it to
   the user, never work around it." Without this line, agents look for
   another route to the same action.
8. **Describe the architecture as boundaries.** Name the layers, what each
   one owns, and give a test for misplaced code ("if the library knows about
   exit codes, it is in the wrong layer").
9. **Document each fact in one place.** Version numbers, constants, settings
   flow, generated content: one source, everything else derives from it.
   Instruction files must not repeat a fact that lives in code (such as the
   current version); they go stale.

## 2. Guardrails (hooks)

10. **Enforce every hard rule with a hook, not just a sentence.** Block
    irreversible or outward-facing commands before they run: force-push,
    pushing to the default branch, merges, tags, publishing, destructive
    resets, repository-wide reformatting.
11. **Fail closed.** If a guard script crashes or cannot run, refuse the
    action and say the guard needs fixing. A broken guard must not become a
    silent allow.
12. **Guard every route, not just the obvious one.** If editing a file is
    forbidden, a shell redirect, `sed -i`, `cp` or `mv` into it must be
    forbidden too. Parse command chains, substitutions and `bash -c` strings.
    Don't flag text that merely mentions a command, such as a commit message
    or heredoc body.
13. **Make refusals actionable.** Each denial message says why and what to do
    instead ("generated file — edit X and run `script Y`").
14. **Choose between deny, ask and remind.** Deny what must never happen. Ask
    the human for what is sometimes legitimate (switching to the main branch,
    a version change). Refuse once for a reminder ("run the docs check
    first"), and store a marker so it never loops.
15. **Check the work when the agent stops.** Run fast consistency checks
    (stale generated files, missing records, secrets in unpushed commits) when
    the agent says it is done, and only for checks whose source files
    changed, so they stay fast.
16. **Guard privacy and secrets mechanically.** Scan staged changes, commit
    messages, pushed commits and PR/issue bodies for real hostnames, public
    IPs, personal e-mail addresses, credentials and production data. Use
    reserved example values (`example.com`, RFC 5737 addresses) in docs and
    tests. Only a human may extend the allowlist.
17. **Be honest about limits.** Document each guard as "a guardrail against
    mistakes, not a sandbox", and say what it does not catch.
18. **Test the guards.** Hooks are code and regress like code: give them
    their own test suite.

## 3. Skills (repeatable tasks)

19. **Write a skill for every change that touches many files.** Adding a
    setting, a check, a translation string, a dependency, an ADR, a security
    record: list *every* place that must change, and require the agent to say
    explicitly when a step does not apply. The missed step is the usual bug.
20. **Start each skill with "decide before editing".** Naming, which layer
    the change belongs to, whether it needs a decision record, whether it
    needs a human's approval.
21. **Tell skills to ask, not guess, when input is missing or ambiguous.**
22. **Only a human may start dangerous skills.** Mark release, deploy and
    publish skills so the model cannot invoke them on its own. Invoking them
    is then the human's explicit decision.
23. **Give the agent a way to run the real application.** A script that
    starts the app against local fakes (no production services, no external
    network) lets the agent verify behaviour, not just pass tests.

## 4. Subagents

24. **Make checking agents read-only.** Limit their tools, not just their
    instructions. An agent that runs checks or mutation tests never edits,
    commits or reformats.
25. **Fix the output format.** One results table
    (pass / fail / warning / skipped), then violations with file and line,
    then numbered concrete fixes. The subagent does not ask to apply them;
    the main conversation asks the human.
26. **"Not run" never counts as "passed".** A missing tool or an unaffected
    check is reported as skipped, with the reason.
27. **Send noisy, long-running work to a subagent** so its output does not
    flood the main context.

## 5. Verification

28. **Provide a one-command local preflight that mirrors CI**: linters, type
    checks, security scanners, generator checks, the test suite. Agents run
    it before every pull request.
29. **Give every generator a `--check` mode** that fails when the checked-in
    output is stale. "Did you regenerate?" becomes a command, not a judgement
    call.
30. **Pin tool versions** in the commands agents run
    (`npx tool@x.y.z`, `uvx tool@x.y.z`) so local results match CI.
31. **Keep documented runtimes and commands accurate.** If the docs say the
    suite takes 75 s and it takes 8 minutes, agents time out or skip it.

## 6. Tests

32. **Name tests as sentences describing the behaviour they protect**, with a
    one-line docstring saying why it matters. Agents read them as
    specifications.
33. **Assert both the positive and the negative case.** An assertion that
    still passes when the feature is removed is worse than none.
34. **Prefer realistic fakes to mocks.** A small real server driven by a
    behaviour description beats patched libraries. Derive expected values
    from running the code against it instead of hard-coding lists that go
    stale.
35. **Turn architectural rules into tests.** Packaging exclusions, forbidden
    third parties, security properties, "no second implementation of this
    constant", CI hardening: if a rule matters, a test fails when it breaks.
36. **Freeze critical outputs in a golden corpus** and check it in CI, so a
    changed verdict is a visible, reviewed diff.
37. **Use mutation testing on demand** for the core decision logic, to find
    out whether the tests would notice a wrong answer.

## 7. Generated files

38. **Never hand-edit generated files.** Block edits with a guard that names
    the generator to run instead.
39. **Fence generated blocks inside hand-written files** with start/end
    markers, and guard those regions.
40. **Regenerate on conflict; never merge by hand.** Mark generated files
    (for example with `.gitattributes`), provide merge drivers or a
    conflict-resolution skill that rebuilds them. For append-only files such
    as changelogs, keep both sides.

## 8. Records and traceability

41. **Record durable decisions** (ADRs): layer boundaries, public interfaces,
    security and deployment model, data lifecycle, long-lived dependencies.
    Agents read the relevant ones before changing an area. Never rewrite an
    accepted record; supersede it with a new one.
42. **Require a changelog entry for every change,** in an `Unreleased`
    section, and generate the release notes from it rather than editing them
    by hand.
43. **Every security fix gets a record** of what was decided, which releases
    were affected and why. Agents draft; humans publish.
44. **Every new dependency gets a record**: justification, why the standard
    library or existing packages don't suffice, security review, the tests
    that exercise it. Agents propose; humans approve.
45. **Keep dated audit reports** in the repository so later agents know what
    has already been examined.

## 9. Workflow and isolation

46. **Define the branching model and enforce it with a guard.** Agents work
    only on the allowed branches; switching to or creating others is refused
    or asked.
47. **Isolate the agent's tools from the outside world.** Browser automation
    and MCP servers run headless, isolated, loopback-only, behind a
    deliberately dead proxy, so an agent cannot reach the internet by
    accident.
48. **Keep third-party integrations an explicit decision.** List forbidden
    services and enforce the list with a test.
49. **Never let an agent publish, release or bump a version on its own.**
    If landing on the default branch publishes something, merging to it is a
    human action.

## 10. Several agent tools, one policy

50. **Implement each policy once.** When supporting several agent tools, add
    thin adapters (a dispatcher script, a mirrored config) that call the same
    hook scripts and read the same skills. Two copies of a policy drift.
51. **Test that instruction files agree with each other.** Mirrored skill
    directories must be identical. Commands, runtimes, versions and rules
    stated in several files must match. Rules must not contradict each other
    (a worktree skill that creates branches a guard forbids).
    Instruction drift is the main failure mode of this whole approach; check
    it like code.
