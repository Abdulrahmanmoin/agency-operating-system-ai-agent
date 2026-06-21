# Demo video — ready-made prompts

Copy-paste prompts for recording an AgencyOS demo, tuned to the BrightBrew data.

**Before recording:**
- Restart the backend (`uv run python scripts/serve_api.py`) so the longer Plan/Proposal output
  and the latest report code are live.
- Pre-paste these into a notes file and copy from there during recording to avoid typos on camera.

---

## Setup: a meeting brief to attach (Story 1 needs an input)

Save this as `brightbrew-brief.txt` and attach it with the 📎 button at the start of Story 1:

```
Client: BrightBrew, a specialty coffee shop in Austin.
Call notes — kickoff with founder Maya.

Maya wants to go direct-to-consumer. Right now they only sell in-store.
Goals: launch an online Shopify store to sell beans and merch, and refresh
the brand (logo feels dated, wants a warmer look). Also wants a launch-week
marketing push to drive traffic.

Budget: around $40k total. Timeline: wants it live in about 8 weeks before
the holiday season. Maya mentioned she's the only approver and can be slow
to respond. Product photography isn't ready yet. She wasn't sure whether she
wants a subscription option or just one-time purchases.
```

---

## Story 1 — From a messy client call to a validated proposal

Paste these one at a time (each builds on the last):

1. `Extract the requirements from this brief.`
2. `What's unclear or missing? Ask me anything you need.`
   - Clarification will pause and ask — answer in plain text, e.g.:
   - `One-time purchases only for now, no subscription. Yes, $40k is the total budget.`
3. `Now build a phased project plan.`
4. `Break the plan into tasks with priorities and dependencies.`
5. `What are the risks?`
6. `Draft a client-facing proposal.`
7. `Run a quality review on everything.`

**Shortcut version** (autonomy in one line instead of step-by-step):

```
Handle this end to end — requirements, plan, tasks, risks, and a client-ready proposal.
```

> On camera: open the **Deliverables** panel on the right and download the **Project Plan** and
> **Proposal** as PDF — they're now long and sectioned.

---

## Story 2 — From plan to live delivery + PM progress report

1. `Create ClickUp tickets for these tasks.`
   - ClickUp will show drafts and pause — approve with:
   - `Yes, create them.`
2. Optional ad-hoc ticket to show flexibility:
   - `Create a ticket to call the client Friday about the photography.`
3. `Generate a progress report for the PM.`

> On camera, walk through the report: % complete, the **[DONE] / [IN PROGRESS] / [NOT STARTED]**
> split, the per-developer breakdown, and especially the **ClickUp-vs-GitHub divergences**
> (e.g. *"Conduct SEO audit — ClickUp: complete · GitHub: no branch or PR yet"*). Then download it
> as PDF.

---

## Bonus one-liners (good for showing intent routing)

- `Just extract the requirements — nothing else.` — shows it runs only what you ask.
- `Draft a proposal.` — with nothing prior, the Manager asks before chaining prerequisites.
- `Show me a progress report.` — works with no source material; reads live ClickUp + GitHub.
