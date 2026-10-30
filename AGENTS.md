# Agent instructions

## Reviewing bugs

Rate each bug from 1 to 10 on how often it would happen and how bad it would be. If the two scores multiplied are below 5, just file it as an issue and leave the code alone.

- Score >= 5: fix it now, add a regression test, push.
- Score < 5: `gh issue create` with both scores and the failure scenario; do not touch the code.
- Only realistic scenarios count. Run the review skills (`/code-review`, `ponytail:ponytail-review`) after every big feature push.

## Integrity rules

- Never edit `fixtures/ground_truth.jsonl` to make a test or metric pass. Fix the code.
- Never commit a metric, benchmark number or sample output that did not come from a real run.
- Offline and synthetic data only. No network calls, paid APIs or secrets.
