# Trust-First Product Cleanup Design

## Goal

Make Alforaij feel like a calm decision tool for real estate users: first answer the user's question, then show evidence, then offer deeper controls.

## Product Direction

The primary user emotion to optimize is confidence under financial uncertainty. The first screen should focus on one action: describe a property or need and get a clear evaluation. Secondary actions such as export, account, alerts, and dashboards stay available, but they should not compete with the first decision.

## Scope

This pass is intentionally conservative:

- Fix obvious source and API reliability issues that undermine trust.
- Reframe the first viewport around search and decision.
- Repair accessibility issues found by browser audit.
- Remove only clearly temporary review artifacts and files proven unused.
- Avoid a full frontend framework migration or broad file split in this pass.

## UX Requirements

- Search input must be visible and prominent in the first meaningful viewport.
- Result and waiting states must explain what happened in plain Arabic.
- If some sources fail, the product should still return usable partial results.
- Tabs must remain keyboard and screen-reader friendly.
- Export buttons should feel secondary until a report exists.

## Technical Requirements

- Keep the current Python stdlib server and vanilla frontend for this pass.
- Do not remove existing user-facing features.
- Do not delete unknown user files unless they are confirmed unreferenced generated artifacts.
- Preserve Arabic RTL behavior and existing brand assets.

## Error Handling

- `/api/health` should never block the user experience on slow external database calls.
- `/api/analyze` should return a bounded response instead of leaving the UI waiting indefinitely.
- Source failures must be reported as source status, not as a broken product state.

## Testing

- Run focused unit tests around source parsing, health, and search behavior.
- Run a local browser smoke test for the main screen.
- Run accessibility audit after ARIA changes.
