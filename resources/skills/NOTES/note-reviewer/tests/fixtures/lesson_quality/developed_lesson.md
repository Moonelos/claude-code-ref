# When Mira's kiosk may reuse a price

Mira's kiosk sells blue notebooks. Given a sequence of requests, you will learn to explain when it may reuse a saved price, why that price can differ from the price book, and why a failed lookup sometimes produces an error even though a price is still stored. You need only variables and `if` statements.

## Start with the decision Mira needs to make

The price book is authoritative: it holds the current price. The kiosk keeps a cache, meaning a saved result it can reuse instead of reading the price book again. Reuse saves a read, but a saved result cannot reveal a later change by itself.

Our fictional kiosk permits reuse for five time units after a successful read. All requests are sequential, take no time, and use one integer clock. A price-book read returns its current price or fails. The kiosk does not change the price book.

A cache entry contains two values: `price` and `expires_at`. After a successful read at time `t`, it stores `(price, t + 5)`. This gives us a decision the kiosk can actually perform: reuse an entry only if the current time is less than its deadline. Equality is already too late. This five-unit reuse duration is often called a time to live, or TTL.

## Follow one notebook price through a change

The cache begins empty, and the notebook costs 12 credits. At time 0, Mira receives a request. There is no saved result to reuse, so the kiosk reads the price book. The read succeeds; it returns 12 and saves `(12, 5)`.

At time 3, the price book changes to 15. Nothing contacts the kiosk to report that change, so its saved entry remains `(12, 5)`. At time 4, a customer requests the price. The kiosk compares `4 < 5`, gets true, and returns the saved 12 without reading the book. The cache's deadline also remains 5: reuse does not start a new five-unit interval.

```text
Time                 0              3       4       5       6
Price book           12 ------------>15 --------------------15
Saved cache entry    (12, 5) ------------------------------>(15, 11)
Request result       12                     12      error   15
                                            ^       ^       ^
                                       4 < 5:   5 < 5:   new read
                                       reuse    false    succeeds
                                                read fails
```

The two rows for the book and cache matter: at time 3 only the book changes. At time 5 the cached tuple still exists, but the deadline prevents returning it. At time 6 a successful read finally replaces it. The visual tracks stored data separately from permission to use it.

Thus “valid for reuse” does not mean “equal to the current price book.” Time 4 demonstrates the difference: the saved price satisfies the kiosk's reuse rule even though it is no longer current. This model accepts that tradeoff; it does not promise every displayed price is current.

## Why a stored price cannot rescue the failed request

At time 5, checking `5 < 5` produces false. The kiosk must now read the book. In this trace that read fails. The old value is still 12, and its deadline is still 5; neither fact changed because a read failed. Returning 12 would require an exception to the reuse rule. Our model provides no such exception, so the request returns an error and leaves the entry unchanged.

Keeping expired data in memory is harmless under this rule because each request checks the deadline before using it. Deleting it would not make the failed request succeed either: the kiosk still has no permitted price to return.

At time 6 another request arrives, and the book is available. The old entry again fails the deadline check, so the kiosk reads 15, returns it, and stores `(15, 11)`. The deadline comes from this successful read, not from the previous deadline or the source's time-3 edit.

## Apply the decision to a different trace

Suppose a successful read at time 10 stores `(20, 15)`. The price book changes to 22 at time 12. Requests arrive at 14 and 15; the price book is unavailable at both times. A request at 17 can read it successfully. What does each request return, and what remains stored?

Work from the condition before considering availability:

- At 14, `14 < 15` is true, so return 20 and keep `(20, 15)`. The kiosk does not contact the book. Its unavailability therefore cannot make this request fail, and the hit does not move the deadline to 19.
- At 15, `15 < 15` is false, so attempt a read. That read fails: return an error and keep `(20, 15)`. Its continued presence does not renew permission to use it.
- At 17, the entry is still expired. A successful read returns 22 and replaces it with `(22, 22)`: the second 22 is a deadline calculated as `17 + 5`, not a copy of the price.

The request at 14 tests whether you choose the reuse branch before asking about book availability. The request at 15 tests the exact boundary. Together they explain why the same unavailable book can accompany either a successful response or an error.

This lesson covers only this sequential decision. Concurrent requests, different clocks, proactive refresh, and retrying within one request would require additional rules and are outside the model.
