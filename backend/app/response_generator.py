from __future__ import annotations


def _format_issues(issues: list[dict]) -> str:
    if not issues:
        return "no open JIRA issues"
    lines = [f"  - {issue['key']} ({issue['status']}): {issue['summary']}" for issue in issues[:5]]
    more = f"\n  ...and {len(issues) - 5} more" if len(issues) > 5 else ""
    return f"{len(issues)} JIRA issue(s):\n" + "\n".join(lines) + more


def _format_commits(commits: list[dict]) -> str:
    if not commits:
        return "no recent commits"
    lines = [f"  - [{commit['repo']}] {commit['message']} ({commit['sha']})" for commit in commits[:5]]
    more = f"\n  ...and {len(commits) - 5} more" if len(commits) > 5 else ""
    return f"{len(commits)} recent commit(s):\n" + "\n".join(lines) + more


def _format_pull_requests(pull_requests: list[dict]) -> str:
    if not pull_requests:
        return "no open pull requests"
    lines = [f"  - [{pr['repo']}] #{pr['number']}: {pr['title']}" for pr in pull_requests]
    return f"{len(pull_requests)} open pull request(s):\n" + "\n".join(lines)


def generate_response(name: str, activity: dict) -> str:
    """Combines JIRA + GitHub activity into one conversational answer."""
    issues = activity["jira_issues"]
    commits = activity["github_commits"]
    pull_requests = activity["github_pull_requests"]

    if not issues and not commits and not pull_requests:
        return f"{name} doesn't have any recent JIRA or GitHub activity."

    return (
        f"Here's what {name} has been working on:\n\n"
        f"JIRA: {_format_issues(issues)}\n\n"
        f"GitHub commits: {_format_commits(commits)}\n\n"
        f"GitHub PRs: {_format_pull_requests(pull_requests)}"
    )
