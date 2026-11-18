# Rotating API keys

API keys belong to a workspace, not to a person. Rotate a key whenever someone who knew it leaves the team, or at least every 90 days.

## Rotate a key without downtime

Create a new key under Settings > API keys, deploy it to every service that calls the API, confirm the old key shows no traffic for a day, then revoke the old key. Revoked keys stop working immediately.
