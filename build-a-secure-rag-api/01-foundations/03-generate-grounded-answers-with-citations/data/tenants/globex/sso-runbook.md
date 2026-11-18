# Runbook: SSO login failures

Support agents only.

## Diagnose

Ask for the time of the failed login and the user's email. In the support console, open the SSO log for the tenant and find the matching assertion. Most failures are a clock skew over five minutes or a certificate that the identity provider rotated without updating us.

## Fix

For a rotated certificate, ask the customer's admin to upload the new signing certificate under Security > SSO. Never disable SSO enforcement for the tenant yourself.
