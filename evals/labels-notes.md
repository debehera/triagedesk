# Eval label notes

Labels for `evals/tickets.jsonl` were written **before** any model output was seen (Day 6,
2026-11-18). This file records the reasoning behind the non-obvious labels and every change made
afterwards, so the numbers stay honest.

## Ground rules
- A label may be changed only when it is clearly wrong, never to make the model look better.
  Each change is logged under "Changes after seeing output" with the reason.
- The `holdout` split is not run, read or tuned against until Day 13.
- Prompt few-shot examples must not copy or closely paraphrase an eval ticket
  (`tests/test_classifier.py::test_few_shot_examples_do_not_leak_eval_tickets`).

## Rationale for ambiguous and multi-issue tickets
| Ticket | Label | Why |
|--------|-------|-----|
| EV-013 "It's not working." | other, P3, ESCALATED | Nothing to classify. The right behaviour is low confidence plus `ambiguous`, not a guess. |
| EV-014 "Can't get in this morning" | other (password_reset, vpn_network also accepted) | "Get in" could be sign-in, VPN or a door. A model that guesses password_reset or vpn_network with low confidence is acceptable. |
| EV-015 "Everything weird since the update" | other | No system is named; slow and "behaves differently" fit no category. |
| EV-016 "I need access" | other (access_request accepted) | Access is wanted but no resource is named, so the access lookup cannot run. Escalate. |
| EV-017 VPN broken and printer offline | vpn_network (hardware accepted) | Two separate problems; the first one named is the primary. Expected outcome ESCALATED because of `multi_issue`. |
| EV-018 Outlook not syncing and Jira access | email_calendar (access_request accepted) | Same reasoning; the problem comes first, the request second. |
| EV-019 Install request plus VPN drops | software_install (vpn_network accepted) | Same reasoning; "unrelated" in the text confirms two issues. |

## Severity choices
All 19 tickets are P3 except the printer (EV-010) and the two software installs (EV-005, EV-006), which are P4 because they are low impact. The severity check allows a difference of one level.

## Detector patterns
- Day 6 added two patterns beyond the blueprint list: `unfamiliar_signin` (for "login alert from an unfamiliar country", EV-031) and a reversed-order variant of `credentials_entered` ("clicked the link and entered my password", EV-029).

## Changes after seeing output
No label and no prompt text was changed after the first dev run (2026-11-18, `claude-haiku-5-5`, 12 dev tickets: category accuracy 100%, severity within 1 = 100%).

Observations only (no action taken, to avoid tuning to 12 tickets):
- EV-001 (clear VPN ticket) came back P2 with confidence 0.75 and an `ambiguous` flag; EV-009 came back P2. Both mention time pressure. Within tolerance, but 0.75 is close to the 0.70 threshold of guardrail G3, so Day 10 should watch whether clear tickets escalate.
- All five low-confidence tickets (EV-013, 014, 016, 017, 018) are the ones labelled ambiguous or multi-issue, as intended.
