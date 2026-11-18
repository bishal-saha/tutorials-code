# Runbook: stuck data exports

Internal. For support agents only. Do not paste this runbook into customer replies.

## Symptoms

An export stays in the running state for more than two hours, or the export worker logs ERR-7731 repeatedly. The customer sees no progress on the Settings > Exports page.

## Recovering a stuck export

1. Find the export id from the customer's ticket and open it in the admin console.
2. Check the export worker queue depth. If it is above 500, page the data platform on-call before doing anything else.
3. Restart the export worker for the customer's region from the admin console. This releases the lock that ERR-7731 reports.
4. Requeue the export. Each export can be requeued three times; the retry limit is internal and should not be mentioned to the customer.

## After recovery

Tell the customer the export has been restarted and give a fresh estimate. Add the export id and the time of the restart to the incident log.
