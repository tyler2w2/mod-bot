import os

TOKEN                = os.environ["DISCORD_TOKEN"]
LOG_CHANNEL          = int(os.environ["LOG_CHANNEL"])
APPEAL_CATEGORY      = int(os.environ["APPEAL_CATEGORY"])
BOT_APPROVAL_CHANNEL = int(os.environ.get("BOT_APPROVAL_CHANNEL", "0"))  # unused but kept safe

APPEAL_ROLE = int(os.environ["APPEAL_ROLE"])

STAFF_ROLES = [
    int(r.strip())
    for r in os.environ["STAFF_ROLES"].split(",")
    if r.strip()
]
