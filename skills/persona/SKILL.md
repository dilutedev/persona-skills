---
name: persona
description: Build or refresh a working-style persona for one or more GitHub users in the context of a repository, from their real PRs, reviews and commits. Personas live in ~/.personas/<repo>/<username>.md and feed /persona-review. Use for "generate a persona for <user>", "profile this reviewer", "refresh the personas", "learn from PR #N".
argument-hint: "[username ...] [--repo owner/name ...] [--learn <pr-number>]"
---

# /persona

Arguments: $ARGUMENTS

## What this is for

A persona is a written profile of how one person works in one repository: what they own, what they flag in review, how they phrase it, what settles their concerns, and how they write their own PRs. Its main consumer is `/persona-review`, which reads a persona before code is pushed and predicts what that person would object to, so the author fixes it first and the real reviewer spends their time on the things only they can judge.

That use sets the quality bar. A persona is only useful if its claims are specific enough to check against a diff and true enough that the prediction holds. "Cares about code quality" is worthless. "Asks for `SET lock_timeout` on any migration that adds a foreign key to a hot table (#412, #398)" is something a later review can act on. Every claim in a persona traces back to something the person actually wrote, and anything the evidence does not show is left out rather than guessed.

Personas describe working style in a repository, drawn from written work artifacts only. They are not a description of the person, and the file should never speculate about personality, motives or ability.

## Usage

```
/persona alice                                   one user, current repo
/persona alice bob                               several users
/persona                                         everyone active in the current repo
/persona alice --repo acme/api --repo acme/web   one persona per repo
/persona alice --learn 123                       fold a finished review back into the persona
```

With no `--repo`, use the repository of the current directory (`gh repo view --json nameWithOwner -q .nameWithOwner`). If the current directory is not a GitHub repository and no `--repo` was given, ask which repository to use.

## Where personas live

`~/.personas/<repo-name>/` holds everything for one repository:

- `<username>.md`: the persona, one per GitHub login
- `README.md`: an index of the personas plus team-wide patterns
- `_evidence/<username>.md`: raw collected evidence, regenerated on every run

The directory is named after the repository name alone (`acme/api` lives in `~/.personas/api/`). If that directory already holds personas whose frontmatter names a different owner, use `<owner>-<repo-name>` instead.

A persona is always scoped to one repository, because people review differently in codebases they own than in ones they visit. When several repositories are given, run the whole process once per repository and write one file per repository.

## Step 1: Collect evidence

```
python3 ~/.claude/skills/persona/scripts/collect_evidence.py --repo <owner/name> --out ~/.personas/<repo-name> [--users login1,login2]
```

This downloads every PR, review, inline review comment, PR conversation comment and the user's recent commits through the `gh` CLI, and writes `_evidence/<login>.md` for each user. Omitting `--users` covers every non-bot contributor. It prints one summary line per user with their counts and activity window. On a repository with thousands of PRs it takes a few minutes.

Evidence files in `_evidence/` are overwritten on every run. Persona files are never overwritten by the script.

## Step 2: Read the evidence

Read each user's evidence file completely before writing anything. For someone with a lot of review history the file is long, and the review threads are the part that matters most, so do not sample them.

An active reviewer's evidence file can run past 200 KB. When a run covers more than two or three people, give each person to their own subagent with this skill's steps 2 and 3 and the template path, so no single context has to hold everyone's evidence.

For a prolific reviewer the file shows at most 10 threads per PR and 200 in total, newest first, and the `threads per PR` line shows how many exist. If one PR holds most of someone's review history, fetch the rest of that PR's comments with `gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate` before drawing conclusions from it.

Each review thread shows the diff lines the comment was attached to, the comment, and the replies. Read all three together: the diff shows what triggered the comment, and the replies show whether the author changed the code, pushed back successfully, or was overruled. That is how you learn what the person holds firm on and what they let go.

While reading, look for:

- **Repeated concerns.** The same point raised on different PRs is a pattern. A point raised once is an observation and goes in the persona only when it was clearly a blocking issue.
- **Weight.** How they mark something optional ("nit", "not blocking", a question) versus required (a request for changes, an unlabelled statement, a comment repeated until fixed).
- **Where the concern applies.** A concern tied to migrations, to a money path or to one service only belongs on diffs that touch those.
- **What settled it.** A code change, a measurement, a worked example, a link to a prior decision.
- **Drift over time.** People change. Every item carries a date; when early and recent behaviour differ, describe the recent behaviour and note the change.
- **What they let through.** Things other reviewers flag that this person approves without comment. This keeps a later review from raising noise in their name.
- **Tooling in their voice.** Bot-style reviews, AI co-author trailers and generated PR bodies reflect their tools. Say so rather than attributing the prose style to them.

If the repository is checked out locally, open the files behind the most important repeated concerns so each checklist item names the real helper, module or rule involved instead of paraphrasing the comment.

## Step 3: Write the persona

Write `~/.personas/<repo-name>/<username>.md` following the structure in `~/.claude/skills/persona/persona-template.md`. Read the template before writing the first persona of a run.

The `Review checklist` section is the part `/persona-review` applies mechanically, so it gets the most care:

- Phrase each item as something that can be verified by looking at a diff and the surrounding code.
- Give each item a weight: `blocks` (they have requested changes or held approval over it), `expects` (they raise it every time and the author always ends up changing it), or `nit` (they mention it and approve anyway).
- Say which changes it applies to, as paths or kinds of change.
- Cite the PRs where they raised it, with a short direct quote when their wording is distinctive.
- Order the list by weight, then by how often it comes up.

Set `confidence` from the amount of review evidence, since review behaviour is what the persona predicts:

| Confidence | Evidence |
|---|---|
| high | 40 or more review comments or reviews with written bodies, across many PRs and recent |
| medium | 10 to 39, or plenty of authored PRs and replies but little reviewing |
| low | fewer than 10, enough to describe them as an author only |
| very low | a handful of artifacts; write a short stub that says what exists and stops |

Someone with no review history gets a persona with an empty checklist and a line saying there is no evidence of how they review. Do not fill it from how they write their own code.

Mark `active` from the activity window. Someone with nothing in the last 90 days is inactive, and the file says so in the frontmatter.

### When a persona already exists

Existing persona files contain hand-written knowledge from real interactions. Edit the file in place: update counts, dates and confidence, add or revise checklist items the new evidence supports, and remove an item only when recent evidence contradicts it. Never touch the `First-hand notes` section. If the file predates the template and has no `Review checklist` section, add one built from the evidence and keep the rest of the file as written.

## Step 4: Update the index

Update `~/.personas/<repo-name>/README.md`: one index row per persona (username, inferred role, active window, confidence, one line), and a `Team-wide patterns` section for things that hold across people, such as who approves what, branch flow, commit conventions, review tooling and recurring review themes. Create the file if it does not exist, and keep any existing rows and notes for people this run did not cover.

## Learning from a finished review (`--learn <pr-number>`)

The fastest way a persona improves is comparing its prediction with what the reviewer actually said. For `--learn`:

1. Fetch that PR's reviews and inline comments by the named user (`gh api repos/<owner>/<repo>/pulls/<n>/comments`, `gh pr view <n> --json reviews,comments`).
2. Compare each thing they raised with the persona's checklist.
3. Add a checklist item for anything they raised that the persona did not predict, cited to this PR. Strengthen the citation on items it did predict. If the persona predicted an objection they explicitly did not have, lower that item's weight or remove it.
4. Add a dated line to `First-hand notes` saying what changed and why.

## Finishing

Report, per persona: the path, the confidence, the number of checklist items, and the two or three strongest patterns found. Call out anything that surprised you or that the evidence left unclear, and say plainly which personas are stubs.
