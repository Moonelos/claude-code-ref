# Filled audit examples

These blocks show the expected depth for a realistic collection: `kafka-notes/`, "Kafka from zero to
production," written for developers who know basic programming but not messaging. The product facts
show the level of specificity expected. Re-verify any fact before you reuse it in a real audit.

Formats are defined in `audit-reports.md`. These examples show what a useful block looks like: exact
evidence, the reader's harm, and a repair someone can act on without asking a follow-up question.

## Per-note block (`_audit/foundations.audit.md`)

```text
# foundations/03_consumer_groups.md (212 lines)
ORDERING: role foundation; PASS; payoff line 14/212; the opening shows two consumers splitting partitions 0–3 of `orders` before any configuration.
EXPLANATION: FAIL; teach-back FAIL (missing: first failure); problem, owned state (partition assignment), actor (group coordinator), transition (consumer C2 joins → P2,P3 move to C2), and misconception (“every consumer gets every message”) are present, but nothing says what breaks when a consumer stalls past `max.poll.interval.ms`.
LESSON: FAIL; see lesson_quality.audit.md :: Consumer groups and rebalancing.
VISUAL: FAIL; the rebalance involves 3 actors (C1, C2, coordinator) and a time-ordered handoff, explained only in prose at lines 88–131.
PRACTICE: FAIL; the note ends at a config table with no recap or check-yourself questions.
Summary: 0 critical, 1 high, 2 med, 0 low

FIX-HIGH: Rebalance handoff at lines 88–131 has no diagram, so the reader must track three actors and the revoke/assign order in their head, which is the point where the lesson loses them. Add after line 90, introduced as “watch which partitions C1 gives up before C2 receives them”:
    ```mermaid
    sequenceDiagram
      participant C1 as Consumer C1 (P0–P3)
      participant G as Group coordinator
      participant C2 as Consumer C2 (new)
      C2->>G: JoinGroup
      G->>C1: rebalance: revoke P2, P3
      C1->>G: commit offsets P2=41, P3=17; ack
      G->>C2: assign P2, P3
      C2->>C2: resume P2 at 41, P3 at 17
    ```
  Follow it with prose explaining why the commit comes before the assignment: if C1 skipped the commit, C2 would resume at the last committed offset and reprocess messages.
FIX-MED: No first failure — add a short trace in which C1 spends 6 minutes on one batch with `max.poll.interval.ms=300000`, gets kicked from the group, and its later commit fails with `CommitFailedException`. That is the symptom readers will see in production logs.
FIX-MED: No retention block — end with a 4-bullet recap of the causal chain and questions such as:
    Q: A group has 3 consumers and `orders` has 2 partitions. What does the third consumer do?
    A: It stays idle. A partition is assigned to at most one consumer in a group, so the extra consumer receives nothing until a partition becomes free. This is why the consumer count beyond the partition count adds failover capacity but no throughput.
```

Notice what makes this block useful. It cites line numbers. The diagram uses the note's own names
and offsets. It says what the prose around the diagram must explain. The practice question tests a
prediction rather than a definition.

## Clean per-note block

```text
# production/07_monitoring_lag.md (164 lines)
ORDERING: role implementation; PASS; payoff line 11/164; a runnable `kafka-consumer-groups --describe` with real LAG output comes first.
EXPLANATION: PASS; teach-back PASS (missing: none); lag is defined as log-end offset minus committed offset, traced with P0: 1200 − 1150 = 50, and the “lag = slowness” misconception is ruled out with an idle-producer example.
LESSON: PASS; see lesson_quality.audit.md :: Operating consumers.
VISUAL: PASS; the producer → partition → consumer offset positions are shown in a before/after table at line 40 and interpreted.
PRACTICE: PASS; the recap and 3 questions include a changed condition (lag growing on one partition only → hot key).
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: alert thresholds, the dashboard query, and the recovery runbook reach operationalized depth.
```

## Landscape report (`_audit/landscape.audit.md`)

```text
# Current landscape — 2026-09-29
Research: COMPLETE
Baseline: the notes teach Kafka 3.6 with ZooKeeper-based clusters
Searched: Apache Kafka release notes 3.7–current; upgrade notes; KIP index (accepted/released); Confluent and AWS MSK docs; Kafka Summit/Current talks from the last year; the strimzi and kafka-ui repositories

## ZooKeeper removal (KRaft only)
Status: DEPRECATED
Relevance: CHANGES-BASELINE
In collection: stale — production/02_cluster_setup.md teaches a ZooKeeper deployment
Why it matters: a reader following the setup note builds a cluster that no current major version supports, and the upgrade path requires migrating to KRaft first
Suggested placement: rewrite production/02_cluster_setup.md around KRaft; move ZooKeeper to a migration note
Sources: https://kafka.apache.org/documentation/#upgrade (primary, 2026-09-29)

## New consumer rebalance protocol (KIP-848)
Status: GA
Relevance: ADD-TO-NOTES
In collection: absent
Why it matters: server-side incremental assignment removes the stop-the-world rebalance that 03_consumer_groups.md presents as unavoidable
Suggested placement: new section at the end of foundations/03_consumer_groups.md, after the classic protocol is taught
Sources: https://cwiki.apache.org/confluence/display/KAFKA/KIP-848 (primary, 2026-09-29); Kafka release notes (primary, 2026-09-29)

## Share groups / queues for Kafka (KIP-932)
Status: PREVIEW
Relevance: MENTION
In collection: absent
Why it matters: work-queue semantics without the partition count limiting consumer count, which is exactly the limit the notes teach in 03
Suggested placement: the "What's changing" section of the README, and a forward pointer from 03's partition-limit discussion
Sources: https://cwiki.apache.org/confluence/display/KAFKA/KIP-932 (primary, 2026-09-29)
```

Each item says what it changes for this reader and where it goes. A bare list of release-note
headlines would not do that.

## Lesson-quality block with a structural repair

```text
# Consumer groups and rebalancing
Files: foundations/03_consumer_groups.md, foundations/04_offsets.md
LESSON: FAIL
Reader: knows topics and partitions from 01–02; promised to explain and predict consumer-group behavior
Evidence: 03 introduces the assignment trace (developed), then states “commit after processing” (stated, not developed); 04 explains commits but uses a new `payments` example, so the reader cannot connect commits to the rebalance in 03.
Reasoning burden: the reader must work out alone why commit timing decides duplicates versus loss during a rebalance, which is the central production decision.
Visual support: missing; needs one evolving sequence diagram (the one in the per-note report), replayed with a crash between processing and commit.
Structure: MERGE, REORDER
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Commit semantics are taught apart from the rebalance that makes them matter — merge 04's offset sections into 03 after the assignment trace, and keep the `orders` example.
Proposed sequence: assignment → a consumer joins (rebalance) → where does the new owner resume? → committed offset → a crash before the commit (duplicates) → a crash after an early commit (loss) → the choice between them.
Content mapping: 03 lines 1–131 keep; 04 lines 20–95 move into 03 after line 131; 04's `payments` example is replaced with `orders`; 04 lines 96–140 (manual commit API) become a reference section.
Example development: C1 owns P2 at offset 41 → processes 41–45 → crashes before committing → C2 resumes at 41 and reprocesses 41–45; the diagram is replayed with the crash marked.
Rewrite sample: When C1 crashes after processing messages 41–45 but before committing, the coordinator still holds 41 as P2's committed offset. C2 takes over P2 and asks where to start; the answer is 41, so messages 41–45 are processed twice. Nothing is lost, but anything those messages did, such as charging a card, happens twice. Committing before processing flips the risk: C2 would start at 46, and if C1 died mid-batch, messages 41–45 would never be processed.
Acceptance task: C1 commits offset 46 and then crashes while processing 46–50. Predict where C2 resumes, and which messages are duplicated or lost. (Expected: C2 resumes at 46; nothing is lost or duplicated, because the commit covered only completed work.)
```

## Reader-path transfer checkpoint

```text
TRANSFER: FAIL
Checkpoint: after foundations/04_offsets.md
Scenario: auto-commit every 5s is on; the consumer crashes 3s after the last auto-commit, having processed 30 more messages. What happens to those 30?
Reasoning: they are reprocessed by the next owner, because the committed offset predates them; auto-commit gives at-least-once behavior.
Evidence: missing premise — 04 never explains that auto-commit runs on a timer independent of processing (line 52 only lists `enable.auto.commit=true` in a table).
```
