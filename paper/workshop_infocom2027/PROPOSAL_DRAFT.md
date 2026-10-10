# INFOCOM 2027 workshop proposal (DRAFT 0.1, 2026-10-10)

Working notes for the owner sit at the bottom, below the line. Everything above the
line follows the CFP's required order (items 1 to 11). Proposal due **2026-10-28**,
one PDF, letter or A4, 10 pt minimum, to infocom2027workshop@gmail.com with subject
"Submission of INFOCOM 2027 Workshop Proposal: STALE".

---

## 1. Title

**STALE 2027: First International Workshop on Acting on Stale State in Networked
Systems**

Short name: STALE. Half day, in person, Honolulu, May 24, 2027.

## 2. Organization team

- Andrew H. Bond, San Jose State University, USA (General Chair)
- [TPC Co-Chair, second institution, ideally outside the US] TBD
- [TPC Co-Chair or Challenge Chair, ideally a cluster operator or national
  research platform staff member] TBD
- [Publicity Chair, ideally an early-career researcher] TBD

## 3. Scope and topics

Every networked controller acts on a picture of the world that was true some time
ago. A cluster admission gate reads a capacity record that was sampled by one process,
carried by a message bus, and consulted after a scheduler has already moved on. A
congestion controller reacts to signals that are one round trip old. A spectrum user
senses a channel, then transmits into whatever the channel has become. Edge
orchestrators, federated learning coordinators, and digital twins all share this
problem. The decision is made now. The evidence is from the past. The consequences
land on someone else.

STALE brings together researchers who study how old information should change what a
networked system does. We are especially interested in work that connects three kinds
of evidence that are usually published separately. The first is a model that says
what the best possible policy can achieve for a given information age. The second is
a finite-sample statement about a policy fitted from real data. The third is a
deployed system whose records let an independent reader check what actually happened.

Topics include, but are not limited to, the following.

- Age of information and value of information in control loops, admission control,
  and scheduling
- Admission and offloading decisions driven by delayed or partial capacity records
- Guest-side behavior on shared infrastructure, including opportunistic and
  volunteer clusters, research platforms, and multi-tenant GPU pools
- Limits on what feedback can achieve when observations are delayed, and when a
  static policy is as good as an adaptive one
- Budgeted and risk-constrained decisions under delayed outcome labels
- Message-bus and publish/subscribe control planes, including leaf federation,
  delivery semantics, and their effect on decision freshness
- Cloud and edge bursting, cold start, warm pools, and the cost of acting late
- Learned controllers (reinforcement learning, bandits) under stale observations, and
  tests of whether they beat simple baselines
- Opportunistic spectrum access and collision-constrained access with aged sensing
- Measurement studies of staleness in production systems, including Kubernetes,
  Slurm, and cloud control planes
- Audit, provenance, and replay of control decisions from append-only event records
- Benchmarks, traces, and simulators for stale-state control

We welcome regular papers (up to 6 pages), short papers on early results or negative
results (up to 4 pages), and demo papers (up to 3 pages plus a live demo). Negative
results are explicitly in scope. A paper showing that a feedback controller cannot
beat a static budget under realistic delay is as useful as one showing that it can.

## 4. Rationale

### 4a. Relevance to the INFOCOM community

Information freshness is a long-standing INFOCOM topic. Age of information, delayed
feedback in congestion control, opportunistic spectrum access, and scheduling under
partial observation have all appeared in the main program for more than a decade.
Most of that work stops at the model. STALE asks what happens when these models meet
real control planes, where the age of a record is itself a measured, noisy quantity
and the outcome of a decision arrives late or not at all. That connection between
networking theory and operated systems is the core of INFOCOM's identity.

### 4b. Timeliness

Three changes make the topic urgent now.

1. Shared GPU capacity is scarce and is increasingly accessed by guests who do not
   control placement. National research platforms, campus clusters, and spot markets
   all rely on users to behave well with whatever partial view of the cluster they
   have. Policies that ban or throttle users who over-request make guest-side
   decisions consequential.
2. Control planes are becoming message-driven. Systems built on NATS, Kafka, and
   similar buses decouple the process that samples state from the process that acts
   on it. That decoupling adds delay that existing models rarely account for.
3. Learned controllers are being deployed for scheduling and admission. Whether they
   provide any benefit when observations are old is an open empirical question with
   direct cost implications.

### 4c. Expected submissions

The topic sits where several active communities overlap. Age of information,
cognitive radio, and network control theory supply the models. Systems and HPC
researchers supply deployments and traces. Machine learning for systems supplies
learned controllers. Each of these groups currently publishes this kind of work as a
side result inside papers about something else. A dedicated venue with a shared
benchmark gives them a reason to write it up directly. We target 20 to 30 submissions
and 8 to 10 accepted papers for the first edition.

The short submission window (paper deadline December 29, 2026) favors early results
and short papers, which matches the workshop's purpose. The open benchmark described
below also lowers the cost of producing a credible submission.

### 4d. Attracting attendees

- **The Stale-State Challenge.** We will release, at the time of the call, an open
  replay harness and a set of capacity traces with known delays. Entrants submit an
  admission policy. The harness scores each policy on the work it gets done against a
  fixed budget for decisions made while capacity was unavailable, and checks every
  decision against the recorded event log. The leaderboard and a short talk by the top
  entries close the workshop. A challenge gives students a concrete entry point and
  gives attendees something to follow.
- **A live demo session.** Demos run against a real message-bus control plane that
  bursts Kubernetes Jobs onto a shared research cluster from a laptop in the room,
  showing record age, decisions, and outcomes on a live dashboard.
- **A panel of operators and researchers** titled "What a good guest looks like."
  Cluster operators state what they need from guest workloads, and researchers say
  what their models can and cannot promise.
- **Publicity** through the INFOCOM, MobiHoc, and SIGMETRICS mailing lists, research
  platform user communities, and NATS and Kubernetes community channels.

## 5. Tentative committees

**Organizing committee.** See Section 2.

**Technical program committee** (to be confirmed, target 15 to 20 members across
age of information, network control, cognitive radio, systems and HPC, and machine
learning for systems).

- [Name, affiliation] TBD
- [Name, affiliation] TBD
- ...

Organizers will not handle their own submissions. Any paper with an organizer as
author will be managed by a TPC member without a conflict, and organizer papers will
not exceed two.

## 6. Draft call for papers

> **STALE 2027. First International Workshop on Acting on Stale State in Networked
> Systems.** In conjunction with IEEE INFOCOM 2027, Honolulu, Hawaii, USA, May 24,
> 2027.
>
> Every networked controller decides now using information from the past. Admission
> gates read capacity records that were sampled seconds ago and carried over a message
> bus. Congestion controllers react to signals one round trip old. Spectrum users
> transmit into channels they sensed earlier. STALE invites work on how old
> information should change what a networked system does, and on how to show,
> with models, data, and auditable deployments, that it does.
>
> Topics of interest include age and value of information in control loops,
> admission and offloading from delayed capacity records, guest-side behavior on
> shared clusters, limits of feedback under delay, budgeted decisions under delayed
> outcome labels, message-bus control planes, cloud and edge bursting, learned
> controllers under stale observations, opportunistic spectrum access with aged
> sensing, measurement studies of staleness in production systems, audit and replay
> of control decisions, and benchmarks and traces for stale-state control.
>
> Negative results are welcome.
>
> **Stale-State Challenge.** An open replay harness and capacity traces are available
> at https://github.com/ahb-sjsu/stale-bench. Challenge entries are submitted as a 2-page description plus code and are
> eligible for presentation in the challenge session.
>
> **Submission formats.** Regular papers up to 6 pages, short papers up to 4 pages,
> demo papers up to 3 pages, all in IEEE two-column conference format including
> references. Reviews are double-blind. Accepted papers will be submitted for
> inclusion in IEEE Xplore. At least one author of each accepted paper must register
> and present in person.
>
> **Important dates.** Paper submission December 29, 2026. Notification February 2,
> 2027. Camera ready February 16, 2027. Workshop May 24, 2027.

## 7. Schedule

| Milestone | Date |
|---|---|
| Call for papers and challenge harness released | November 11, 2026 |
| a. Paper submission deadline | December 29, 2026 |
| b. Review deadline (proposed) | January 22, 2027 |
| c. Acceptance notification | February 2, 2027 |
| d. Camera ready | February 16, 2027 |
| e. Program ready (set by INFOCOM and IEEE) | March 4, 2027 |
| Challenge leaderboard frozen | April 30, 2027 |
| Workshop | May 24, 2027 |

## 9. Format

Half day, two sessions of 90 minutes, sized for 8 to 10 accepted papers.

- Session 1. Opening (5 min). Invited talk (30 min). Four paper talks (55 min).
- Session 2. Four to six paper talks and demos (50 min). Challenge results (15 min).
  Panel "What a good guest looks like" (25 min).

If submissions substantially exceed expectations we will ask the workshop chairs
about a full day.

## 10. Keynote and panel

Yes. One invited talk from a researcher in age of information or network control
theory [name TBD, to be confirmed before the proposal is submitted if possible], and
one panel of three to four speakers mixing research cluster operators and researchers.

## 11. Workshop history

This is the first edition.

---
---

# Owner notes (not part of the proposal)

## What I based this on

- CFP read 2026-10-10 from the INFOCOM 2027 site. Required items 1 to 11 (the CFP
  skips item 8). The CFP lists "Program ready ... March 4, 2026", which is a typo for
  2027. I used 2027 above.
- Your INFOCOM submission as compiled from the 56-Sol bundle
  (`paper/infocom2027_syed.pdf`, "Budgeted Admission from Timestamped Capacity
  Records in Shared Clusters"). The workshop theme is its three-kinds-of-evidence
  structure (population optimum, per-policy finite-sample confidence, auditable
  realized run) lifted into a call.
- The declined SC26 paper (`paper/paper_sc26_revised.tex`) supplies the demo and the
  challenge harness: the NATS leaf topology, `burst.submit`/`burst.status` subjects,
  the prober and politeness decider, the measured 7.3 s cold start and 76 ms warm
  pool.

## Things you need to decide or supply

1. **Co-organizers.** A one-person organizing team is the weakest part of this
   proposal. INFOCOM workshops nearly always list two to four chairs from different
   institutions. I did not invent names. Even one co-chair with an INFOCOM or
   MobiHoc track record would help a lot. Syed could be listed in a light role
   (publicity or TPC) if he agrees, since that is a small time cost, but only with
   his explicit yes.
2. **TPC names.** Same issue. A tentative list of 8 or more people who have said yes
   is much stronger than "TBD". Each needs to be asked first.
3. **Keynote.** A named, confirmed speaker strengthens the proposal. Optional.
4. **Double-blind exposure.** Your INFOCOM paper is under review until December 8.
   The proposal goes to the workshop chairs, not the TPC, and I kept it at topic
   level with no citation of the submission or its results. Please keep it that way
   until notification. Also, if you plan to submit your own follow-up to STALE, the
   organizer-paper rule in Section 5 covers it.
5. **Challenge traces.** I wrote that traces will be released. Before promising
   that, decide what data is safe to publish. Traces of your own jobs and of the
   controlled run-owned taint are yours. Anything that records other NRP tenants'
   pending pods is other people's activity and should be checked with NRP before
   release. A synthetic Markov trace generator plus your own controlled traces is
   the safe default. The replay harness would be new code (a few days of work built
   on `benchmarks/infocom/`).
6. **Name.** STALE is my suggestion. Alternatives: AGED (Acting on Aged Evidence in
   Decisions), FRESH (inverted framing), LATE. STALE is the most memorable.
7. **AI disclosure.** The CFP states no generative-AI policy for proposals. IEEE's
   general policy asks for disclosure of AI-generated content in articles. A
   proposal is not an article, but the text above is my draft and you should edit
   it into your own voice before sending.

## Next steps once you have reviewed

- Fill names, then I can build the PDF (pandoc or a short LaTeX file, 10 pt, letter).
- If you want the challenge, I can scope the replay harness against
  `benchmarks/infocom/`.
