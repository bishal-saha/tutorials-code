# Runbook: recovering stuck exports

Support agents only.

## Symptoms

A payroll export has been running for over two hours, or the export service reports ERR-9054. The customer's export page shows no progress.

## Recovering a stuck export

1. Look up the export id in the support console.
2. Restart the export worker for the customer's region. ERR-9054 means the worker lost its database connection; a restart clears it.
3. Requeue the export once. If it sticks again, escalate to the payroll engineering on-call with the export id.

## After recovery

Confirm with the customer that the export completed and attach the file checksum to the ticket.
