# Context Injector — Agent Instructions

## Project Context

- **Language:** Python 3.10+ (governor), Shell (hooks/installers), Markdown (commands/docs)
- **Test framework:** pytest
- **Pre-commit hooks:** Talisman (secret detection)
- **Issue tracker:** Beads (`bd`)
- **Specs (immutable):** `docs/superpowers/specs/` and `docs/superpowers/plans/` — never modify these. Newer specs supersede older ones by convention.

## Architecture

Two independent modes sharing a plugin directory (`~/.claude/plugins/context-injector/`):

- **v1 (keyword classification):** `UserPromptSubmit` hook injects context files based on prompt keywords. Toggled via `/ctx on|off`. Lock file: `/tmp/ctx-locks/<hash>`.
- **v2 (state machine governor):** `SessionStart`, `PreToolUse`, `PostToolUse`, `PreCompact` hooks enforce workflow phases and inject context per state. Toggled via `/governor <machine>|off|status`. Lock file: `/tmp/ctx-governor/<hash>`.

Both modes use separate lock files and can be enabled independently.

## Task Tracking

Use `bd` (Beads) for ALL task tracking. Do NOT use markdown TODO lists.

1. File an issue before starting work: `bd create "title" --description="..." -t bug|feature|task -p 0-4`
   - **Exhaustive details required.** The description must include enough context for someone (or a future agent) to understand the problem and approach without re-reading the surrounding code. Include: what is wrong or missing, where in the codebase it manifests, and any known constraints.
   - If the brainstorm or planning phase yields pertinent extra detail (trade-offs considered, rejected approaches, edge cases discovered, related issues), add that to the Beads issue as well.
2. Claim it: `bd update <id> --claim`
3. When done: `bd close <id> --reason "..."`
4. Before every commit: `bd backup`

## Workflow

### Phases (mandatory, in order)

Every non-trivial task goes through these phases. Do not skip. Do not start implementing before completing brainstorm.

1. **Brainstorm** — **Always invoke the `superpowers:brainstorming` skill first.** Read the relevant code. Check how the existing system handles similar cases. Identify at least two approaches and their trade-offs. Ask: "does the system already have infrastructure for this?" Consider whether an open-source project already solves the problem.
2. **Plan** — Choose an approach. For features spanning multiple modules, identify independently-committable units and their order. For Heavy tasks, write the design down before proceeding. Use the `superpowers:writing-plans` skill for multi-step tasks.
3. **Test first** — Write failing tests that define the expected behavior. No implementation code until at least one test exists.
4. **Implement** — Write the minimum code to make the tests pass.
5. **Self-review** — Before running the verification gate, review your own diff (`git diff`). Look for: workaround guards, missing test coverage, weak assertions, stale docs. If the diff is large (Heavy task), run the `/review` skill.
6. **Verify** — Run `python3 -m pytest tests/`. All tests must pass.
7. **Deploy** — Copy changed files to `~/.claude/plugins/context-injector/` and `~/.claude/commands/` as appropriate.
8. **Commit** — One logical unit per commit. `bd backup` before `git add`. Push to remote only when asked.

When asked to audit or show issues, only report findings — do not fix unless explicitly asked.

### Complexity classification

Classify before starting. This determines how much ceremony is needed.

- **Light** (< 50 lines, single file, no new abstractions) — brief brainstorm. Example: adding a keyword to the classifier.
- **Standard** (50–300 lines, 2–5 files, follows existing patterns) — brainstorm identifies the pattern being followed. Example: adding a new state machine.
- **Heavy** (300+ lines, new abstractions, multiple subsystems) — brainstorm must produce a written design with trade-offs before any code. Break into independently-committable units. Do not attempt in a single pass. Re-read actual code before each phase — design documents can anchor you to a flawed model.

### Verification gate

```bash
python3 -m pytest tests/          # full test suite
```

### Commits and state

- One logical unit per commit. Each commit must have its own tests.
- Update README if the diff changes public behavior, adds features, or modifies architecture.
- Leave the working directory clean. No uncommitted files.
- Prefer a committed partial result over an uncommitted complete attempt. If a session may end, commit what's done with a `WIP:` prefix and file an issue for the remainder.
- When test counts are mentioned, verify that count hasn't regressed.

## Interaction Style

- When interrupted or cancelled, immediately proceed with the new instruction. No clarifying questions — treat interruptions as implicit redirects.
- **Brainstorm collaboratively.** Present options and trade-offs to the user and actively incorporate their input before proceeding.
- **Stop and consult when patching.** If an implementation requires more than one corrective patch (fix-on-fix), stop. The design is wrong. Re-brainstorm the approach with the user before adding more patches. Accumulating compensating transforms is a sign the underlying model doesn't match reality.

## Talisman (Secret Detection)

- If Talisman detects a potential secret, **stop** and prompt for guidance before updating `.talismanrc`.
- Don't overwrite existing `.talismanrc` entries — add at the end.

## Documentation

- Never modify files in `docs/superpowers/specs/` or `docs/superpowers/plans/`.
