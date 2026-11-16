import argparse
import collections
import datetime
import json
import pathlib
import re
import statistics
import subprocess

GRAPHQL_QUERY = "query($owner:String!,$name:String!,$endCursor:String){repository(owner:$owner,name:$name){pullRequests(first:25,after:$endCursor){pageInfo{hasNextPage endCursor}nodes{number title state createdAt mergedAt additions deletions changedFiles body baseRefName author{login __typename} files(first:100){nodes{path}} reviews(first:50){nodes{author{login __typename} state body submittedAt}}}}}}"

REVIEW_COMMENT_JQ = ".[] | {id, login: .user.login, type: .user.type, pr: (.pull_request_url|split(\"/\")|last|tonumber), path, body, diff_hunk, in_reply_to_id, created_at} | tojson"
ISSUE_COMMENT_JQ = ".[] | {login: .user.login, type: .user.type, pr: (.issue_url|split(\"/\")|last|tonumber), body, created_at} | tojson"
COMMIT_JQ = ".[] | {sha, message: .commit.message, date: .commit.author.date} | tojson"


def run_gh(arguments):
    return subprocess.run(["gh", *arguments], check=True, stdout=subprocess.PIPE, text=True).stdout


def gh_jsonl(arguments):
    return [json.loads(line) for line in run_gh(arguments).splitlines() if line.strip()]


def truncate(text, limit):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …[trunc]"


def is_bot(login, account_type):
    return account_type == "Bot" or login.endswith("[bot]")


def directory_of(path):
    return "/".join(path.split("/")[:2])


def format_counts(counter, limit):
    return ", ".join(f"{key}:{count}" for key, count in counter.most_common(limit))


def load_pull_requests(repo):
    owner, name = repo.split("/")
    nodes = gh_jsonl(["api", "graphql", "--paginate", "-F", f"owner={owner}", "-F", f"name={name}", "-f", f"query={GRAPHQL_QUERY}", "--jq", ".data.repository.pullRequests.nodes[] | tojson"])
    pull_requests = {}
    for node in nodes:
        author = node["author"] or {"login": "ghost", "__typename": "User"}
        reviews = []
        for review in node["reviews"]["nodes"]:
            reviewer = review["author"] or {"login": "ghost", "__typename": "User"}
            if review["submittedAt"]:
                reviews.append({"pr": node["number"], "pr_author": author["login"], "reviewer": reviewer["login"], "bot": is_bot(reviewer["login"], reviewer["__typename"]), "state": review["state"], "body": review["body"], "at": review["submittedAt"]})
        pull_requests[node["number"]] = {**node, "login": author["login"], "bot": is_bot(author["login"], author["__typename"]), "paths": [file["path"] for file in node["files"]["nodes"]], "reviews": reviews}
    return pull_requests


def load_comments(repo, endpoint, jq_filter, pull_requests):
    rows = gh_jsonl(["api", f"repos/{repo}/{endpoint}", "--paginate", "-X", "GET", "-f", "per_page=100", "--jq", jq_filter])
    for row in rows:
        row["bot"] = is_bot(row["login"] or "ghost", row["type"])
        row["login"] = row["login"] or "ghost"
    return [row for row in rows if row["pr"] in pull_requests]


def load_commits(repo, login):
    commits = []
    for page in range(1, 4):
        page_commits = gh_jsonl(["api", f"repos/{repo}/commits", "-X", "GET", "-f", f"author={login}", "-f", "per_page=100", "-f", f"page={page}", "--jq", COMMIT_JQ])
        if not page_commits:
            break
        commits += page_commits
    return commits


def build_threads(review_comments):
    grouped = collections.defaultdict(list)
    for comment in review_comments:
        grouped[comment["in_reply_to_id"] or comment["id"]].append(comment)
    threads = [sorted(comments, key=lambda comment: comment["created_at"]) for comments in grouped.values()]
    return sorted(threads, key=lambda thread: thread[0]["created_at"], reverse=True)


def spread_across_pull_requests(threads, per_pull_request_limit, total_limit):
    taken_per_pull_request = collections.Counter()
    selected = []
    for thread in threads:
        pull_request_number = thread[0]["pr"]
        if taken_per_pull_request[pull_request_number] < per_pull_request_limit:
            taken_per_pull_request[pull_request_number] += 1
            selected.append(thread)
    return selected[:total_limit]


def render_thread(thread, pull_requests):
    root = thread[0]
    hunk = "\n".join((root["diff_hunk"] or "").splitlines()[-8:])[-600:]
    lines = [f"### PR#{root['pr']} ({pull_requests[root['pr']]['login']}) {root['path']} — {root['created_at'][:10]}", "```diff", hunk, "```"]
    for position, comment in enumerate(thread):
        lines.append(f"- {comment['login']}: {truncate(comment['body'], 1000 if position == 0 else 400)}")
    return lines


def render_title_breakdown(authored):
    types = collections.Counter()
    scopes = collections.Counter()
    for pull_request in authored:
        match = re.match(r"^(\w+)(?:\(([^)]+)\))?!?:", pull_request["title"] or "")
        if match:
            types[match.group(1).lower()] += 1
            if match.group(2):
                scopes[match.group(2)] += 1
    return [f"title types: {format_counts(types, 10)}", f"title scopes: {format_counts(scopes, 10)}"]


def render_authored(login, pull_requests):
    authored = sorted((pr for pr in pull_requests.values() if pr["login"] == login), key=lambda pr: pr["createdAt"], reverse=True)
    lines = ["## Authored PRs", f"count: {len(authored)}, merged: {sum(1 for pr in authored if pr['mergedAt'])}"]
    if not authored:
        return lines
    sizes = [pr["additions"] + pr["deletions"] for pr in authored]
    lines.append(f"size (additions+deletions): median={statistics.median(sizes)} max={max(sizes)}")
    lines += render_title_breakdown(authored)
    directories = collections.Counter(directory_of(path) for pr in authored for path in pr["paths"])
    lines += [f"top directories: {format_counts(directories, 12)}", "", "### Recent PR titles"]
    lines += [f"- #{pr['number']} [{pr['state']}] {pr['createdAt'][:10]} {pr['title']}" for pr in authored[:30]]
    longest_of_rest = sorted(authored[3:], key=lambda pr: len(pr["body"] or ""), reverse=True)[:2]
    lines += ["", "### PR body samples"]
    for pr in authored[:3] + longest_of_rest:
        lines += [f"#### #{pr['number']} {pr['title']}", truncate(pr["body"], 1800), ""]
    return lines


def render_reviews_given(login, all_reviews):
    given = sorted((review for review in all_reviews if review["reviewer"] == login), key=lambda review: review["at"], reverse=True)
    lines = ["## Reviews given", f"by state: {format_counts(collections.Counter(review['state'] for review in given), 10)}", f"whose PRs: {format_counts(collections.Counter(review['pr_author'] for review in given), 10)}"]
    with_body = [review for review in given if (review["body"] or "").strip()][:40]
    return lines + [f"- {review['at'][:10]} PR#{review['pr']} ({review['pr_author']}) [{review['state']}]: {truncate(review['body'], 1500)}" for review in with_body]


def render_evidence(login, repo, pull_requests, review_comments, issue_comments, all_reviews, commits, today):
    all_threads = build_threads(review_comments)
    own_threads = [thread for thread in all_threads if pull_requests[thread[0]["pr"]]["login"] == login and any(comment["login"] == login for comment in thread)][:40]
    others_threads = [thread for thread in all_threads if pull_requests[thread[0]["pr"]]["login"] != login and any(comment["login"] == login for comment in thread)]
    others_comments = [comment for comment in review_comments if comment["login"] == login and pull_requests[comment["pr"]]["login"] != login]
    received = collections.Counter((review["reviewer"], review["state"]) for review in all_reviews if pull_requests[review["pr"]]["login"] == login and not review["bot"])
    own_conversation = sorted((comment for comment in issue_comments if comment["login"] == login), key=lambda comment: comment["created_at"], reverse=True)
    my_review_count = sum(1 for review in all_reviews if review["reviewer"] == login)
    my_pr_count = sum(1 for pr in pull_requests.values() if pr["login"] == login)
    dates = [pr["createdAt"] for pr in pull_requests.values() if pr["login"] == login]
    dates += [review["at"] for review in all_reviews if review["reviewer"] == login]
    dates += [comment["created_at"] for comment in review_comments + issue_comments if comment["login"] == login]
    dates += [commit["date"] for commit in commits]
    if not dates:
        raise SystemExit(f"no activity found for {login} in {repo}; check the login")
    window = f"{min(dates)[:10]}..{max(dates)[:10]}"
    lines = [f"# {login}", f"repo: {repo}", f"generated: {today}", f"counts: PRs authored={my_pr_count}, review comments given={len(others_comments)}, reviews given={my_review_count}, conversation comments={len(own_conversation)}, commits={len(commits)}", f"activity window: {window}", ""]
    lines += render_authored(login, pull_requests)
    lines += ["", "## Reviews received", format_counts(received, 12), "", "## Review threads on their own PRs"]
    for thread in own_threads:
        lines += render_thread(thread, pull_requests)
    commented_directories = collections.Counter(directory_of(comment["path"]) for comment in others_comments)
    shown_threads = spread_across_pull_requests(others_threads, 10, 200)
    threads_per_pull_request = collections.Counter(f"#{thread[0]['pr']}" for thread in others_threads)
    lines += ["", "## Review threads on others' PRs", f"threads: {len(others_threads)}, inline comments: {len(others_comments)}, shown below: {len(shown_threads)} (at most 10 per PR, newest first)", f"threads per PR: {format_counts(threads_per_pull_request, 40)}", f"top directories commented on: {format_counts(commented_directories, 10)}", ""]
    for thread in shown_threads:
        lines += render_thread(thread, pull_requests)
    lines += [""] + render_reviews_given(login, all_reviews)
    lines += ["", "## PR conversation comments"]
    lines += [f"- {comment['created_at'][:10]} PR#{comment['pr']} ({pull_requests[comment['pr']]['login']}): {truncate(comment['body'], 600)}" for comment in own_conversation[:40]]
    lines += ["", "## Commits", f"fetched: {len(commits)}", "", "### Recent subjects"]
    lines += [f"- {commit['message'].splitlines()[0]}" for commit in commits[:30]]
    lines += ["", "### Recent full messages"]
    for commit in commits[:6]:
        lines += ["---", commit["message"].strip()]
    summary = f"{login}: PRs={my_pr_count} review_comments={len(others_comments)} reviews={my_review_count} conversation_comments={len(own_conversation)} commits={len(commits)} active={window}"
    return "\n".join(lines) + "\n", summary


def select_users(pull_requests, review_comments, issue_comments, all_reviews):
    logins = {pr["login"] for pr in pull_requests.values() if not pr["bot"]}
    logins |= {review["reviewer"] for review in all_reviews if not review["bot"]}
    logins |= {comment["login"] for comment in review_comments + issue_comments if not comment["bot"]}
    return sorted(logins - {"ghost"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--users")
    arguments = parser.parse_args()
    pull_requests = load_pull_requests(arguments.repo)
    review_comments = load_comments(arguments.repo, "pulls/comments", REVIEW_COMMENT_JQ, pull_requests)
    issue_comments = load_comments(arguments.repo, "issues/comments", ISSUE_COMMENT_JQ, pull_requests)
    all_reviews = [review for pr in pull_requests.values() for review in pr["reviews"]]
    users = arguments.users.split(",") if arguments.users else select_users(pull_requests, review_comments, issue_comments, all_reviews)
    evidence_directory = pathlib.Path(arguments.out) / "_evidence"
    evidence_directory.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    for login in users:
        commits = load_commits(arguments.repo, login)
        markdown, summary = render_evidence(login, arguments.repo, pull_requests, review_comments, issue_comments, all_reviews, commits, today)
        (evidence_directory / f"{login}.md").write_text(markdown)
        print(summary)


main()
