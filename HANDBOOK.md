# Building a Multimodal Document Agent with Muse Code

Your workshop handbook, keep it open while you work.

## 1. Setup

### 1.1 Before you arrive

- **A macOS or Linux laptop.** That's where Muse Code runs. On Windows, you'll need WSL (Windows Subsystem for Linux).
- **git and Python 3.9 or newer.** On a Mac, `xcode-select --install` gets you both. On Linux, use your package manager (include `venv`: on Debian and Ubuntu that's `python3-venv`).
- **Muse Code**, installed by following <https://dev.meta.ai/docs/muse-code>.
- **Your Meta Model API key.** It needs access to `muse-spark-1.3` and `sam-3.1`.
- **A charger.** Keep your laptop plugged in and awake while your agent runs. If it dozes off, every call the agent was waiting on gets dropped.

### 1.2 Get the repo

```bash
git clone https://github.com/meta-models/legal-agent-workshop.git
```

### 1.3 Add your API key

Your key goes in two places. The agent you build uses it to read the case documents, and Muse Code uses it to write that agent with you. Start with the agent:

```bash
cd legal-agent-workshop/agent
cp .env.example .env
```

Open `.env` and paste your key after `MODEL_API_KEY=`. Leave everything else as it is. (Muse Code gets the same key in 1.6.)

### 1.4 Check your setup

Still in `agent/`:

```bash
./helper setup       # installs the SDKs in .venv (OpenAI + MCP), copies the case's 21 documents, checks your key
```

Your agent talks to the Meta Model API with the official OpenAI Python SDK, which `./helper setup` installs into `agent/.venv` (it needs the internet for that, once), along with the MCP SDK that serves the agent's tools. `./helper` always uses that environment, so there's nothing to activate.

If everything looks good, this should read:

```text
INFO Seeded 21 initial documents
INFO Preflight passed: 21 case documents, 21 in inbox
INFO HTTP Request: GET https://api.meta.ai/v1/models "HTTP/1.1 200 OK"
INFO MODEL_API_KEY works: muse-spark-1.3 and sam-3.1 are available.
```

If it says your key `cannot use` a model, grab one of us.

### 1.5 Open the Agent Console

The console shows your agent's runs as they happen: every turn, every tool call, and what came back.

In a new terminal tab:

```bash
cd legal-agent-workshop
python3 ui/ui.py
```

Then open <http://127.0.0.1:8765> in your browser. Leave that tab running for the rest of the workshop.

### 1.6 Start Muse Code

In another terminal tab:

```bash
cd legal-agent-workshop/agent
muse
```
> [!NOTE]
> - The first time, Muse Code asks how to sign in. Choose **Paste an API key** and paste the same key.
> - If it asks whether to trust the folder, say yes.
> - Always start Muse Code from `agent/`. That folder is its whole workspace, and everything you build lives there.


### 1.7 Give Muse Code the ground rules

Make this your first message every time you start Muse Code:

```text
You are my coding assistant. We're in a workshop: I'm learning to build a legal case-investigation agent in this folder, one step at a time. This first message only sets ground rules: don't create, edit, or delete any file until I ask. Reply "Ready" and wait for my first request.

Ground rules:
* When I ask for something, build only that, then stop and report. Write the smallest readable code that does what I asked.
* Change only files in `legal_agent/` and `verification/`, and only the ones I ask about.
* `agent_kit/` is a pre-built library: use it, don't edit it.
* The model chooses every tool call: don't hard-code which tool runs when, and keep anything specific to one case out of the code.

Don't run the agent or the tests unless I ask: I'll run the agent myself from the console. Don't open `.env`, and never print or log API keys or populated environment values. Every completion report lists the files changed, what you ran, and any limitation.
```

Muse Code should reply "Ready" and change nothing. If it starts editing files anyway, press Esc to stop it, then undo its changes from `agent/` with `git checkout -- legal_agent/ verification/`.

## 2. Session 1: Build the agent

By the end of this session you'll have an agent that reads the case documents, records what it can prove, and files a memo. Here's the order:

| Step | What happens |
|---|---|
| 2.1 What's already built | A quick tour of the kit you build on. |
| 2.2 Read the case and the playbook | The task your agent solves, and the system prompt it starts from. |
| 2.3 What an agent loop is | The idea behind the code you're about to write. |
| 2.4 Build the loop | Two prompts to Muse Code. About 5 to 10 minutes. |
| 2.5 Run your agent | Watch it work, one turn at a time, in the console. About 5 to 10 minutes. |
| 2.6 Read the memo | Decide whether you'd sign it. |
| 2.7 Get ready for Session 2 | Catch up if you need to. |

### 2.1 What's already built

You won't write any plumbing today: the repo ships with it. Paths are relative to `agent/`.

| Already built | Path | What it does |
|---|---|---|
| **Tools** | `mcp_server/tools/` | The actions the model can take, served as an MCP server, one file per tool: draft a checklist, read documents (quotes checked against the page), record facts, file the memo. Session 2 adds verification tools. Your loop uses `mcp_client.definitions()` and `mcp_client.run()`. |
| **Case record** | `agent_kit/case_record.py` | Where your agent writes down its work: its checklist, the facts it proves, any flags or evidence requests, and the final memo. It refuses any quote that isn't on the page. |
| **The agent's playbook** | `legal_agent/system_instructions.md` | How to work any case: draft a checklist, plan, investigate, file a memo. Your agent sends it as its system prompt every turn. |
| **Progress** | `agent_kit/progress.py` | Saves your agent's progress after every turn, so you can watch it in the console, and picks a stopped run back up where it left off. |

Today you build the loop, in `legal_agent/loop.py`. In Session 2, you build the checks that make the agent trustworthy, in `verification/`.

### 2.2 Read the case and the playbook

Two short files decide what your agent works on and how.

```bash
head -8 ../cases/northbridge-v-caldera/objective.md
```

**The case:** This is the task your agent will solve: one legal question about a failed software rollout, why it matters, and what a good answer looks like. The UI console shows the same text on the card called **The agent's assignment**.


```bash
head -12 legal_agent/system_instructions.md
```

**The playbook:**  This is the system prompt your agent is seeded with every turn: how to work any case (draft a checklist, plan, investigate with exact quotes, file a memo), how to use judgement, and what to do when it's stuck. It knows nothing about this particular case; just how to operate in general.

> [!TIP]
> The playbook is yours. If you'd work the case differently, edit it now, or come back to it after your first run: it's the quickest way to change how your agent behaves.

### 2.3 What an agent loop is

An agent is a model that uses tools in a loop. Each turn:

1. **The model decides.** It sees the playbook, the case, and everything that's happened so far, and picks one tool to call.
2. **Your code acts.** It runs that tool for real: reads a document, records a fact, files the memo.
3. **The result goes back.** The tool's output joins the conversation, so next turn the model works from what actually happened, not from what it guessed.

Then it goes again. The loop stops when the job is done (here, when the agent files its memo) or when it hits a turn limit, so a confused model can't spin forever.

The split matters: the model makes every choice, and your code carries it out and keeps the record. That's why the ground rules in 1.7 say never to hard-code which tool runs when.


### 2.4 Build the loop

Right now your agent has a playbook and a toolbox, and no way to use either. Time to build the loop from 2.3.

Paste these into Muse Code (your tab from 1.6) one at a time, and let each one finish before you send the next. If Muse Code asks before running a command, say yes.

**Prompt 1: plan it first.** No code yet.

```text
Read legal_agent/loop.py and the primitives in agent_kit (start with agent_kit/progress.py and agent_kit/mcp_client.py; the tools themselves live in mcp_server/). In simple language, propose a brief plan for building an agentic loop with them: what happens in one turn, and when the loop stops. No code yet.
```

Check the plan against 2.3: the model picks every tool, your code runs it and sends back the result, the run is saved every turn, and it stops when the memo is filed or the turns run out. If something's off, say so now: one sentence fixes a plan, and code takes much longer to untangle.

**Prompt 2: build the loop.**

```text
Build the agent loop in legal_agent/loop.py. In run_agent, start a run with new_run, give the model legal_agent/system_instructions.md as its instructions and the case's objective.md as its first message (settings.case_dir finds the case), and offer it the tools from mcp_client.definitions(). Each turn, ask the model what to do next, run the one tool it picks with mcp_client.run(), send the result back, and save progress. Stop when a tool result's status says the run is over, or at the turn limit; on the last turn, tell the model to file its memo. If the model call still fails after retries, save the run as paused. Then make resume_run pick a stopped run back up: resume() gives you the message to send the model.
```

You're done when Muse Code reports back and, in `agent/`, `git status` shows `legal_agent/loop.py` as the only file changed. The real test is your first run, next. Both prompts usually take 5 to 10 minutes.


**If it goes sideways:**

- Muse Code builds more than you asked for, like the checks in `verification/` (those come in Session 2): stop it, and undo them from `agent/` with `git checkout -- verification/`.
- Muse Code wants to change `agent_kit/`: tell it no. The ground rules from 1.7 already say so, but a reminder doesn't hurt.

### 2.5 Run your agent

Your loop is built. Time to let it work the whole case, and watch it think. Switch to the console tab from 1.5.

1. Tick **Step through turns**, leave **Turns** at 30, and click **▶ Start agent**. (If the button is greyed out, the console doesn't think your loop is built yet: check that `legal_agent/loop.py` no longer says "not implemented", then refresh the page.)
2. The first turn runs, then the agent waits. The bar above the timeline says **Paused before turn 2**.
3. Read the turn in the timeline. Every turn has the same three rows:

   | Row | What it shows |
   |---|---|
   | **plan** | The model's decision, and how many tokens it took. |
   | **act** | The one tool it picked, and its arguments. On a document read, **show details** lists each document and how many quotes checked out. |
   | **observe** | What came back: a fact recorded, a quote refused, the memo filed. Green went well; red was refused and goes back to the model to fix. |

4. Click the turn's header (**what the model saw ›**) for the full picture: what the model saw, what it decided, and what the tool returned.
5. Click **Next turn ▶** to run one more. Within the first couple of turns, the agent drafts its checklist, and it shows up in the **Checklist** panel on the right. Hold it up against the one you wrote down in 2.4: what did it think of that you didn't, and what did it miss?
6. After three or four turns, click **Run to end**. The rest runs on its own, usually in 5 to 10 minutes. Facts fill in under the checklist items as the agent proves them, and **Terminal output** under the timeline shows one line per turn.

You're done when the run's status says **answered** and a yellow **Memo** card appears above the timeline.

**If it goes sideways:**

- **Paused at the turn limit**: the agent used all 30 turns without filing a memo. Click **Resume with 15 more turns**. That's your `resume_run` at work: it picks up from the saved conversation, not from scratch.
- **A red row**: usually the kit doing its job. A quote that isn't on the page gets refused, and the model reads why and tries again. Worry only if the same refusal repeats turn after turn.
- **A turn takes a minute or more**: the model is busy, or the API asked it to wait. The OpenAI SDK retries on its own.
- **Paused: the Model API call failed**: the API kept failing even after those retries, so your loop saved the run and stopped. The card shows the error. Click **Resume with 15 more turns** to pick up where it left off.
- **The console shows no turns**: your loop isn't calling `save_progress` after each turn. Tell Muse Code.
- **The run stops with an error**: run `./helper run --turns 3` from `agent/` to see the error in your terminal, and paste the last lines to Muse Code.

### 2.6 Read the memo

The memo card shows the agent's conclusion, one finding per checklist item (each marked **proven**, **escalated**, or **not_proven**), and the gaps it admits to. Click a finding, and the **Checklist** panel jumps to that item and shows the facts behind it: document, page, and the exact quote.

**Would you sign off on this memo?** Pick one finding and follow it all the way down to the page that proves it.

A **Verify this run** card also appears above the timeline. Leave it for now: that's where Session 2 starts.

<details>
<summary>What to look for</summary>

The memo is filed as **unverified**, and for good reason. Every quote is real (the kit refused the ones that weren't), but real quotes can still add up to a shaky memo. In this case, look for:

- **A signature claim proven by someone saying it was signed.** Meeting minutes saying a certificate was signed aren't the signature. Nobody looked at the page.
- **Evidence from a document the agent shouldn't cite.** One document is a privileged memo from Northbridge's own lawyers. Nothing stopped the agent reading it, or quoting it.
- **A checklist nobody checked.** The agent decided what needed proving, and then proved it. If its checklist missed a question, so did the memo.

Model judgment, with no code checking it: that's what Session 2 fixes.

</details>

### 2.7 Get ready for Session 2

If your agent filed a memo, you're ready. You can close the console and Muse Code: your run is saved in `agent/workspace/`, and Session 2 starts from it (3.0).

Running behind, or your loop won't cooperate? Swap in the finished Session 1 agent so you start Session 2 level with everyone else. From the repo root (the `legal-agent-workshop` folder):

```bash
rsync -a --delete --exclude .env --exclude .venv --exclude workspace solutions/01_session1/agent/ agent/
```

It keeps your `.env`, your Python environment, and your runs, and replaces everything else in `agent/`, including any edits to the playbook. Then run `./helper run --turns 30` from `agent/` to see it work.

> [!WARNING]
> Use this only before you start building the checks in Session 2: it also resets `verification/`, so it would undo your checks. During Session 2, catch up with 3.10 instead.

> [!NOTE]
> On this branch, the snapshot is the pre-MCP agent: swapping it in replaces the MCP tool server with the original in-process tools. It behaves the same from the console, but it isn't the MCP setup anymore.

## 3. Session 2: Make the agent trustworthy

Your Session 1 agent files a memo, and nothing checks it. By the end of this session, checks the model can't skip will review its checklist and its memo, the agent will stop and ask a person for evidence when it needs it, and an attorney will sign off before the memo is final. Here's the order:

| Step | What happens |
|---|---|
| 3.0 Set up for Session 2 | Reopen the console and Muse Code, and find your Session 1 run. About 5 minutes. |
| 3.1 Why verify | Decide what you'd want checked before you sign. About 5 minutes. |
| 3.2 Where the checks sit | A short tour of the verification layer. About 5 minutes. |
| 3.3 Build the memo rules | Two prompts to Muse Code. About 5 to 10 minutes. |
| 3.4 Verify the memo | Run your check on your Session 1 memo. About 2 minutes. |
| 3.5 Is that enough? | Find the gap the memo rules can't see. |
| 3.6 Build the checklist check | One prompt to Muse Code. About 5 to 10 minutes. |
| 3.7 Verify the checklist | Run it on your Session 1 checklist. About 2 minutes. |
| 3.8 Continue with verification on | Pick up your Session 1 run from its checklist and watch the checks work. About 10 to 15 minutes. |
| 3.9 What changed | Compare the two runs. |
| 3.10 Catch up | If you need to. |

### 3.0 Set up for Session 2

Nothing from Session 1 needed to stay running: every run is saved in `agent/workspace/` as it happens, and the console reads it back when it starts.

1. **Open the console.** In a terminal tab:

   ```bash
   cd legal-agent-workshop
   python3 ui/ui.py
   ```

   Then open <http://127.0.0.1:8765>.

2. **Start Muse Code.** In another tab:

   ```bash
   cd legal-agent-workshop/agent
   muse
   ```

   Paste the ground rules from 1.7 as your first message. Muse Code doesn't remember Session 1, and doesn't need to: what you build today is specified in the files.

3. **Find your Session 1 run.** In the console's **Run** panel, pick the run with status **answered**. If it's your newest run, it's already selected. You should see its memo card and its checklist.

You're done when your Session 1 run is selected in the console and Muse Code has replied "Ready".

> [!WARNING]
> Your runs live in `agent/workspace/`, which git doesn't track. Don't re-clone or delete the `legal-agent-workshop` folder, don't reset the case with **clear runs**, and if you switch case in the console, switch back before you continue.

**No Session 1 run?** Do the catch-up in 2.7, then click **▶ Start agent** in the console (untick **Step through turns** if you don't want to step) and wait for status **answered**. That takes 5 to 10 minutes.

### 3.1 Why verify

Select your Session 1 run in the console (use the picker in the **Run** panel if it isn't already selected), and reread its memo and its checklist.

At the end of Session 1 you asked: would you sign off on this memo? Now the harder question: **what would have to be checked before you could?** Write down two answers:

1. **What could be wrong with the memo itself?** A finding with no fact behind it? A citation that doesn't match anything the agent recorded? A signature item marked proven when nobody looked at the signature? A sentence that says more than its quote?
2. **Where in the agent's work would you put the check?** After it's done, or at the moment it tries to move on?

Keep your answers: you'll compare them with what the checks find in 3.4 and 3.7.

The **Verify this run** card above the timeline runs checks on a finished run. If you click its buttons now, they say **not implemented yet**: the checks are yours to build.

### 3.2 Where the checks sit

The verification layer is a set of checks in `agent/verification/`, one file each, each with one function: `run_verification`. They aren't in your loop, and they aren't tools the agent chooses to call. They sit **inside the tools**, at the moments the agent tries to move forward:

| When the agent calls | The check | Who builds it | If it fails |
|---|---|---|---|
| `set_checklist` | **Checklist check** (`verify_checklist.py`): does the checklist cover what this case needs? | **You** (3.6) | Refused with feedback, and the agent revises. After 3 tries the checklist is accepted, and the score is kept for the attorney. |
| `submit_memo` | **Memo rules** (`verify_memo.py`): is the memo consistent with what the agent actually recorded? | **You** (3.3) | Refused with the list of problems. |
| `submit_memo` | **Claims check** (`verify_claims.py`): is each finding supported by its quotes? Runs after the memo rules pass. | Pre-built | Refused with the claims. |
| `request_evidence` | **Evidence request check**: is the item real and still unproven, and has the agent read everything it can see? | Pre-built | Refused with the reason. |
| The memo passes both | **Attorney sign-off** | Pre-built | Rejected: the attorney's notes go back to the agent. |

Why inside the tools? Imagine a separate `verify_memo` tool instead. It would run only if the model decided to call it, and a confident model skips it. Here, the agent can't file a memo without passing the memo checks, and its checklist isn't saved until it passes the checklist check or uses up its 3 tries. Until a checklist is saved, the agent can still read documents and plan, but it can't record a fact, ask for evidence, or file a memo: each of those needs a checklist item. The model can't skip the checks, and neither can a bug in your loop.

Two more things the verification layer adds:

- **The agent can ask a person for evidence.** When a checklist item can't be proven from the documents it can see, it calls `request_evidence`, and the run stops (status **needs_input**) until a person releases documents or replies.
- **A memo refused 3 times goes to a person**, instead of looping forever.

The full spec is in `agent/VERIFICATION.md`. Each check's docstring is the spec for what it receives and returns.

### 3.3 Build the memo rules

The memo rules are plain code, not a model call. They hold the memo up against the case record: every checklist item settled, every citation matching a fact the agent recorded, signature items actually checked, no evidence request left open.

If you restarted Muse Code since Session 1, paste the ground rules from 1.7 again first: they live only in the conversation.

Paste these into Muse Code one at a time.

**Prompt 1: read first.** No code yet.

```text
Do not change files. Read VERIFICATION.md and the docstrings in verification/verify_memo.py and verification/verify_checklist.py. In five bullets, say what each check receives, what it returns, and who sees the result.
```

Check the answer: each check returns `passed` plus feedback, and the agent sees only the feedback. The checklist check also returns a score, which goes to the console and the attorney, never to the agent.

**Prompt 2: build the memo rules.**

```text
Implement run_verification in verification/verify_memo.py as its docstring describes. Then run ./helper test --verification: only the MemoRulesTest tests need to pass for now. The checklist tests fail with "not implemented yet" until the next step, so don't implement verify_checklist.py.
```

You're done when Muse Code reports the `MemoRulesTest` tests passing and, in `agent/`, `git status` shows `verification/verify_memo.py` changed (plus `legal_agent/loop.py` from Session 1).

**If it goes sideways:**

- Muse Code starts on `verify_checklist.py` too: press Esc to stop it. That's 3.6. Undo from `agent/` with `git checkout -- verification/verify_checklist.py`.
- Muse Code changes `agent_kit/` or the tests: tell it no. The ground rules say so, and the tests are the spec. Undo from `agent/` with `git checkout -- agent_kit/ tests/`.
- Muse Code hard-codes something about this case, like a document ID or an item name: tell it no. Your checks have to work on any case.

> [!WARNING]
> Don't run `git checkout` on `legal_agent/`. Your Session 1 loop isn't committed, and you'd lose it.

### 3.4 Verify the memo

In the console, on your Session 1 run, click **Verify the memo** in the **Verify this run** card. It takes 10 to 30 seconds: the buttons grey out while it runs, and the result appears in the card. (Or from `agent/`: `./helper verify RUN_ID --memo`, with the run ID from the **Run** panel.)

The result lists every problem it found, in two kinds:

| Line | Where it comes from |
|---|---|
| **rule:** | Your `verify_memo.py`: problems code can find, like a missing finding, a citation with no matching fact, or a signature item nobody checked. |
| **claim:** | The pre-built claims check: one Muse Spark call that asks whether each finding's quotes support what it says. Only a model can judge that. |

Compare with what you wrote down in 3.1. What did the check catch that you expected? What didn't you expect?

<details>
<summary>What to look for</summary>

Your Session 1 run had verification off, so the agent couldn't check signatures and nothing reviewed its memo. Common catches:

- **A signature item marked proven with no signature check.** The agent never had `check_signatures` in Session 1. It took someone's word that a page was signed.
- **A finding marked proven with no fact recorded for it**, or a citation that doesn't match any recorded fact.
- **No finding for a checklist item.** The agent skipped it in the memo.
- **A claim:** a finding that says more than its quotes do.

</details>

You're done when the card shows a **Memo** result.

### 3.5 Is that enough?

Your memo rules check the memo against the checklist: every item settled, every citation backed. So ask yourself: **what can't they see?**

<details>
<summary>The gap</summary>

The checklist itself. The agent wrote its own checklist, then proved it. If an important question never made the list, every memo rule can pass and the memo still misses it. The memo is only as good as the checklist it's built on, so the checklist needs a check too, at the moment the agent sets it.

</details>

### 3.6 Build the checklist check

The checklist check compares your agent's checklist with the questions a good investigation of this case has to answer. Those questions are the **ground truth**. They live outside `agent/`, so neither your agent nor Muse Code ever sees them: the pre-built `load_reference` at the top of `verify_checklist.py` reads them for your code. Your code asks Muse Spark which of them the checklist covers, turns that into a score, and writes feedback for the agent.

**Prompt 3: build the checklist check.**

```text
Implement run_verification in verification/verify_checklist.py as its docstring describes. Leave load_reference as it is. Then run ./helper test --verification: everything should pass now.
```

You're done when Muse Code reports the tests passing and `git status` shows `verification/verify_checklist.py` changed, next to `verify_memo.py` and your Session 1 loop.

> [!IMPORTANT]
> The feedback goes to your agent as written. It must point to **what kind of question is missing**, and never quote, paraphrase, or count the ground-truth questions. If it did, your agent would just copy them down, and the check would be worthless. Nothing checks this for you: you'll judge it yourself in 3.7.

If it goes sideways, the same fixes as in 3.3 apply.

### 3.7 Verify the checklist

Back on your Session 1 run, click **Verify the checklist**. (Or from `agent/`: `./helper verify RUN_ID --checklist`.)

The card shows two things:

- **Ground-truth coverage**: how much of the ground truth your agent's checklist covers. Only you and the attorney see this number.
- **Feedback the agent would get**: exactly what your agent reads when its checklist is refused.

Read the feedback and ask: **could the agent find the missing question from this alone, without being told the answer?** If the feedback reads like the answer, tighten what your code asks Muse Spark for, and verify again. If it's too vague to act on, the agent will flounder in 3.8.

Compare the coverage with your first answer from 3.1.

You're done when the card shows a **Checklist** result next to the **Memo** one.

### 3.8 Continue with verification on

Now let your agent redo the work with the checks in place. You don't start over: the agent keeps its Session 1 conversation up to the moment it set its checklist, and carries on from there with verification on. Your Session 1 run isn't changed.

1. On your Session 1 run, click **Continue from the checklist, verification on**. Your checklist check runs on the Session 1 checklist, and the console opens a new run. Its first timeline row says **Continued from … checklist** and shows the result: usually **Checklist refused**, with the coverage and the feedback.
2. Untick **Step through turns** (unless you want to step through), then click **Resume this run** on the purple card. The agent reads the feedback and revises its checklist. In the **Checklist** panel, new items say **added after check**, and the header shows the new coverage.
3. The agent investigates again. Document text is saved from Session 1, so reads are quicker. Refusals show up as red rows, each naming the check that caught it. A memo refused by your memo rules or by the claims check goes back to the agent with the problems, and it fixes them.
4. When the agent can't prove an item from the documents it can see, it calls `request_evidence`. The run stops with status **needs_input**, and a **Handoff to the reviewer** card shows the item, the request, and what's been read.
5. Click **1 · Release follow-up evidence**. New documents land in the inbox, as if they'd just arrived from the other side.
6. Click **2 · Resume this run**. The agent reads the new documents, finishes its checklist, and files its memo, which goes through your memo rules and the claims check again.
7. When the memo passes, the run stops at **awaiting_signoff**, and an **Attorney sign-off** card appears. You're the attorney. Read the memo, click a finding, and check its quotes. Then:
   - **Approve memo**: the run ends as **done**, and the card becomes **Signed-off memo**.
   - **Reject with notes**: your notes go back to the agent, which revises the memo. It goes through the checks again and comes back for sign-off.

You're done when the run's status says **done**.

> [!NOTE]
> `check_signatures` is a stand-in for now: it reports every signature as consistent. The real check compares a signature with a page the signer genuinely signed, and anything else becomes a flag on the sign-off card.

**If it goes sideways:**

- **Continue or Verify says "not implemented yet"**: one of your checks isn't built. Go back to 3.3 or 3.6, or use 3.10.
- **Nothing moves after Resume, and the bar says "Paused before turn …"**: step mode is on. Click **Run to end**.
- **Resume ends straight away with nothing new**: the run is waiting for a person. Release the evidence (step 5) first.
- **Paused at the turn limit**: click **Resume with 15 more turns**.
- **The same refusal repeats exactly, turn after turn**: the feedback is too vague for the agent to act on. For a checklist refusal, tighten the feedback in your check.
- **The checklist check passes everything, or refuses everything**: your check is off, not the agent. Run **Verify the checklist** on your Session 1 run again and look at the coverage.
- **A handoff card asks for a reply instead of evidence**: the memo was refused 3 times. Write one line of guidance (for example, which item to list as a gap) and click **Send reply and resume**.
- **A red row you don't understand**: click the turn header (**what the model saw ›**) to see exactly what the check returned.

### 3.9 What changed

Use the picker in the **Run** panel to switch between your Session 1 run and the one you just finished:

- **The checklist**: the refused draft, the feedback, the items added after the check, and the coverage before and after.
- **The memo**: every refusal in the timeline, and the check that caught it.
- **The handoff**: where the agent stopped to ask for evidence instead of guessing, and what it did with the new documents.
- **The signed memo**, next to the unverified one from Session 1.

Now go back to the question from Session 1: **would you sign off on this memo?** This time, what are you relying on: the model, or checks that don't trust the model?

That's the idea behind the whole session. The model does the reasoning. The checks, which sit outside it at the moments that matter, decide whether the work is good enough to move on.

### 3.10 Catch up

If your checks won't cooperate, swap in the finished ones so you can still do 3.8. From the repo root (the `legal-agent-workshop` folder):

```bash
cp solutions/02_session2/agent/verification/verify_checklist.py solutions/02_session2/agent/verification/verify_memo.py agent/verification/
```

It replaces only your two checks, and leaves your loop, your `.env`, and your runs alone. Then run `./helper test --verification` from `agent/` to confirm.

No Session 1 run to start from? Do 2.7 first, then come back.
