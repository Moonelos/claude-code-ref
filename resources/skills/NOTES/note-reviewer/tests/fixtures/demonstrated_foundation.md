# A Lease Turns Permanent Ownership into a Timed Claim

> **Who this is for**: engineers new to leases.

## One crashed worker must not own work forever

Without an expiry, worker A can claim job 42, crash, and block it permanently. A lease stores an
owner plus an expiry, allowing another worker to claim the job after time runs out.

```text
t=00  owner=worker-a, expires=30
t=20  worker-a renews       → owner=worker-a, expires=50
t=55  worker-b claims       → owner=worker-b, expires=85
```

The coordinator changes the stored owner only after comparing the current time with the expiry.
At `t=40`, worker B must still be rejected; at `t=55`, the same request succeeds. Temporary
ownership does not prove that worker A stopped running, so effects still need a fencing or
idempotency boundary.

> **The near-miss**: a lease is not a lock that proves exclusivity forever; it is a timed claim whose
> old owner may continue after expiry.

> **Key insight**: expiry restores progress after owner failure but creates a stale-owner race.

## What breaks first

⚠️ A pause longer than the lease can let worker B acquire the job while worker A resumes. Do not use
an unfenced lease when two concurrent effects would corrupt state.
