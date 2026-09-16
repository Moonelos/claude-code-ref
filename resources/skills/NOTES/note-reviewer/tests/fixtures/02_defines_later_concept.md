# A Fencing Token Orders Owners

> **Who this is for**: engineers new to fencing.

A fencing token is a monotonically increasing owner generation. Storage accepts token 8 and later
rejects a delayed write carrying token 7, so an expired worker cannot overwrite the current owner.

> **Key insight**: storage, not the worker, enforces owner freshness.
