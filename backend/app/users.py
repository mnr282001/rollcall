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
}


def lookup_user(name: str) -> dict | None:
    return _USERS.get(name.strip().lower())
