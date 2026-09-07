"""Reject an unexpected deployment account or project before publishing."""
import json
import os
import urllib.request


def get(path):
    request = urllib.request.Request(
        "https://api.vercel.com" + path,
        headers={"Authorization": "Bearer " + os.environ["VERCEL_TOKEN"]},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify():
    for key in ("VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID"):
        if not os.environ.get(key):
            raise SystemExit(f"Missing repository secret: {key}")
    if get("/v2/user")["user"]["username"] != "why-only-english":
        raise SystemExit("Unexpected Vercel account; deployment blocked")
    team_id = os.environ["VERCEL_ORG_ID"]
    project_id = os.environ["VERCEL_PROJECT_ID"]
    team = get(f"/v2/teams/{team_id}")
    if team["slug"] != "why-only-englishs-projects" or team["billing"]["plan"] != "hobby":
        raise SystemExit("Unexpected team or plan; deployment blocked")
    project = get(f"/v9/projects/{project_id}?teamId={team_id}")
    if project["name"] != "stocksignal" or project["accountId"] != team_id:
        raise SystemExit("Unexpected project; deployment blocked")
    print("Verified why-only-english / stocksignal / Hobby")


if __name__ == "__main__":
    verify()
