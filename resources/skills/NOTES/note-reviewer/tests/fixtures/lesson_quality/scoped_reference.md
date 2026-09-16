# Kiosk cache decision reference

Scope: a lookup sheet for readers who already understand the kiosk lesson. It specifies the fictional sequential model; it does not teach cache design. Requests take no time and share one integer clock. The price book is authoritative; reading it returns its current price or fails.

## Rules

| State at request time `t` | Action | Result and subsequent state |
| --- | --- | --- |
| Stored `(price, expires_at)` and `t < expires_at` | Reuse; do not read the book | Return stored price; keep entry and deadline |
| Empty cache or `t >= expires_at`; read succeeds with `p` | Read the book | Return `p`; store `(p, t + 5)` |
| Empty cache or `t >= expires_at`; read fails | Read the book | Return error; keep existing state |

Source edits do not notify or invalidate the cache. Stored expired entries are never served. No proactive refresh, concurrent requests, differing clocks, or within-request retries are defined.

## Example lookup

Mira starts empty. A successful request at 0 reads 12 and stores `(12, 5)`. The book changes to 15 at 3. A request at 4 returns 12 and keeps `(12, 5)`. At 5 a failed book read produces an error and leaves `(12, 5)`. At 6 a successful read returns 15 and stores `(15, 11)`.
