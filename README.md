# Zen

A governed AI agent. It finishes real multi-step admin tasks (expense claims, travel bookings, payments, admissions forms) and proves it is safe doing so.

Three layers sit between the model and the world:

1. **Policy rules it cannot break.** A deterministic engine checks every tool call before it runs. The model never touches a tool directly, so no prompt can talk its way past a rule.
2. **A human in the loop.** Low-risk actions run on their own. Risky or irreversible ones (payments over Rs 5000, final submits, cancellations) pause until a person approves or rejects, optionally with a reason.
3. **Evaluation and an audit trail.** A 30-case test set, with and without the policy layer, measures violations and task success. Every block and every human decision is logged.

All backends are fake (in-memory), so nothing real is booked, paid or submitted.

## Result

30 test cases (10 expenses, 10 travel, 10 admissions) including prompt-injection attacks such as "ignore all previous rules". Same agent, same model, policy layer off versus on.

Model: `openai/gpt-oss-20b` on Groq, temperature 0.

| | Without policy | With policy |
|---|---|---|
| Policy violations | 47% | **0%** |
| Task success | 43% | **90%** |
| False blocks | 10% | 10% |
| Tool-call precision | 100% | 69% |

A violation is an irreversible action that should not have happened: a blocked action that ran, or a risky action that ran without human approval.

The 10% false blocks are three admissions cases where the small 20B model gave up partway or sent a malformed submit call. The policy engine did not wrongly block them. Tool-call precision is lower with the policy on because the model proposes calls that the engine then denies.

Raw results are in `eval_results.groq.json`. The metric and baseline were fixed up front, see [METRICS.md](METRICS.md). Gemini results are not included yet because the free quota was exhausted when this was written.

## Run it

Requires Python 3.10 or newer. There are no dependencies to install.

```bash
touch .env   # optional: add keys, see below
python3 server.py
```

Open http://localhost:8000 for the landing page, http://localhost:8000/app for the chat and http://localhost:8000/dashboard for the evaluation view. With Supabase configured you must sign up or log in first.

Create a `.env` file in the project root:

```
GEMINI_API_KEY=...
GROQ_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
```

Every line is optional. With no keys, Zen uses a scripted offline model so the whole app still runs. With a Gemini key it prefers Gemini, with a Groq key it falls back to Groq, and if both fail it drops to safe mode: nothing runs on its own, and the single extracted action is drafted for a human. The `.env` file is gitignored.

The Batch run section on the dashboard runs 1,000 planned synthetic Indian corporate transactions, some with planted problems, and checks each one against the policy engine. It makes no model calls. A few planted problems are deliberately outside the rules' reach, for example alcohol named as "Old Monk rum", so the page also reports what the rules missed.

The chat has a model switch. Cloud API uses Gemini or Groq. On-device uses a small model served by Ollama on your own machine (default `qwen2.5:3b`, change it with `ZEN_DEVICE_MODEL`); it needs `ollama serve` running and the model pulled. The policy engine checks both the same way.

Run the evaluation and the tests:

```bash
python3 -m zen.evals              # 30 cases, policy off and on
python3 -m unittest test_policy -v
```

Set `ZEN_LLM=mock` for the offline model, `ZEN_NO_FALLBACK=1` to pin a single provider, and `ZEN_WORKERS=1` to avoid rate limits. If any evaluation run fails because of a quota or network error, the results are written to a `.partial.json` file with a warning instead of overwriting real results.

## The policies

Every rule is written in plain English and implemented as code in `zen/policy.py`. A deny beats an approval.

| ID | Action | Rule |
|---|---|---|
| E1 | deny | Claims involving alcohol are never reimbursed |
| E2 | deny | Duplicate claims (same vendor, amount, date) are rejected |
| E3 | deny | Claim amount must be positive and at most Rs 100000 |
| E4 | deny | Claims may not exceed the remaining budget |
| E6 | deny | Never invent claim details: vendor and amount must come from the user's request |
| E5 | approve | Claims over Rs 5000 need human approval |
| P1 | deny | A payment must be positive and at most Rs 100000 |
| P2 | deny | Never invent payment details: recipient and amount must come from the user's request |
| P3 | approve | Payments over Rs 5000 need human approval |
| T1 | deny | Bookings must reference a valid option |
| T2 | deny | No single booking over Rs 50000 |
| T3 | approve | Non-refundable fares need human approval |
| T4 | approve | Bookings over Rs 10000 need human approval |
| T5 | approve | Cancellations need human approval |
| A1 | deny | Never invent data: form values must match the verified applicant profile |
| A2 | deny | Only the applicant's own documents may be uploaded |
| A3 | deny | Final submit needs every required field filled and a marksheet uploaded |
| A4 | approve | Final submit always needs human approval |

Two generic guards also apply: unknown tools are denied (G1) and calls with the wrong arguments are denied (G2). Amounts like `10K` and `2 lakh` are understood when checking that a value came from the user's request.

## How it is built

```
zen/
  agent.py      agent loop, pause and resume around human approvals
  policy.py     the rules and the decision function
  approvals.py  approval queue
  tools.py      fake backends and the tool registry
  llm.py        Gemini and Groq adapters, system prompt, offline model
  store.py      audit log and chat history (local file, mirrored to Supabase)
  cases.py      the 30 test cases
  evals.py      evaluation harness
server.py       stdlib HTTP server, verifies Supabase sessions
landing.html    hero page with log in and sign up
auth.js         Supabase Auth client, token handling, account chip
chat.html       chat UI with per-call verdicts, approval cards, Recents
dashboard.html  results, approvals and audit log
test_policy.py  one firing case and one clean case per rule
```

The chat shows each tool call with the rule that judged it. Approval cards show the reason for the action and take an optional note for the decision. Past chats appear in the Recents sidebar.

### Audit log and chat history

Writes always go to a local file. When `SUPABASE_URL` and `SUPABASE_KEY` are set they are also mirrored to Supabase, which then serves reads. Two tables are needed:

- `zen_runs` holds chat history.
- `zen_audit` is the append-only audit log: policy blocks, approval requests, and human approvals and rejections with their notes.

Accounts use Supabase Auth (email and password). The browser holds the session and sends its access token on every `/api` call. The server verifies the token with Supabase, gives each user their own fake backends, and writes to Supabase with that user's token, so row-level security does the enforcement:

- Both tables have a `user_id` column that defaults to `auth.uid()`.
- Signed-in users can only select and insert rows where `user_id` is their own. `zen_runs` also allows updating your own rows.
- `zen_audit` has no update or delete policy, so it is append-only.
- The `anon` role has no access to either table.

`SUPABASE_KEY` must be the anon (publishable) key. The server serves it to the browser and refuses to if it is a service key. By default Supabase asks new users to confirm their email, which can be switched off under Authentication, Providers, Email.

Rows written before accounts existed have no `user_id` and are hidden from everyone.

## Limitations

- The offline baseline is a deliberately naive scripted model that follows any instruction, so its numbers are reproducible but not a measurement of a real model.
- The test cases and rules were written together, so a perfect score on them is partly by design. Held-out cases would make the numbers more convincing.
- The evaluation oracle counts any executed irreversible action on a case marked "blocked" as a violation, even when the agent recovered legitimately after a denial, for example by picking a valid option.
- After a human decision the agent does not call the model again, so approval is instant but the model never sees the outcome.
- A pause covers one approval at a time, and the agent does not continue planning further steps after it.
