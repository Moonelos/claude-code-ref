# Eval: python-service-architecture skills

Πώς ελέγχουμε αν τα `python-service-architecture` και
`python-service-architecture-audit` κάνουν τους agents να γράφουν συνεπή,
καθαρό κώδικα. Η ιδέα: agents χτίζουν από το μηδέν ρεαλιστικά services
χρησιμοποιώντας **μόνο** τα skills, και μετά ανεξάρτητοι agents κάνουν audit
στον κώδικα και λένε **γιατί** έγινε κάθε λάθος (κανόνας που λείπει, κανόνας
που συγκρούεται, ή κανόνας που αγνοήθηκε).

Το μέτρο επιτυχίας δεν είναι «μηδέν ευρήματα». Είναι:

- μηδέν ευρήματα με ρίζα **(b) ασαφής/αντιφατικός κανόνας**,
- κανένας υπερ-σχεδιασμός που τον προκάλεσε κανόνας του skill,
- τα ίδια σημεία να μη χρειάζονται «μάντεμα» από διαφορετικούς builders.

Τα behavioral defects (edge cases σε failure paths, encoding, timing) τα
μετράμε **χωριστά** και δεν είναι κριτήριο επιτυχίας του γύρου: το σύνολό τους
δεν έχει όριο, και ο στόχος «μηδέν defects στο πρώτο build» οδήγησε στους
γύρους v3–v7 σε κανόνες υπερπροσαρμοσμένους στα briefs A/B. Τα βρίσκει το
audit skill («Behavioral probes»), όχι το builder skill.

## Κόστος

| Βήμα | Agents | Tokens (περίπου) | Χρόνος |
| --- | --- | --- | --- |
| Builders | 3 | ~350k ο καθένας | ~25–30 λεπτά (παράλληλα) |
| Audits | 3 | ~180k ο καθένας | ~5 λεπτά ο καθένας |
| Σύνολο ανά γύρο | 6 | ~1.6M | ~35 λεπτά |

## Βήμα 0: snapshot

Πάντα πάνω σε αντίγραφο, ώστε να μπορείς να αλλάζεις τα skills όσο τρέχει ο
γύρος και να συγκρίνεις εκδόσεις.

```bash
RUN=v2                                   # όνομα γύρου
EVAL=/tmp/arch-eval                      # ή ένα scratch directory
mkdir -p $EVAL/skills-$RUN $EVAL/$RUN
cp -R resources/skills/PYTHON/* $EVAL/skills-$RUN/
```

Κανόνες για να είναι έγκυρο το test:

- Οι builders **δεν** διαβάζουν το `python-service-architecture-audit`.
- Κάθε builder σηκώνει δική του PostgreSQL σε δικό του φάκελο/port (στον
  πρώτο γύρο δύο agents μοιράστηκαν ένα cluster και μπερδεύτηκαν).
- Τα audits είναι report-only.

## Βήμα 1: οι 3 builders (παράλληλα)

Στο Claude Code: «ξεκίνα 3 background agents με τα παρακάτω prompts». Αντικατέστησε
`$SKILLS` με `$EVAL/skills-$RUN` και `$OUT` με `$EVAL/$RUN`.

### Κοινό προοίμιο (βάλε το στην αρχή κάθε builder prompt)

```text
You are a backend engineer building a new Python service from scratch. You MUST follow the architecture skill exactly as written.

Skills (read these files first, and follow their reference routing; also read sibling skills they point to when relevant):
- $SKILLS/python-service-architecture/SKILL.md (and its references/ and assets/)
- Sibling skills are in the same $SKILLS directory (python-repository-setup, python-code-conventions, python-settings-config, python-sqlmodel-alembic, pytest, python-logging, otel-observability). Resolve any "fallback: ../../<skill>" paths against $SKILLS.
Do NOT read or use anything under python-service-architecture-audit.

Build in: $OUT/<service-name>/ (a single-service repository; create pyproject with uv). If you need a throwaway PostgreSQL, create your own data directory under that folder on a free port; do not touch other clusters.
```

### Κοινό κλείσιμο (στο τέλος κάθε builder prompt)

```text
When done, reply with: the source tree, the list of application actions and their entry points, and any place where the skill instructions were ambiguous, contradictory, or where you had to guess (be specific and honest — this feedback is the main purpose of the exercise).
```

### Brief A: expense-approvals (HTTP API, state transitions, outbox)

```text
Brief — "expense-approvals" HTTP API (FastAPI, PostgreSQL via SQLModel/SQLAlchemy async):
- POST /claims: an employee submits an expense claim (amount, currency, category, description). Amount limits per category come from configuration. Idempotent per client-supplied Idempotency-Key header.
- GET /claims/{id} and GET /claims?status=&cursor= (cursor pagination, page size limit from config).
- POST /claims/{id}/approve and /reject: only callers with the manager role; only PENDING claims can transition; reject requires a reason. Concurrent approve/reject of the same claim must be safe.
- After approval, notify the payroll system via its HTTP API (POST /payouts) — this external call must not happen inside the DB transaction and must not be lost if payroll is down (choose and implement an appropriate pattern).
- Health/readiness endpoints.
- Auth: assume a bearer token whose claims (sub, roles) are already verified by a gateway and passed as headers X-User-Id and X-User-Roles.

Requirements: production-quality code, full typing (mypy strict), unit tests with fakes, integration tests may be written but you don't need a running Postgres (skip if unavailable). Run ruff, mypy and the unit tests via uv and make them pass. Include import-linter contracts if the skills require them.
```

### Brief B: shipment-worker (SQS consumer, periodic loop, uncertain writes)

```text
Brief — "shipment-worker", a long-running worker:
- Consumes "order.paid" events from an SQS queue (JSON body: order_id, customer_id, items[{sku, qty}], address). Messages can be duplicated and can arrive malformed.
- For each new order: persist it (PostgreSQL), then create a shipment through the carrier's HTTP API (POST /shipments, returns tracking_number). The carrier API sometimes times out after actually creating the shipment and supports an Idempotency-Key header.
- Transient carrier failures: retry with backoff (policy from config) by returning the message to the queue with a visibility delay; permanent rejections: mark the order as SHIPMENT_FAILED and delete the message; malformed messages go to the DLQ.
- A second periodic loop every N minutes finds orders stuck in SHIPMENT_PENDING for longer than a configured threshold and re-attempts them.
- Graceful shutdown on SIGTERM; liveness/readiness over a tiny HTTP server.

Requirements: production-quality code, full typing (mypy strict), unit tests with fakes. Use boto3 (via asyncio.to_thread) or aioboto3 — your choice per the skill. You don't need real AWS/Postgres; integration tests may be written and skipped if unavailable. Run ruff, mypy and the unit tests via uv and make them pass. Include import-linter contracts if the skills require them.
```

### Brief C: ticket-triage (LLM, agent tool, fallback)

```text
Brief — "ticket-triage" HTTP API (FastAPI, PostgreSQL):
- POST /tickets: a customer support ticket arrives (subject, body, customer_tier). The service classifies it with an LLM (OpenAI via the approach the skill prescribes) into category (billing/technical/account/other), priority (P1–P4) and a short summary, using structured output.
- Business rules: enterprise-tier customers are never below P2; if the model's confidence is below a configured threshold, or the model output is invalid, or the model is unavailable, the ticket goes to a HUMAN_REVIEW state instead of CLASSIFIED — the ticket must always be stored.
- Record the prompt version and model name with each classification.
- GET /tickets/{id}; POST /tickets/{id}/reclassify (only for HUMAN_REVIEW tickets, re-runs the model).
- A small agent variant: for technical tickets, an agent with a tool "search_known_issues(query)" (backed by a DB table of known issues) suggests up to 3 related known issues, stored with the ticket.
- Health/readiness endpoints.

Requirements: production-quality code, full typing (mypy strict), unit tests with fake model handles (no live LLM calls). You don't need real Postgres; integration tests may be written and skipped if unavailable. Run ruff, mypy and the unit tests via uv and make them pass. Include import-linter contracts if the skills require them.
```

### Προτεινόμενο: ένα 4ο brief που το skill δεν έχει «δει»

Το παράδειγμα του worker στο `api-and-workers.md` μοιάζει πολύ με το Brief B, άρα
το B μετράει λιγότερο τη γενίκευση. Σε κάθε γύρο καλό είναι να προστίθεται ένα
καινούργιο brief με διαφορετικό σχήμα, π.χ.:

```text
Brief — "report-exporter": a CLI + scheduled batch job. `export-reports --since DATE` reads invoices from a PostgreSQL database the service does NOT own (read-only), aggregates them per customer, renders an XLSX per customer, uploads each to S3, and records which exports succeeded in its own small table so a rerun skips finished customers. A Kafka consumer also triggers single-customer exports on "customer.requested_report" events. Health endpoint not needed; exit codes matter.
```

## Βήμα 2: τα 3 audits (ένα ανά service, μόλις τελειώσει ο builder)

```text
Run an architecture audit of a Python service, following an audit skill exactly.

Skill: $SKILLS/python-service-architecture-audit/SKILL.md
It depends on $SKILLS/python-service-architecture/ (SKILL.md, references, assets). Sibling skills are under the same $SKILLS directory; resolve "fallback: ../<skill>" paths against it. Run the bundled script from $SKILLS/python-service-architecture-audit/scripts/audit_service.py.

Target service: $OUT/<service-name>/ (package src/<package>).

This is REPORT-ONLY: do not modify any file, do not create FEEDBACK.md or plans. Do the full static + semantic audit as the skill describes.

Reply with:
1. Static script output summary (counts per rule, and which hits you confirmed vs dismissed as false positives, with why).
2. Semantic findings: each with classification (Violation/Improvement/Preference), file:line evidence, and the skill rule it breaks.
3. For each finding, your judgment of the ROOT CAUSE in the architecture skill: (a) the rule is missing, (b) the rule exists but is ambiguous/buried/contradicted elsewhere (quote where), (c) the rule is clear and the builder just ignored it. This is the most important part.
4. Any place where the audit skill itself was unclear or its script produced noise.
5. Also: is any part of the service over-engineered relative to the brief BECAUSE a skill rule pushed it there? Name the rule.

The brief the builder received, for context: <paste the brief>
```

## Βήμα 3: σύγκριση και διορθώσεις

Για κάθε service, γέμισε μία γραμμή:

| Service | Script V/R (επιβεβαιωμένα) | Semantic V/I/P | Ρίζα (a)/(b)/(c) | Υπερ-σχεδιασμός από κανόνα | «Μάντεψα» σημεία του builder |
| --- | --- | --- | --- | --- | --- |

Μετά:

1. Ομαδοποίησε τα ευρήματα που εμφανίζονται σε **2+ services**: αυτά είναι
   αδυναμίες του skill, όχι τύχη.
2. **(b)**: λύσε τη σύγκρουση σε ένα σημείο (ένας κανόνας, ένας ιδιοκτήτης,
   βλ. `resources/skills/CLAUDE.md` «Rule ownership»).
3. **(a)**: πρόσθεσε κανόνα μόνο αν χρειάστηκε σε πραγματικό service.
   Ένα behavioral εύρημα μπαίνει στο builder skill μόνο αν είναι (b) ή αν το
   ίδιο defect εμφανίστηκε σε **2+ διαφορετικά briefs**. Αλλιώς, και για κάθε
   (c), γίνεται probe στο audit skill («Behavioral probes»).
4. **Υπερ-σχεδιασμός**: ξαναδιατύπωσε τον κανόνα που τον προκάλεσε, με ρητό
   trigger («μόνο όταν…»).
5. **Script noise**: false positive → διόρθωση στο script + regression test στο
   `python-service-architecture-audit/tests/`.
6. Μετά από κάθε αλλαγή:

```bash
cd resources/skills/PYTHON/python-service-architecture-audit
uv run --with pytest pytest -q tests
uv run --python 3.13 --no-project python scripts/audit_service.py ../python-service-architecture/assets/canonical_service/src/my_service
cd ../python-service-architecture
PYTHONPATH=assets/canonical_service/src uv run --no-project \
  --with "sqlalchemy[asyncio]" --with sqlmodel --with aiosqlite \
  python -B -m unittest discover -s assets/canonical_service/tests/integration
cd ../python-repository-setup
uv run --python 3.13 --no-project python -m unittest discover -s tests  # τα δύο templates δεν αποκλίνουν
uv run --python 3.13 --no-project python scripts/update_toolchain.py --check  # pins συνεπή σε όλα τα αρχεία
```

   Έλεγξε και για σπασμένα anchors μετά από μετονομασία ή μεταφορά ενοτήτων
   (grep για το παλιό heading σε **όλα** τα skills, όχι μόνο στα δύο).

## Ιστορικό

| Γύρος | Ημερομηνία | Script ευρήματα (A/B/C) | Κύρια ρίζα | Σημείωση |
| --- | --- | --- | --- | --- |
| v0 (baseline) | 2026-09-29 | 9 / 5 / 6 | (b) σχεδόν όλα | Κενό: πού ζουν loops και consumers → νέο `workers/` |
| v1 | 2026-09-29 | 1 (FP) / 0 / 0 | συμπεριφορά (κατάταξη σφαλμάτων, 401 ως «μόνιμο») | Υπερ-σχεδιασμός από «commit πριν από την κλήση σε μοντέλο» και από τον πίνακα UoW. Διορθώθηκαν μετά τον γύρο, χωρίς να ξαναδοκιμαστούν |
| v2 | 2026-09-29 | 0V+7R / 0V+5R / 0V+1R | (b) CI, κυρίως (c) | Και τα τρία builds πέρασαν Ruff, strict mypy, unit tests και import-linter, αλλά τα ανεξάρτητα audits βρήκαν πραγματικά λειτουργικά σφάλματα. Έγινε repair pass· βλ. παρακάτω. |

## Αποτελέσματα v2

Snapshot: commit `901bc4b4005f49794d6c21227ac26c5de0aeddea`,
`/tmp/arch-eval/skills-v2`. Οι builders δεν διάβασαν το audit skill. Τα
audits ήταν report-only και έτρεξαν μετά από κάθε αρχικό build.

| Service | Script V/R αρχικά | Semantic ευρήματα | Ρίζα | Υπερ-σχεδιασμός από κανόνα | Builder guesses |
| --- | --- | --- | --- | --- | --- |
| expense-approvals | 0/7, όλα τα R επιβεβαιώθηκαν | Αβέβαιη παράδοση payroll, ελλιπής μετάφραση DB σφαλμάτων, worker lifecycle, HTTP status mapping, technical routes σε bootstrap, ανεπαρκής έλεγχος concurrency | 1 κοινό (b) για CI· τα υπόλοιπα (c) | Κανένας | Payroll idempotency/replay, μόνιμη απόρριψη, category limits, read visibility |
| shipment-worker | 0/5, 4 επιβεβαιώθηκαν, 1 FP (`Inbox` Protocol) | Carrier 404, malformed SQS envelopes, concurrent success/rejection, duplicate ID, batch isolation, redrive policy | 1 κοινό (b) για CI· τα υπόλοιπα (c) | Κανένας | Carrier replay contract, address schema, provider status taxonomy |
| ticket-triage | 0/1, επιβεβαιώθηκε | OpenAI error classification, χαμένα low-confidence metadata, διπλό integration instance | 1 κοινό (b) για CI· τα υπόλοιπα (c) | Κανένας | Crash πριν από το πρώτο commit, known-issue fallback/search, metadata retention |

**Κοινό (b):** Το architecture skill ζητούσε CI μόνο όταν υπήρχε ήδη CI,
ενώ το audit skill και το repository-setup ζητούσαν CI ακόμη και σε νέο
repository. Ο κανόνας στο architecture skill ευθυγραμμίστηκε με τα άλλα δύο.
Το ψευδές εύρημα για το ρητά προβλεπόμενο worker `Inbox` αφαιρέθηκε από το
audit script και καλύπτεται με regression test. Δεν προέκυψε κανόνας που
εξανάγκασε υπερ-σχεδιασμό ή επαναλαμβανόμενο σημείο αρχιτεκτονικής όπου οι
builders έπρεπε να μαντέψουν. Οι ελλείψεις συμπεριφοράς είχαν σαφείς κανόνες
που δεν εφαρμόστηκαν στον πρώτο γύρο.

**Repair pass:** Οι ίδιοι builders διόρθωσαν τα ευρήματα στα scratch services.
Ruff, strict mypy, unit tests και import-linter ξαναπέρασαν και στα τρία.
Τα unit tests έγιναν 7/9/10 για A/B/C. Το A πέρασε επιπλέον ένα integration
test σε απομονωμένο PostgreSQL για concurrent submit/approve/reject και
outbox recovery· η πρώτη δοκιμή migration αποκάλυψε rollback bug που
διορθώθηκε. Το παγωμένο audit script μετά τις διορθώσεις έδωσε 0/0 για A,
0/1 για B (μόνο το γνωστό `Inbox` FP), 0/0 για C. Το live audit script έδωσε
103 passing tests και 52 passing subtests, μαζί με το νέο regression test.

Απομένει επαλήθευση με πραγματικό SQS/carrier για το B, με PostgreSQL/live
model για το C και με πραγματικό payroll για το A. Η εγγύηση replay των
παρόχων για σταθερό `Idempotency-Key` είναι εξωτερική υπόθεση στα A/B.
Επομένως ο γύρος δείχνει ότι οι κανόνες είναι πλέον συνεπείς, αλλά **δεν**
τεκμηριώνει «μηδέν προβλήματα» στην πρώτη υλοποίηση ή production readiness.

## Γύρος v3: πρώτη προσπάθεια με implementation checks

Snapshot: `/tmp/arch-eval/skills-v3`. Τρεις νέοι builders πήραν μόνο το brief
και τα builder skills. Δύο αρχικοί agents είδαν κατά λάθος το ιστορικό v2 του
παρόντος εγγράφου· αποκλείστηκαν και αντικαταστάθηκαν από fresh agents με
αυτοτελές brief. Το C έμεινε blind. Τα αποτελέσματα παρακάτω αφορούν μόνο τα
τρία blind builds. Οι builders δεν διάβασαν το audit skill.

| Service | First-pass gates | Static audit μετά το freeze | Συμπέρασμα |
| --- | --- | --- | --- |
| expense-approvals | Ruff, strict mypy, 4 unit, 4 import contracts | 0V/5R | Ένα επιβεβαιωμένο κενό coverage στα contracts και τέσσερα άμεσα `datetime.now` στο `db/`. Δεν έγινε PostgreSQL integration· το ίδιο το build αναφέρει σφάλμα επιλογής YAML layer από `.env`. |
| shipment-worker | Ruff, strict mypy, 15 unit, import contracts | 0V/6R | Δύο άμεσα `uuid4` στα actions είναι επιβεβαιωμένα. Τα μεγάλα repository methods χρειάζονται semantic review· τα `Liveness` και `Inbox` notices απαιτούν κρίση ως boundary protocols. Δύο PostgreSQL tests έγιναν skip χωρίς database. Η carrier replay παραδοχή γράφτηκε στο handoff αλλά όχι στο port docstring. |
| ticket-triage | Ruff, strict mypy, 17 unit, 3 PostgreSQL integration, Alembic, pre-commit/pre-push, Docker smoke | 0V/0R | Η builder-initiated PostgreSQL δοκιμή βρήκε και διόρθωσε ordering bug πριν το freeze. Δεν έγινε live model test. |

Ο v3 γύρος δείχνει καλύτερη πρώιμη επαλήθευση στο C, αλλά **δεν περνά** το
κριτήριο «χωρίς προβλήματα στην πρώτη προσπάθεια» για A/B. Τα παραπάνω static
hits ελέγχθηκαν από τον συντονιστή, όχι από νέο ανεξάρτητο semantic auditor:
το διαθέσιμο agent thread limit δεν επέτρεψε νέα audit threads. Άρα δεν
ισχυριζόμαστε πλήρες semantic pass για κανένα από τα τρία services.

Μετά το freeze του v3, το live architecture skill απέκτησε ρητό mapping
provider statuses → port outcomes, υποχρεωτικό search για άμεσο χρόνο/UUID
στις εσωτερικές layers, επαλήθευση πλήρους import-contract coverage και
έλεγχο της replay παραδοχής στο port docstring. Αυτή η νεότερη έκδοση
**δεν είχε ακόμη δοκιμαστεί από νέο blind builder** κατά το freeze του v3.

## Γύρος v4: δεύτερος blind έλεγχος A/B

Snapshot: `/tmp/arch-eval/skills-v4`. Δύο fresh builders πήραν αυτοτελή
briefs A/B και μόνο τα builder skills, χωρίς το παρόν έγγραφο, τα παλιά builds
ή το audit skill. Δύο χωριστοί report-only auditors διάβασαν το audit skill
μετά το freeze.

| Service | First-pass verification | Static V/R | Κύρια semantic ευρήματα |
| --- | --- | --- | --- |
| expense-approvals | 237 tests σε PostgreSQL 16, 4 import contracts, Ruff, strict mypy, pre-commit | 0/2, και τα δύο R απορρίφθηκαν ως FP/review-only | Batch 20 payouts με lease 60s μπορεί να ξεπεράσει το lease λόγω 10s timeout ανά item· HTTP 409 σε replay μπορεί να σημαίνει ήδη δημιουργημένο payout· τα unattempted leased rows αυξάνουν attempt counter. Επίσης cursor σε σελίδα μόνο με corrupt rows δεν προχωρά. |
| shipment-worker | 159 tests με PostgreSQL 14, moto SQS και carrier stub, 4 contracts, Ruff, strict mypy, pre-commit | 0/0 | Δεν υπάρχει visibility heartbeat ούτε δηλωμένο bound για batch 10 × carrier timeout έναντι queue visibility. SIGTERM grace 45s μπορεί να λήξει μέσα σε πλήρη παρτίδα. Ένα integrity error σε settle/record attempt δεν έχει item-level handling. |

Η δομή, οι atomic transitions, η βασική idempotency ροή και η επαναφορά μετά
από crash πέρασαν ουσιαστική δοκιμή. Οι auditors βρήκαν όμως παραγωγικά timing
και failure-path κενά, άρα ούτε ο v4 είναι clean first pass. Δεν μετρήσαμε ως
skill defects επιλογές προϊόντος που δεν καθορίζει το brief (π.χ. self-approval,
ακριβές σχήμα address, health semantics).

Μετά τα audits, το live skill απέκτησε κανόνες για lease/visibility sizing,
shutdown με πλήρη παρτίδα, replay-409, attempt counters, conflicting duplicate
keys και cursor progress πάνω από corrupt rows. Οι κανόνες μπήκαν στους
θεματικούς ιδιοκτήτες (`persistence.md`, `api-and-workers.md`, `boundaries.md`)
και το `SKILL.md` παραπέμπει σε αυτούς με implementation checks. Αυτές οι
διορθώσεις **δεν ανήκουν στο v4 snapshot** και χρειάζονται νέο blind round.

## Γύρος v5: επανέλεγχος lease και visibility

Snapshot: `/tmp/arch-eval/skills-v5`. Νέα blind builds A/B και ξεχωριστοί
report-only semantic auditors, χωρίς πρόσβαση των builders σε παλιά ευρήματα.

| Service | First-pass verification | Static V/R | Αποτελέσματα audit |
| --- | --- | --- | --- |
| expense-approvals | 229 tests σε PostgreSQL 16, Docker smoke, Ruff, strict mypy, 4 import contracts, pre-commit | 0/1, R review-only | Το per-item lease διορθώνει τον κίνδυνο του v4. Όμως rejected payout δεν έχει discoverable operator exit, corrupt outbox row μπορεί να σταματήσει τον dispatcher, corrupt claim row σταματά ολόκληρο cursor page, και replay μετά αλλαγή policy μπορεί να δώσει 422 αντί για αρχικό αποτέλεσμα. |
| shipment-worker | 164 tests με PostgreSQL, moto SQS και carrier stub, 2 E2E, Ruff, strict mypy, 4 import contracts | 0/0 | Το visibility budget και το stop ανά item διορθώνουν τα v4 κενά. Όμως schema-valid αλλά μη αποθηκεύσιμο `order.paid` μπορεί να crash-loop το process· whitespace-only tracking number περνά adapter validation και σπάει domain invariant. |

Οι νέοι κανόνες βελτίωσαν τα συγκεκριμένα timing paths, αλλά ο v5 **δεν
τεκμηριώνει καθαρή πρώτη προσπάθεια**. Μετά το freeze προστέθηκαν στους
θεματικούς ιδιοκτήτες κανόνες για storage-compatible validation, per-item
poison records, κοινή validation adapter/domain, replay πριν από μεταβλητή
policy, και αναφορά αποτελέσματος μόνο μετά από επιτυχημένο fenced write.
Το πρώτο skill πρόσθεσε μόνο τους αντίστοιχους ελέγχους handoff.

## Γύρος v6: poison data και replay

Snapshot: `/tmp/arch-eval/skills-v6`. Τα blind builds A/B διακόπηκαν μία φορά
από κοινό `ENOTFOUND` προς το API και συνεχίστηκαν από τις ίδιες συνεδρίες,
χωρίς πρόσβαση στα audit skills ή στα παλιά αποτελέσματα. Το σφάλμα δικτύου
δεν μετρήθηκε ως εύρημα. Ξεχωριστοί auditors έλεγξαν τα frozen services.

| Service | First-pass verification | Static V/R | Αποτέλεσμα semantic audit |
| --- | --- | --- | --- |
| expense-approvals | 142 tests (22 integration, 1 E2E) σε PostgreSQL 16, Docker build, Ruff, strict mypy, import contracts | 0/1, R review-only | Replay μετά αλλαγή policy και poison payout πριν από valid row καλύπτονται. Όμως `NUL` σε description/rejection reason περνά domain validation και απορρίπτεται από PostgreSQL ως raw data error· exact Alembic-head readiness μπορεί να βγάλει παλιά pods εκτός υπηρεσίας κατά rolling migration. |
| shipment-worker | 121 tests (13 integration) σε PostgreSQL 16, Ruff, strict mypy, import contracts | 0/0 | Poison stored row και full-batch SIGTERM καλύπτονται. Όμως Unicode digit ή υπερμεγέθες `Retry-After` μπορεί να προκαλέσει uncaught exception και επαναλαμβανόμενο crash του worker. Consumer retry και sweeper μπορούν να συμπέσουν στο ίδιο order· αυτό βασίζεται στην ανεπιβεβαίωτη εγγύηση carrier idempotency. |

Ο v6 είναι σαφώς καλύτερος στα paths που έσπασαν στον v5, αλλά **δεν
αποδεικνύει μηδέν προβλήματα**. Μετά το freeze ο κανόνας boundary validation
αναφέρει ρητά storage-incompatible text και bounded conversion από untrusted
headers· το persistence περιγράφει κοινό due/claim contract για consumer και
sweeper και πλήρη lease budget· το health guidance αποτρέπει exact-head
readiness σε rolling deploy. Χρειάζεται νέο blind round για αυτές τις αλλαγές.

## Γύρος v7: outbound encoding και πραγματικές αποτυχίες DB

Snapshot: `/tmp/arch-eval/skills-v7`. Δύο νέοι builders διάβασαν μόνο το
builder skill και τα routed references. Το shipment session διακόπηκε μία φορά
και συνεχίστηκε από το ίδιο session. Ξεχωριστοί report-only auditors εξέτασαν
τα frozen services χωρίς προηγούμενα αποτελέσματα.

| Service | First-pass verification | Static V/R | Semantic αποτέλεσμα |
| --- | --- | --- | --- |
| expense-approvals | 194 tests, PostgreSQL 14, Ruff, strict mypy, 4 import contracts | 0/2 (και τα 2 review-only) | Η προηγούμενη αποτυχία σε `Retry-After`, replay μετά από policy change και poison row καλύφθηκε. Παραμένει αδύναμη η μόνιμη ανακάλυψη/επανεκκίνηση των `FAILED` payouts: το runbook υπάρχει μόνο στο `BUILD_REPORT.md`. Το payroll 409 θεωρείται delivered από μη επαληθευμένη παραδοχή. |
| shipment-worker | 208 tests, PostgreSQL 16, moto SQS, carrier stub, Docker image, Ruff, strict mypy, 4 import contracts | 0/2 (και τα 2 review-only) | Μη ASCII `order_id` γίνεται μη κωδικοποιήσιμο HTTP `Idempotency-Key` και μπορεί να ρίξει τη διαδικασία. Η ταξινόμηση DB exceptions χάνει timeout/failover errors που ο dialect τυλίγει ως `DBAPIError`. Readiness με `SELECT 1` δεν ελέγχει schema ή πρόοδο loop. Απεριόριστα unknown retries χρειάζονται μόνιμη operator ανακάλυψη. |

Οι στατικοί έλεγχοι δεν εντόπισαν αυτά τα behavioral gaps. Δεν υιοθετήθηκαν
αυτόματα όλες οι auditor παρατηρήσεις: το brief δεν υπόσχεται snapshot
pagination ούτε απαγορεύει self-approval, ενώ τα υπόλοιπα 409 semantics
απαιτούν πραγματικό provider contract. Τα παραπάνω είναι επαρκή ώστε ο v7 να
**μην περάσει** τον στόχο «σωστό από την πρώτη προσπάθεια». Μετά το freeze
προστέθηκαν στο πρώτο skill και στα references έλεγχοι outbound encoding,
πραγματικών driver errors, schema/progress readiness και operator runbook.

## Trim μετά τον v7

Οι κανόνες των γύρων v3–v7 (snapshot `745a17e`) ξαναεξετάστηκαν με τα
κριτήρια του Βήματος 3. Οι γενικοί αρχιτεκτονικοί κανόνες έμειναν: process
owner σε hybrid, ιδιοκτησία health state, `core/clock.py`, attempt count ως
retry input, domain validation στον adapter, idempotent replay/conflict,
μη-ειδικά 4xx ως unavailable, discoverable operator exit. Οι κανόνες lease,
visibility, grace period, 409 replay, DB error classification, corrupt cursor
και poison/encoding συμπτύχθηκαν σε μία αρχή ο καθένας. Ο πίνακας
«Implementation checks» του `SKILL.md` έγινε μία παράγραφος. Οι λεπτομέρειες
(encoding σε headers, `Retry-After`, attempt counters, consumer/sweeper
overlap, runbook, readiness σε rolling deploy) μεταφέρθηκαν στα «Behavioral
probes» του audit skill.

Επόμενος γύρος (v8): blind builds σε ένα από τα A/B, σε ένα απλό CRUD API
(έλεγχος υπερ-σχεδιασμού) και στο 4ο brief (γενίκευση). Μετράμε χωριστά
αρχιτεκτονική συμμόρφωση και behavioral defects.
