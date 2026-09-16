# Keeping a kiosk price cache correct

## What you will learn

Given a request trace, explain when a cached price may be returned, why a displayed price can lag the price book, and what the kiosk must do when the price book is unavailable. This is a first lesson for readers who know variables and `if` statements but have not studied caches.

## The fictional system

Mira's kiosk sells one item, a blue notebook. The price book is authoritative. It initially records 12 credits and changes to 15 credits at time 3. Requests are sequential, take no time, and use one integer clock. A price-book read either returns its current price or fails; there are no writes through the kiosk.

The cache starts empty. A successful read at time `t` stores `(price, expires_at = t + 5)`. A stored entry is valid exactly when `t < expires_at`. A hit returns it without contacting the price book or changing its deadline. An empty or expired cache requires a price-book read. A failed read returns an error and leaves the cache unchanged; expired entries may remain stored but may never be served.

## Validity

TTL is an admission policy for reuse. Distinguish logical validity from physical residency, and freshness from authority. Hits do not implement sliding expiration. The boundary predicate is strict.

## Trace

| Time | Event | Cache after event | Kiosk result |
| --- | --- | --- | --- |
| 0 | Request; price book available | `(12, 5)` | 12 |
| 3 | Price book changes to 15 | `(12, 5)` | No request |
| 4 | Request | `(12, 5)` | 12 |
| 5 | Request; price-book read fails | `(12, 5)` | Error |
| 6 | Request; price book available | `(15, 11)` | 15 |

## Consistency

The time-4 result exhibits bounded reuse without invalidation. Authority remains with the price book. Cache coherence and immediate freshness are separate concerns. Treat the deadline as a lease on reuse, not proof of source equality.

## Failure handling

Fail closed on expiration. The time-5 error preserves the validity invariant despite residual state. Retry at the next request. Do not conflate a resident value with a permissible response.

## Transfer

Move the last successful fill to time 10 and the failed request to time 15. Predict the result and justify it using the same invariant.

Answer: error. Physical residency does not establish logical validity.

## Operational scope

This model excludes concurrent requests, clock disagreement, proactive refresh, and retries within a request. Those are separate design problems.
