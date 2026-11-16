---
name: persona-review
description: Pre-review a diff through the eyes of specific teammates, using their personas in ~/.personas, and report what each would likely flag before the code is pushed. Use for "review as <user>", "review with <user>'s persona", "what would <user> say about this", "pre-review this for my reviewers".
argument-hint: "<username> [username ...] [pr-number | branch | path]"
---

# /persona-review

Arguments: $ARGUMENTS

## What this is for

Before a PR goes to a human reviewer, predict what that particular reviewer would object to, so the author can fix it first. The goal is fewer review rounds: the reviewer should open the PR and find that the things they always ask for are already done.

This is a lens added on top of a normal code review, and it does not replace one. It reports only what a named person would likely raise, based on their persona. General correctness bugs that nobody in particular is known to look for belong to `/code-review`; if you notice a serious one while reading the diff, mention it in one line at the end and leave it out of the persona findings.

A wrong prediction costs the author real work on something the reviewer never wanted, and it puts words in a colleague's mouth. So every finding must rest on a checklist item or a documented pattern in the persona file, with the past PR where that person raised the same thing. If the persona does not support a finding, it is not a finding.

## Usage

```
/persona-review alice              current branch, one reviewer
/persona-review alice bob          several reviewers
/persona-review alice 123          a specific PR
```

At least one username is required. If the arguments above name no one, do not pick reviewers yourself and do not run anything: reply with the usage lines above, list the personas available for the current repository if there is one, and stop. Guessing whose eyes to review through is the prediction most likely to be wrong.

## Step 1: Work out what is being reviewed

- A PR number: `gh pr diff <n>` and `gh pr view <n> --json title,body,baseRefName,files,reviewRequests,commits`.
- A branch or path: the diff of that branch or path against the base branch.
- No target given: the current branch of the current directory against its base, including uncommitted changes. Take the base from the branch's open PR if there is one, otherwise the repository's default branch.

If no target was given and the current directory is not a git repository, say so and stop. Do not go looking for a repository or a PR elsewhere on the machine.

Collect the PR title, the PR body or the draft of it, and the commit messages along with the diff. Several personas have expectations about those, and they are as much a part of the review as the code.

If there is no diff, say so and stop.

## Step 2: Choose the personas

The repository is `gh repo view --json nameWithOwner -q .nameWithOwner`, and its personas are in `~/.personas/<repo-name>/` (or `~/.personas/<owner>-<repo-name>/`).

Use exactly the usernames given.

For each name:

- **No persona file in this repository.** Look for the same username under another repository in `~/.personas/`. If one exists, use it and say that it comes from a different codebase, so repository-specific items may not carry over. If none exists, generate one by following `~/.claude/skills/persona/SKILL.md` for that user, then continue.
- **Confidence `low` or `very low`, or an empty checklist.** Say there is not enough evidence to predict this person's review, and do not produce findings for them.
- **Marked inactive.** Use it, and note that the persona may be out of date.
- **No `Review checklist` section** (personas written before that section existed). Work from the `As a reviewer` and `How to work with them` sections instead, treating each documented pattern as a checklist item.

Read each persona file in full, including `First-hand notes`, which records corrections from real reviews and overrides the checklist where they disagree. Read the `Team-wide patterns` section of the README too.

## Step 3: Review as each person

Go through one persona at a time. For each checklist item:

1. Decide whether it applies to this diff, using the item's `applies to`. Skip items that do not apply.
2. Check it against the code for real. Many reviewer concerns cannot be judged from the diff alone:
   - "Reuse what exists" means searching the repository for an existing helper that does the same job.
   - "Hot-path cost" means reading the callers to see how often the changed code runs.
   - "Migration safety" means looking at the other migrations and at which tables are involved.
   - "Scope" means comparing each changed file with what the PR says it does.
3. Record a finding only when the check fails, or when it is the kind of change they always ask a question about.

Then check the PR title, body, commit messages and overall size against what the persona says they expect as a reader: format, what the description should lead with, whether they want worked examples or measurements, whether they would ask for the PR to be split.

Note what the diff already does right by their standards. A short list of the checks that pass tells the author what not to worry about, and gives them points to put in the PR description.

When several personas are in play, review each independently and merge afterwards. If two people would flag the same thing, report it once with both names. If two people want opposite things, report the conflict as its own item, because the author will need to resolve it with them rather than in the code.

## Step 4: Report

Group by person, most severe first. Use the persona's own weights:

```
## <username> (confidence: <level>, persona updated <date>)

### Would likely block
- `path/file.rs:123` — <the problem, stated plainly>
  - Why them: <checklist item>, raised on #<pr>, #<pr>
  - Likely comment: "<one line in the register they actually use>"
  - Fix: <the concrete change that settled it last time>

### Would likely raise
- ...

### Nits
- ...

### PR description and commits
- ...

### Already in good shape for them
- ...
```

Close with a single `Before you push` list across all personas: the changes worth making, ordered by how likely each is to cost a review round, with the blocking ones first.

Keep it honest and proportionate:

- When a persona's checklist finds nothing wrong, say that in one line. An empty result is a useful answer.
- Do not pad a section with generic review advice to make it look thorough.
- "Likely comment" is a prediction in their style to help the author recognise the concern. Keep it to one line and never present it as something they said.
- When you are unsure whether an item applies, say what you checked and what you could not determine.

Do not change any code as part of this skill. Report, then make the fixes the user asks for.

## After the real review

When the actual review comes back, the user can run `/persona <username> --learn <pr-number>` to fold what the reviewer really said back into the persona. If a prediction from this skill turned out wrong in the current conversation, suggest that.
