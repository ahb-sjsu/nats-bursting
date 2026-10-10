# Stale-State Challenge: harness scope (DRAFT 0.1, 2026-10-10)

The proposal promises "an open replay harness and capacity traces" at the call for
papers (November 11, 2026, a week after the November 4 acceptance notification). This
file scopes what that means, what already exists, and what has to be built.

## 1. The task, in one paragraph

At each decision epoch an entrant's policy receives one delay-tagged capacity record
(the sampled state of one schedulability unit, its age, and source, receive, and
decision timestamps) plus whatever outcome labels have arrived so far. It returns an
admission decision (offer one Job or not, possibly randomized). An offer made while
the unit is available counts as useful work. An offer made while it is unavailable
consumes a budget. The policy must keep that consumption under a stated budget and
should get as much useful work as possible. This is the decision problem of the
INFOCOM submission, stated with its definitions (joint probabilities over action and
current state, binary unit, exogenous state).

## 2. Why replay is valid, and its limit

The capacity state is exogenous in the model. The guest's action does not change it.
So one recorded state sequence can be replayed against any policy, and every entrant
sees the same world. This is the property that makes a cheap, fair leaderboard
possible. The rules must say plainly that the challenge does not cover settings where
the guest's own load changes cluster state. That is a known limit, and a good topic for
papers rather than for the leaderboard.

## 3. Entrant interface

A single Python file, NumPy only, defining one class.

```python
class Policy:
    def __init__(self, budget: float, meta: dict): ...
    def act(self, record: Record, labels: list[Label]) -> float:
        """Return the probability of offering one Job this epoch."""

# Record: unit_id, sampled_state (0/1), age_epochs, t_source, t_receive, t_decide
# Label:  epoch of an earlier offer, realized state at that offer (arrives L epochs late)
```

The harness, not the policy, draws the randomized action, so randomization is
auditable from the seed. The policy runs in a separate process and sees records one at
a time, so it cannot read the future of the trace.

## 4. Trace sets

| Set | Source | Public? | Status |
|---|---|---|---|
| S1 symmetric Markov | generator, flip prob p and age D swept | yes, generator + seeds | `markov_capacity` in `benchmarks/infocom/tau_sweep.py` already does this |
| S2 harder synthetic | asymmetric two-state, semi-Markov (heavy-tailed holding times), regime switching | yes | new, small. No closed-form optimum, so this is the open part of the challenge |
| S3 controlled Atlas runs | E8/E9 per-epoch `samples` (t, a, c, ...) from owned GPUs with self-generated competitors | yes, after a check | 68 files in `benchmarks/infocom/e9_results/` plus `out/`. Short (about 76 epochs each), so useful as realism checks, not for scoring alone |
| S4 shared-cluster traces | NRP, own jobs and run-owned taint only | only after asking NRP | not collected. Anything recording other tenants' pods stays private |
| Hidden test | fresh seeds of S1 and S2, plus held-out S3 segments | no | generated at freeze |

## 5. Scoring

- **Budget check.** For each test trace, the harness counts unavailable-state offers.
  A policy passes if a one-sided exact binomial bound on its violation rate, pooled
  over the hidden test runs, stays at or under the budget. This mirrors the
  submission's calibration step and keeps the rule simple to state.
- **Score.** Useful offers per epoch, reported relative to the best static
  (record-ignoring) policy at the same budget. On S1 the closed-form frontier gives the
  best possible value, so the leaderboard can show each entry as a fraction of the
  optimum. On S2 there is no known optimum and entries are ranked against each other.
- **Optional strict track.** Policies must also respect the budget at every prefix of
  every run, treating unresolved offers as violations until their label arrives. The
  harness checks this deterministically. This mirrors the submission's prefix guard and
  rewards careful accounting rather than luck.

## 6. Audit log

Every run writes an append-only JSONL log with one event per sample, delivery,
decision (with the random draw), and label. A separate auditor script recomputes every
score from the log alone. The leaderboard publishes the logs. Entrants and reviewers
can rerun the auditor and get the same numbers.

## 7. Baselines shipped on day one

All already exist as controllers in `tau_sweep.py` and need porting to the binary
unit and joint-budget definitions.

- static budget (ignores the record)
- delayed threshold (Bayes-optimal on S1)
- AIMD
- regime-adaptive (estimates correlation online and switches)
- REINFORCE policy over the last few records

A starting result for the call: on S1, learned controllers reach but do not beat the
threshold policy. Inviting entrants to break that on S2 is the hook.

## 8. Infrastructure

- New public repo, `stale-bench`, MIT code and CC BY data per the license convention.
  Installable with pip.
- Leaderboard via GitHub Actions. An entrant opens a pull request with one file, CI
  runs the public sets, and the organizers run the hidden set at freeze (April 30,
  2027). Scoring is a few CPU-minutes per entry, so it does not need Atlas or NRP.
- Live demo (separate from scoring): the top entries run through the real nats-bursting
  path (`burst.submit`, prober, decider) against a run-owned taint on a cluster the
  organizers control, shown at the workshop. This needs a policy plug-in point in the
  Go decider (`internal/decider`), which today has only the fixed rule.

## 9. Effort estimate

| Piece | Estimate |
|---|---|
| Core harness: record and label stream, separate-process policy runner, seeded draws | 1 day |
| S1 and S2 generators, closed-form S1 frontier | 0.5 day |
| Port five baselines to the challenge definitions, with parity tests against `tau_sweep.py` | 1 day |
| Audit log and independent auditor | 0.5 day |
| S3 conversion from E8/E9 JSON | 0.5 day |
| CI leaderboard, entry template, README and rules | 1 day |
| **Minimum release for November 11** | **about 4.5 days** |
| Go decider plug-in and live demo path | 2 to 3 days, any time before May |

These are my guesses, not measurements.

## 10. Decisions for you

1. **Double-blind timing.** A public repo released November 11 that reproduces the
   submission's model, frontier, and baselines lets a curious reviewer link the
   submission to you before the December 8 notification. Options: (a) release
   November 11 without the S1 closed-form frontier and without any citation, adding
   them after December 8; (b) release under a neutral workshop GitHub organization; or
   (c) release the full harness on December 9 and tell entrants in the call that it
   is coming. I lean to (a) combined with (b). This is your call. INFOCOM's
   double-blind rules are the authority, and I have not read their exact wording on
   related public artifacts.
2. **Where is the submission's implementation?** The final submitted paper describes
   an event contract, binomial calibration, a prefix guard, and an auditor run on a
   controlled NATS and Kubernetes path. I could not find that code in `nats-bursting`
   or `network-as-a-program`. If it exists, the harness should reuse it so the
   definitions match exactly.
3. **Definitions.** `tau_sweep.py` uses window sizes and over-admission. The
   submission uses one binary unit and a joint-probability budget. I propose the
   submission's definitions for the challenge, with windows as an S2 extension.
4. **Strict track.** Include it or keep a single track. One track is easier to
   explain, and the strict track is the more interesting one technically.
5. **Build now or after November 4.** Building before the proposal goes in would let
   the proposal point to a real URL, at the cost of about 4.5 days that are wasted if
   the workshop is not accepted.

## 11. Status, 2026-10-10

Pushed 2026-10-10 to https://github.com/ahb-sjsu/stale-bench (public, commit
414763c, CI green), local clone `C:\source\stale-bench`. The owner dropped option (b)
after INFOCOM's preprint policy turned out to allow public related work, so only
option (a) applies. Single repo with both tracks.

- Harness, 13 public scenarios (S1 6, S2 4, S3 3), 6 baselines, auditor, CLI,
  CI workflow, example entry. 19 tests pass on Atlas (`~/venvs/stale`).
- S3 holds 62 public controlled-run traces; 31 are held back under
  `embargo/private_data/` (gitignored), along with `HIDDEN_KEY.txt` and the
  S1 frontier (`embargo/frontier.py`, publish after December 8).
- Public results and one hidden-set dry run are in the stale-bench README and
  were measured on Atlas.
- The pull-request scoring job in CI has not run yet (it only runs on PRs).
