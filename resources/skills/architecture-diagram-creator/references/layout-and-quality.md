# Layout and quality

## Visual defaults

- Helvetica; title 28–30 px, subtitle 15–16, boundary labels 14, card text 12–14, legend 14. Enlarge the canvas/cards before shrinking text.
- Under the subtitle, add a thin orange separator (`strokeColor=#FF9900;strokeWidth=2;`). Span the main architecture/title width, stopping before the sidebar. Leave 12–18 px below the subtitle so it does not touch text. Apply this presentation accent to both AWS and neutral views.
- Cards start at 140 × 130 px (120 × 120 only for short labels); centered icons nominally 48 × 48 with labels **inside the outer card**. Match visible artwork size and weight, accounting for transparent SVG margins and wide brand marks; see [icons.md](icons.md#optical-size-consistency). Tint by role; keep neutral colors for external actors.
- Suggested free gaps: 100–180 px horizontally, 100–120 vertically; expand for branching. Grid spacing 10 px. Boundary padding ≥30 px, extra top padding for headings.
- Default measurable minima: 20 px between parallel line centerlines; 20 px straight outward endpoint stubs; 10 px between routes and unrelated cards; 10 px badge/text clearance. These are chosen design defaults, not AWS specifications. Increase spacing with thick lines/large arrowheads. `--min-gap` changes the parallel-line threshold.
- White/light presentation is the portable baseline. If dark mode is requested, use a coherent tested palette and inspect the export; don't assume `light-dark()` works in every renderer.

Use the source examples' titled canvas, tinted cards and teal numbered sidebar as visual inspiration. Do not copy their clutter, stale topology, floating endpoints or connections to icons.

## Routes and narrative

Reserve heading space inside every boundary before routing. Keep routes at least 10 px away from the heading text area, including wrapped lines; cards must not overlap it. Crossing the boundary's empty body is allowed. For long headings, increase top padding/available space, widen the frame, or use a separate root-level `archRole=label` with explicit geometry. Do not conceal a collision with an opaque label background. The validator estimates a conservative text band for top-aligned inline boundary headings from font, width, spacing and line breaks; `archHeaderHeight` can increase the reserved height. Non-top/rotated headings require a separate label. This estimate is not a font-rendering guarantee: inspect every heading and nearby route in the exported image, especially narrow frames and peer-account boundaries.

Lay out the main flow left-to-right or top-to-bottom, then allocate separate lanes for returns and asynchronous branches. Reserve routing lanes before drawing edges. Don't hide overlap by drawing one line on top of another. Prefer re-layout to many bends. Perpendicular crossings are warnings to review, not always avoidable errors; use a clear bridge/jump in editor-managed layouts or restructure if direction becomes ambiguous.

Number meaningful **flow stages**, not every icon or every edge. Default to a sidebar for small diagrams too; omit only if the user asks. A step may cover several related edges. Use the same step ID for its badge, edge(s) and legend row. Start at 1; no duplicates or orphan explanations. Do not imply a strict chronological sequence among concurrent flows: explain branching/concurrency in the sidebar.

Place each canvas badge beside a clear segment of its own step, closer to that segment than to any unrelated route (including unnumbered routes). Prefer a position near the source exit or the first clear segment after a bend, so readers discover the number as they follow the flow. A distant segment may pass proximity checks while weakening the composition; use it only when local placement is crowded or ambiguous. Keep the 10 px clearance; avoid ambiguous positions between branches or near crossings. For a step with several edges, proximity to one representative branch is sufficient. The validator warns on equal or closer unrelated routes using badge-center distance to finite segments; visually verify the association and move the badge or adjust the routing when ambiguous.

Each sidebar row: a separate blue numbered badge, short bold action title, one concise sentence. Use the same badge graphic on the canvas and in the sidebar: `rounded=1;fillColor=#007CBD;strokeColor=#000000;strokeWidth=2;fontColor=#FFFFFF;fontStyle=1;shadow=1;glass=0;align=center;verticalAlign=middle;`. Canvas badges are 28 × 28 with 16 px text; sidebar badges are 40 × 38 with 22 px text. Do not replace the sidebar badge with an inline blue number. Leave 12 px between its right edge and the description.

The light-blue sidebar (`fillColor=#EDF3FF;strokeColor=#6C8EBF;strokeWidth=1;`) begins level with the title and extends to the bottom of the architecture. Put it ≥40 px right of all architecture content and expand it if rows need more room. Sparse optional edge labels should clarify a protocol, branch or otherwise ambiguous relationship; avoid repeating the sidebar. Prefer “Submit job”, “Store result”, “Human review” over SQL statements. A dashed line has a stated meaning (for example asynchronous flow or fallback), consistent throughout that diagram.

## Validation and rendering

### Composition review before delivery

Use both deterministic validation and an LLM visual review of the exported image. The validator checks measurable geometry; the agent judges flow readability, semantic scope and composition, including whether badges feel attached to the start of their flow. This is the existing render-and-review pass, not a separate agent or scoring pipeline. A passing validator is necessary but not sufficient. After rendering, review both the complete composition at reading scale and close-ups of modified regions. Check boundary proportions, unused space, alignment, routing detours, heading/card spacing and consistent icon weight as well as collisions.

For collision fixes, first consider a different card-face anchor, a nearby routing lane, deliberate heading line breaks, or a local card adjustment. When a connection creates crowding or a long detour, consider whether small shifts of neighboring nodes—even those not involved in the connection—would improve the composition. Prefer the arrangement that makes all affected connections clearer overall while preserving the main flow and architectural boundaries. Resize a boundary only when its content, readable heading or necessary routing space needs it. Do not stretch a frame simply to move its heading out of a connector's way. Avoid routes running along boundary borders, where communication can be confused with containment. The validator rejects a route segment that follows a boundary edge within 10 px for at least 20 px; a perpendicular crossing remains valid.

Before accepting a resize, compare the old and new composition: does the added space serve content or routing, and are margins balanced with neighboring groups? Unexplained empty bands, disproportionate frames, and new long detours require another layout pass even when geometry checks pass. Do not enforce a universal density percentage: sparse layouts can be intentional, and infrastructure boundaries have different meanings.

Use a render → inspect → improve → revalidate → re-render loop until visible defects identified in the review are resolved. Inspect the final render after the last layout edit, not an earlier export. Keep a short working review note covering the changed region, overall balance and remaining issues; do not claim an aesthetic review solely from zero XML errors. This review proceeds autonomously without asking the user to approve each refinement.

The script checks the generated contract: XML/IDs/references/finite geometry, explicit boundary anchors, outer-card terminals, orthogonal route segments, outward stubs, card penetration/clearance, card/annotation overlap, parallel route spacing, and flow-badge/legend agreement. It warns on perpendicular crossings and long implementation-heavy labels. It does not infer architectural truth, verify every cloud stencil, or measure actual rendered fonts.

Imported files outside the contract can be inspected, but must not get a clean bill of health for geometry the checker cannot resolve. No automatic fixer should retarget endpoints or relocate nodes without recomputing the whole path and rechecking it.

Export the required PNG with the bundled helper:

```bash
python3 <skill-directory>/scripts/export_png.py docs/example.drawio
```

It writes the same filename stem beside the source; `--output` overrides that path. Inspect the complete composition, dense branches and icon/card endpoints. Confirm every icon renders, text is unclipped, numbers are readable, and arrowheads end at outer faces. If Desktop cannot run, report that rendering and PNG export were unavailable; structural checks alone are not a visual pass.
