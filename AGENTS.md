# Eventmaxxer

This is a portable agent distro for finding and applying to events. Read EVENTMAXXER.md
when asked to start or continue an event campaign. Use the current agent's supported
computer-use tools and spreadsheet connectors. No hidden RSVP APIs, browser credential
extraction, detection evasion, or headless application scripts.

Private applicant information and campaign state belong outside this repository, by
default ~/.local/share/eventmaxxer/. Never commit personal profiles, registration answers,
application history, logs, credentials or tracker IDs. Examples must be fictional.
Existing user authorization carries forward within scope. A schedule adds no authority.

For development, run python3 -m unittest discover -s tests -v. Tests use temporary private
state and fake agent processes; never use live applications to test code. Preserve existing
campaigns and schedulers. Do not deploy a second scheduler for the same account.
