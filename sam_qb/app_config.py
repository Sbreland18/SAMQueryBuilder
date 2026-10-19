"""Static application settings (the Build GUI edits GITHUB_REPO / GITHUB_BRANCH / SUPPORT_EMAIL)."""
APP_NAME = "SAM Ad Hoc Query Builder"
APP_ID = "SAMAdHocQueryBuilder"
PUBLISHER = "Hancock County School District"
GITHUB_REPO = "Sbreland18/SAMQueryBuilder"
GITHUB_BRANCH = "main"
SUPPORT_EMAIL = ""   # where Help > Report a bug sends email reports (set in the Build GUI)


def latest_json_url(repo: str = GITHUB_REPO, branch: str = GITHUB_BRANCH) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/latest.json"
