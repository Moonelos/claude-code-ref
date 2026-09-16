# Does the deadline itself count as valid?

This micro-lesson answers one question for readers who already know the kiosk's reuse rule: return a stored price only when `now < expires_at`; otherwise read the price book, returning an error if that read fails.

## Check equality explicitly

Mira's kiosk holds `(price=12, expires_at=5)`. At time 5 a customer asks for the price. Substituting into the condition gives `5 < 5`, which is false: a number is not less than itself. The kiosk must read the price book. If that read fails, it returns an error, even though 12 remains stored. Storage alone does not satisfy the condition.

## Try a nearby time

At time 4, with the same entry and an unavailable price book, does the request fail? No: `4 < 5` is true, so the kiosk returns 12 without contacting the book. The change from 4 to 5 switches which branch runs. No wider cache-design lesson is intended here.
