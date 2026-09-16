# Jobs, Leases, Heartbeats, Fencing, Retries, and Reconciliation

> **Who this is for**: engineers new to distributed work.

A job represents work. A lease assigns it temporarily. A heartbeat renews the lease. Fencing blocks
old owners. Retries repeat failures. Reconciliation repairs differences.

> **Key insight**: distributed work has several mechanisms.

⚠️ Failures can cause duplicates.
