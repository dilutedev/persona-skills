# persona-skills

Two Claude Code skills for reviewing a PR the way the people who will actually review it would.

Every reviewer has things they always ask for. One wants a `lock_timeout` on every migration that touches a hot table. Another won't approve a new helper until you've shown nothing in the codebase already does the job. You learn these one review round at a time. These skills learn them from the reviewer's history and check your diff for them before you push.

- **`/persona`** reads a teammate's PRs, review comments, reviews and commits in a repository and writes a working-style persona. Its core is a review checklist: concrete things they check for, how much weight each carries, and the PRs where they raised it.
- **`/persona-review`** pre-reviews your diff through one or more personas and reports what each person would likely block, raise or nit. Every finding cites a past PR where that person raised the same thing.

The goal is fewer review rounds. The reviewer opens your PR and finds that the things they always ask for are already done, so they can spend their time on what only they can judge.

## Install

```sh
git clone https://github.com/dilutedev/persona-skills
cp -r persona-skills/skills/* ~/.claude/skills/
```

Requirements:

- [Claude Code](https://docs.claude.com/en/docs/claude-code)
- [`gh`](https://cli.github.com/), authenticated with read access to the repositories you profile
- Python 3.8 or newer (the collector uses only the standard library)

## Usage

```
/persona alice                                   build a persona for alice in the current repo
/persona alice bob                               several users
/persona                                         everyone active in the current repo
/persona alice --repo acme/api --repo acme/web   one persona per repo
/persona alice --learn 123                       correct a persona from a finished review

/persona-review alice                            pre-review the current branch as alice
/persona-review alice bob                        as several reviewers
/persona-review alice 123                        a specific PR
```

`/persona-review` needs at least one username, and it never picks reviewers for you. If there is no persona for a name yet, it builds one first.

## What you get

### A persona

`~/.personas/api/alice.md`, abridged:

```markdown
---
github: alice
repo: acme/api
role: payments owner, main reviewer for billing (inferred)
active: 2025-03-02 → 2026-11-14 (active)
evidence: 212 PRs authored (198 merged), 300 commits, 431 inline review comments, 160 reviews
confidence: high
---

## Review checklist

- **Migrations that add a foreign key to `orders` or `payments` set `lock_timeout`**
  - weight: blocks
  - applies to: `migrations/`
  - seen: #412, #398 — "this will lock orders for the whole backfill"
  - settles it: `SET lock_timeout = '5s'` at the top of the migration

- **New helpers are checked against `common/` before being written**
  - weight: expects
  - applies to: any new function in `services/`
  - seen: #455, #470, #503 — "we already have `retry_with_backoff` in common"
  - settles it: use the existing helper, or say in the PR why it doesn't fit
```

The persona also covers what they work on, how their reviews read, how they mark a point as optional, what they let through, how they write their own PRs, and what has worked when disagreeing with them.

### A pre-review

```markdown
## alice (confidence: high, persona updated 2026-11-14)

### Would likely block
- `migrations/0042_add_refund_fk.sql:3` — adds a foreign key to `payments` with no lock timeout
  - Why them: lock_timeout on hot-table FKs, raised on #412, #398
  - Likely comment: "this locks payments while it validates, can we set lock_timeout"
  - Fix: `SET lock_timeout = '5s';` before the `ALTER TABLE`

### Already in good shape for them
- The new retry logic uses `common::retry_with_backoff`

## Before you push
1. Add `lock_timeout` to `0042_add_refund_fk.sql`
```

## How it works

1. **Collect.** `skills/persona/scripts/collect_evidence.py` pulls every PR, review, inline review thread, conversation comment and recent commit for each user through `gh`. Each thread includes the diff it was attached to and the author's reply, so you can see whether the code changed. Output goes to `~/.personas/<repo>/_evidence/<user>.md`.
2. **Write.** Claude reads the evidence in full and writes `~/.personas/<repo>/<user>.md` from `skills/persona/persona-template.md`. Every claim must trace back to something the person wrote, and anything the evidence doesn't show is left out. Confidence is set from how much review history there is.
3. **Review.** `/persona-review` takes each checklist item that applies to the diff and checks it against the real code. For example, a "reuse" item means searching the repo for an existing helper; it doesn't just pattern-match the diff. It reviews each persona separately, merges the results, and flags cases where two reviewers want opposite things.
4. **Learn.** After the real review, `/persona <user> --learn <pr>` compares the prediction with what the reviewer actually said. It adds what the persona missed and lowers or removes items the reviewer didn't care about.

### Files

```
~/.personas/<repo>/
├── README.md            index of personas and team-wide patterns
├── <user>.md            one persona per GitHub login
└── _evidence/<user>.md  raw collected evidence, regenerated on every run
```

- **One repository per persona.** People review differently in code they own than in code they visit.
- **Safe refreshes.** A refresh edits a persona in place, never overwrites it, and never touches its `First-hand notes` section, which is where you record what you learn working with someone.

## Limits

- **It predicts, it doesn't replace the reviewer.** It covers the patterns a person has shown repeatedly. It can't anticipate their judgment on something new.
- **It is not a general code review.** It only reports what a named person would likely raise. Use `/code-review` or similar for correctness bugs.
- **It needs history.** Someone with fewer than about ten written reviews gets a low-confidence persona, and `/persona-review` declines to make predictions for them.
- **It is GitHub only,** through `gh`. Collection takes a few minutes on a repository with a thousand or more PRs. Commits are capped at each user's 300 most recent, and a very active reviewer's evidence file can pass 200 KB.
- **It drifts.** People's priorities change. Personas record an activity window, weight recent behaviour over old, and get better with `--learn`.

## A note on use

Personas describe how someone works in a codebase, drawn only from written work artifacts: PRs, reviews and commits. They are not a description of the person, and the skill is written never to speculate about personality, motives or ability.

Generated personas stay local in `~/.personas/` and are never part of this repo. They describe real colleagues, so be open about using them: share them with the people they describe, and let those people correct them.

## License

MIT. See [LICENSE](LICENSE).
