#!/usr/bin/env bash
# One mypy run per workspace member: each member's tests/ is a separate root
# with its own top-level conftest, so members cannot share one run.
set -euo pipefail
status=0
for member in services/*/ libs/*/; do
    member=${member%/}
    roots=("$member/src")
    [[ -d "$member/tests" ]] && roots+=("$member/tests")
    MYPYPATH="$(IFS=:; echo "${roots[*]}")" uv run --locked mypy "${roots[@]}" || status=1
done
exit "$status"
