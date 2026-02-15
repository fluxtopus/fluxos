"""
# REVIEW:
# - Hard-coded host list requires manual sync with planner prompts and env overrides; easy to drift.

Centralized configuration for allowed HTTP hosts in the playground.

This is the single source of truth for which external APIs can be called
from workflow HTTP nodes. Keep this in sync with:
- task_planner_agent.py (LLM prompt documentation)
- .env PLUGIN_HTTP_ALLOW_HOSTS (if set, overrides these defaults)
"""

# Default allowed hosts for the HTTP plugin
# These are free, public APIs that require NO authentication
# Organized by category for clarity
ALLOWED_HOSTS = [
    # News & Content
    "hacker-news.firebaseio.com",

    # Code & Development
    "api.github.com",

    # Data & Reference
    "restcountries.com",
    "api.coingecko.com",
    "zenquotes.io",  # Inspirational quotes
    "opentdb.com",  # Trivia questions

    # Fun & Testing
    "pokeapi.co",
    "jsonplaceholder.typicode.com",
    "randomuser.me",
    "catfact.ninja",
    "dog.ceo",
    "dummyjson.com",
    "api.agify.io",
    "api.publicapis.org",

    # Weather
    "wttr.in",

    # Notifications & Webhooks (user-facing endpoints)
    "discord.com",  # Discord webhooks
    "discordapp.com",  # Discord webhooks (legacy domain)
    "hooks.slack.com",  # Slack incoming webhooks
    "api.telegram.org",  # Telegram Bot API
    "ntfy.sh",  # ntfy push notifications
]

# Generate comma-separated string for environment variable
ALLOWED_HOSTS_ENV_STRING = ",".join(ALLOWED_HOSTS)
