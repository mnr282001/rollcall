from __future__ import annotations

# Display name -> per-provider identifiers. Only one real, OAuth-authenticated
# identity exists for this build (see checklist.md's architecture pivot note);
# every other name is deliberately absent so a query for it exercises the
# "user not found" path (Phase 5) rather than returning fabricated data.
_USERS = {
    "nayab": {
        "jira_account_id": "61e9d1c998cd6100706712a6",
        "github_username": "mnr282001",
    },
    # Genuinely zero-activity real accounts, for exercising the "no recent
    # activity" path (Phase 5) without fabricating data: a Jira app account
    # never has assigned issues, and a real GitHub user with no commits in
    # our visible repos never has any there either.
    "idle": {
        "jira_account_id": "557058:f58131cb-b67d-43c7-b30d-6b58d40bd077",
        "github_username": "torvalds",
    },
}


def lookup_user(name: str) -> dict | None:
    return _USERS.get(name.strip().lower())
