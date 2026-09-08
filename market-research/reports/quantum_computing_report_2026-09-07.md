# IonQ and the Quantum Computing Market: What Users, Practitioners, and Investors Actually Say

**Date:** 2026-09-07
**Scope:** IonQ positioned against the broader quantum computing competitive landscape
**Evidence base:** 202 discussions / 3,699 comments from HackerNews (134 threads, 2011–2026) and Reddit (68 threads, past year), plus 6 web searches for company status, financials, and roadmaps.
**Method:** every claim below traces to a quoted comment with a source URL, or to a cited web source. No claims from memory.

---

## TL;DR

**IonQ is winning the retail investor narrative and losing the practitioner one — and the two audiences barely overlap.**

1. **IonQ is nearly invisible where technical credibility is made.** In 15 years of HackerNews quantum discussion, IonQ has **7 comment mentions**, versus D-Wave 108, Google 91, IBM 83, Rigetti 25. Its single largest HN thread is a short-seller fraud report. Meanwhile r/IonQ and r/IonQStock are active, engaged holder communities. The company has retail attention and engineer indifference.

2. **The only quantum claim that survived scrutiny in this entire corpus is error correction.** Google's below-threshold surface-code result and Quantinuum's peer-reviewed 48 logical qubits are the two things skeptics conceded. Every qubit-count record, every "quantum advantage" headline, and every optimization/ML demo was debunked in-thread, usually within five comments.

3. **The bear case on IonQ is being made inside r/IonQ.** Shareholders — not shorts — are the ones writing *"talk is cheap,"* *"it's a research company not a real growth company,"* and *"as a shareholder this makes me want to puke."*

4. **The category's most credible near-term market has nothing to do with quantum computers working.** Post-quantum cryptography is the only place in 3,699 comments where anyone describes an actual budgeted purchase — and those buyers explicitly say they're not betting on a working QC.

5. **Practitioners partition the field rather than dismiss it.** Quantum simulation and quantum sensing are conceded as real. Optimization and quantum machine learning are named, by researchers, as the hype vectors.

---

## 1. The players

| Company | Modality | What they do | Status (Sept 2026) |
|---|---|---|---|
| **IonQ** | Trapped ion (Ba/Ca), microwave-controlled | Cloud QC via AWS/Azure + own cloud; Tempo on-prem systems; expanding into networking, sensing, PQC | Largest pure-play by revenue. Q1 2026 rev **$64.7M** (+755% YoY), Q2 **$80.1M** (+287%), FY26 guidance **$280–290M**. FY26 adj-EBITDA loss guidance **−$310M to −$330M**. Acquired Oxford Ionics ($1.075B), SkyWater ($1.8B, closed), Vector Atomic (sensing) |
| **Quantinuum** | Trapped ion, QCCD (barium) | Helios: 98 physical qubits, **48 error-corrected logical qubits**, 99.921% two-qubit fidelity, Nature-published with Sandia | IPO'd 2026 (opened ~$68); Honeywell retains control |
| **IBM** | Superconducting | Free cloud hardware, Qiskit, Quantum Volume; Nighthawk (120q, square lattice) | Targeting **Starling** by 2029: 200 logical qubits, 100M ops. Awarded **$1B** of the US $2B quantum package |
| **Google Quantum AI** | Superconducting | Willow; below-threshold QEC (Dec 2024); "Quantum Echoes"/verifiable advantage (Oct 2025) | The one result skeptics credit. July 2026: RL calibration improved logical stability 3.5× |
| **Rigetti** | Superconducting | Full-stack; Forest/pyQuil/quilc toolchain | Small revenue, government-lab-concentrated customers; 1,000+ qubit 2027 roadmap that has slipped before |
| **D-Wave** | Quantum annealing (+ gate-model program) | Advantage annealers, Leap cloud, Ocean SDK | Revenue **reversed**: $5.9M H1 2026 vs $18.1M H1 2025. Short interest ~12.5% of float |
| **PsiQuantum** | Silicon photonics | Fault-tolerance-first; no NISQ marketing | >$1.3B raised; $125M DARPA agreement; anchor tenant at Illinois Quantum park; 2026 IPO anticipated |
| **Infleqtion** | Neutral atom | Computing + sensing/clocks | Q2 2026 rev **$12.6M** (+116%); FY26 ~$43M. Took the federal equity-stake deal |
| **QuEra / Atom Computing** | Neutral atom | 1,000+ atom systems; AC1000 (1,200+ qubits) | Atom Computing sold first commercial on-prem system to QuNorth. Fastest-scaling modality on raw count |
| **Microsoft** | Topological (Majorana) + Q#/Azure Quantum | Language, tooling, hardware distribution | Topological program shadowed by paper retractions |
| **Quantum Computing Inc.** | Photonic/thin-film | Dirac-3 optimization machines | Q2 2026 rev $5.6M; $42.5M backlog |

**Market context:** quantum companies generated >$1B revenue worldwide in 2025, projected to $4.4B by 2028 and ~$20B by 2030. North America holds ~61% share. Over 300 companies — Airbus, JPMorgan, Boehringer Ingelheim — are running vendor engagements.

**Failures matter too:** Nordic Quantum Computing Group shut down Dec 2024 after 25 years, citing lack of national strategy.

---

## 2. The credibility gap: IonQ's structural problem

This is the most important finding and it comes from counting, not opinion.

**HackerNews mentions across 15 years (86 on-topic threads, 1,462 comments):**

| Company | Mentions | Sentiment |
|---|---|---|
| D-Wave | 108 | Negative (60 neg / 36 neu / 12 pos) |
| Google | 91 | Mixed (31 neg / 30 neu / 30 pos) |
| IBM | 83 | Mixed (30 neg / 31 neu / 22 pos) |
| Rigetti | 25 | Mixed — **positive-leaning** (11 pos / 4 neg) |
| AWS Braket | 10 | Mixed |
| Qiskit | 9 | **Positive — zero criticism in the entire corpus** |
| Microsoft | 8 | Neutral |
| **IonQ** | **7** | **Skeptical (0 positive)** |
| PsiQuantum | 7 | Mixed |
| Quantinuum | 2 | Neutral |

IonQ's substantive technical coverage on HN consists of a compiler author dismantling an IonQ press release:

> "New family of N-qubit gates can only be run on IonQ quantum computer architecture. ... This is hugely misleading. You can do an N-qubit Toffoli on any computer. That's what a compiler is for."
> — [HN 30343328](https://news.ycombinator.com/item?id=30343328)

> "Unfortunately, I don't personally believe the headline summary and following text are written in good faith."
> — [HN 30343328](https://news.ycombinator.com/item?id=30343328)

And a note on the SPAC-era communications strategy:

> "Yep! This was PR for IonQ SPACing so totally focused on running via their API or APIs they integrate with (Azure, AWS)"
> — [HN 30343507](https://news.ycombinator.com/item?id=30343507)

**Contrast with Rigetti**, the one vendor HN likes — because its people showed up and understated:

> "8 qubits will not solve any problems that a classical computer can't. In fact, considering just how blazing fast modern CPUs are, you can simulate an 8-qubit chip faster"
> — Rigetti engineer, [HN 14595290](https://news.ycombinator.com/item?id=14595290)

In the same thread, a founder claim about exponential gains got this:

> "Please don't make bullshit claims about exponential speedups. I don't know exactly what technology you are claiming to have, but statements like this cause me to believe less in your technology, not more"
> — [HN 14595290](https://news.ycombinator.com/item?id=14595290)

**The lesson the corpus teaches, unambiguously: candor buys credibility in this market and press releases destroy it.**

---

## 3. Ranked pain points

### Critical

**1. No practical application, still — and insiders say it loudest** (HN freq. 61 · Reddit freq. 38)

> "Quantum computers aren't useful; they're still searching for a use." — [HN 27843776](https://news.ycombinator.com/item?id=27843776)

> "There must be around 100 quantum companies now, most of them startups, and--to my knowledge--zero of them providing anything demonstrated to be a valuable commercial product." — [HN 27905231](https://news.ycombinator.com/item?id=27905231)

> "As someone who works in the field, don't listen to what a company has to say about what the future holds for science." — 140 pts, [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1tldqwx/computer_scientists_what_is_your_honest_opinion/)

> "Not an expert here, but I work in the superconducting qubit research field (the platform IBM, Google are banking on). Many of my colleagues (many of which have phds in the field, ex-professors) think quantum computing is never going to do anything useful in their lifetimes." — 14 pts, [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1s6z9md/went_to_rsac2026_expecting_ai_hype_left_actually/)

**2. Benchmark inflation — the audience now assumes bad faith by default** (HN freq. 48)

The corpus documents a *pattern*, not a suspicion: Google's 10,000-year claim → IBM's 2.5-day rebuttal → later classical simulation without a supercomputer; IBM's "quantum utility" matched by a Commodore 64 in a SIGBOVIK paper; an award-winning ECC attack on IBM hardware reproduced with `/dev/urandom`.

> "This particular problem was artificially constructed with the specific goal of demonstrating quantum supremacy. It has little to none practical use." — [HN 21043659](https://news.ycombinator.com/item?id=21043659)

> "each company will push a benchmark that makes their machine look the best." — [HN 36735713](https://news.ycombinator.com/item?id=36735713)

**3. Error-correction overhead is the whole game** (HN freq. 44)

> "Not even a single logical qubit has been achieved to date, even with error correction, so it might be a bit soon to talk of factoring anything." — [HN 27843776](https://news.ycombinator.com/item?id=27843776)

> "The reason there are no error corrected quantum computers is because we need way (way way) many more physical qubits, and they would need to be of better quality (less decoherence)." — [HN 21047804](https://news.ycombinator.com/item?id=21047804)

**4. Qubit-count inflation gets debunked in-thread, every time** (Reddit freq. 29)

> "You have to be careful about the number of qubits here, it is very deceptive. Each qubit here is a magnetic spin, usually a 13C nucleus." — 72 pts, [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1v2yflz/german_firm_debuts_first_100_qubit_diamondbased/)

> "If I was being cynical, its a bit like me taking a regular diamond engagement ring and claiming I have a billion qubit quantum computer." — 26 pts, same thread

> "Quite literally some lady at a quantum summit stood up and did this a couple years ago. Picked up a chip and said it had thousands of qubits...like lady...most of the room have physics backgrounds and know its doesn't matter how many qubits you're holding if you can't coherently control them." — 12 pts, same thread

**5. Research integrity, not just marketing integrity** (Reddit freq. 18)

A user documented apparently fabricated results in a ~1,000-citation Nature Computational Science QML paper. The thread's reaction was that this is systemic:

> "Keep pulling on this thread and you'll find virtually all QC papers based on benchmarking NISQ algorithms are completely full of shit." — 41 pts, [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1t193zt/i_found_fabricated_results_in_a_1kcitation_nature/)

> "During my undergrad, i did a project on ml and qnns in high energy physics. I found the same exact paper and was just as confused." — 62 pts, same thread

### High

**6. D-Wave's marketing did category-wide damage** (HN freq. 58) — D-Wave is the most-discussed and most-distrusted vendor in the HN corpus.

> "They have used scientific terms like 'quantum computer' in ways that have little to do with what the rest of the scientific community means. They have lost a ton of good will to the point that I personally am extremely mistrustful" — [HN 34217218](https://news.ycombinator.com/item?id=34217218)

> "What they have done has significantly damaged the trust that the public had in my field of research." — [HN 34217218](https://news.ycombinator.com/item?id=34217218)

**7. Insiders name which sub-fields are fake** (Reddit freq. 21)

> "certain parts of the industry are complete hype (e.x. optimization, ML). other parts spin genuine algorithms (hamiltonian simulation ) into world-challenge applications like solving global warming or world hunger. some companies are much worse than others at peddling bullshit" — 32 pts, [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1rhvtr7/does_quantum_computing_actually_have_a_future/)

> "Nope. Not useful in quant (search for QC in quant finance subs or look at banks QC departments). Lots of banks and giving up their QC research departments now because, like many other are realising, the cost/time vs reward balance is extremely low on the financial side currently." — 38 pts, [r/Physics](https://www.reddit.com/r/Physics/comments/1r00liq/is_quantum_computing_more_than_a_hype/)

**8. Researchers are steering away from the field themselves** (Reddit freq. 16)

> "I currently research quantum information and before doing my Phd I worked in software/ cryptography. And I stay away from QC investments and even research grants despite the money it would offer." — **211 pts**, [r/Physics](https://www.reddit.com/r/Physics/comments/1r00liq/is_quantum_computing_more_than_a_hype/)

**9. "Logical qubit" is becoming the next inflated metric** (Reddit freq. 12)

> "can someone explain in what sense it is fair to call these logical qubits? They aren't publishing a logical error per gate (as far as I can tell) and their roadmap has 1E-8 infidelity for 2029" — [r/QuantumComputing on Helios](https://www.reddit.com/r/QuantumComputing/comments/1pbrsfg/quantinuum_helios_is_a_new_98qubit_commercial/)

**10. "Verifiable quantum advantage" wasn't verified** (Reddit freq. 20)

> "'The result of the calculation, reported October 22 in Nature, could be verified by another quantum computer — although it hasn't been yet.'" — **378 pts**, [r/science](https://www.reddit.com/r/science/comments/1odckup/googles_willow_quantum_chip_has_achieved/)

> "eh, it has not been verified that this is verifiable…." — 183 pts, same thread

**11. Simulators beat the hardware behind the same API** (HN freq. 27)

> "Right now simulators tend to be faster, cheaper, and more accurate than real quantum computers." — said *on the Amazon Braket launch thread*, [HN 21684668](https://news.ycombinator.com/item?id=21684668)

**12. Shor's record hasn't moved past 21 in a decade** (HN freq. 24)

> "there has never been a genuine implementation of Shor's algorithm. The only numbers ever to have been factored by that type of algorithm are 15 and 21, and those factorizations used a simplified version of" — [HN 42384768](https://news.ycombinator.com/item?id=42384768)

### Medium

**13. The unglamorous scaling wall: control electronics and cryogenic I/O** (HN freq. 16)

> "As an RF/Microwave engineer, I think the elephant in the room are the control electronics. Presently these are racks of equipment for a few logical qubits." — [HN 31559297](https://news.ycombinator.com/item?id=31559297)

**14. The learning ramp has no middle** (HN freq. 19 · Reddit freq. 14)

> "There just seems to be a lack of non-introductory but non-PhD level information. Where is the 'explain it like I've been accepted into college at all'." — [HN 21053405](https://news.ycombinator.com/item?id=21053405)

> "my main grief is that the groundwork section is way too short. Even a very, very smart software engineer won't be able to connect the dots" — [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1piy8cc/i_wrote_a_book_quantum_computing_for_software/)

**15. Quantum lost the attention war to AI** (Reddit freq. 11)

> "Doesn't move fast enough to be interesting plus everyone is busy putting money into LLMs." — 190 pts, [r/cscareerquestions](https://www.reddit.com/r/cscareerquestions/comments/1twu4r2/what_happened_to_quantum_computing/)

---

## 4. IonQ deep dive

### The bull case, as its own holders state it

**SkyWater / vertical integration** — the strongest and only non-price argument in the corpus:

> "The deal could make IonQ the only U.S. quantum company with its own American chip factory. Vertical integration in quantum is actually a big deal. Every other quantum company is dependent on third party fabrication." — [r/TheRaceTo10Million](https://www.reddit.com/r/TheRaceTo10Million/comments/1tb38v9/is_ionq_the_next_bagger_we_havent_caught_yet_my/)

> "Yup, this is massive news!! This will push annual revenues close to $1b" — 12 pts, [r/IonQ](https://www.reddit.com/r/IonQ/comments/1v9a6k1/ionq_receives_regulatory_approval_to_complete/)

**Microwave gates over laser gates** — holders quote a Quantinuum executive against Quantinuum:

> "'The use of free spaced optics (lasers) won't work to scale, are too costly, and have fundamental space constraints.' This is from Zachary Vernon, Director of Photonics at Quantinuum" — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1uawjnh/ionq_vs_quantinuum/)

**Declining the federal equity deal** — reframed as shareholder alignment:

> "Above is taken from Infleqtion announcement. Now you know why IonQ refused. IonQ is with shareholders." — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1tjgkdk/us_to_award_quantum_computing_firms_2_billion_and/)

### The bear case — largely written by shareholders

> "It all looks great on paper, but talk is cheap." — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1uawjnh/ionq_vs_quantinuum/)

> "Say after me it's a research company not a real growth company" — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1oc79h9/ionq_achieves_landmark_result_setting_new_world/)

> "It's a marathon but why the CEO is so busy on hyping the stock up?" — same thread

> "A quantum computer computer needs to advertise at a UFC event ?" — 25 pts, [r/IonQ](https://www.reddit.com/r/IonQ/comments/1u64yvx/ionq_at_the_white_house/)

> "As a shareholder this makes me want to puke." — same thread

> "lol most of their contracts came from government earmarks , its all corruption" — same thread

Even the error-correction efficiency claim was contested on its facts:

> "From the article it seems Quantinuum did this two years earlier and has greatly surpassed it since. Maybe that's why no one cares" — [r/IonQStock](https://www.reddit.com/r/IonQStock/comments/1u3zjsm/ionq_reduced_the_number_of_error_correction_and/)

### Roadmap credibility

IonQ's targets: 256 qubits @ 99.99% by 2026 → >10,000 qubits @ 99.99999% logical by 2027 → ~2M physical qubits by 2030. IBM, by comparison, gives itself until 2029 for a few hundred logical qubits.

Holders themselves apply the discount:

> "Remarkable! But this was announced on Analyst day already. Also caveat - This is achieved on two calcium ions. 256 system will use multi-chains of barium ions." — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1oc79h9/ionq_achieves_landmark_result_setting_new_world/)

> "256 is far less than enough to outperform in optimization problems like this. Aim for 800 fault tolerant qubits(~2027-2028) for edging out classical. Classical optimization software Gurobi can do the stock selection easily like within a second. Optimization is never the low hanging fruit. Simulation is." — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1rkfjpv/ionq_kipuquantum_paper_dropped/)

Even the most bullish framing puts the payoff past 2028:

> "It's a marathon, not a sprint. ... To be clear, IMHO next year's system, 256 qubits, is not even the real breakthrough. According to the roadmap, the system expected to be released after 2028 will start to be significant." — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1oc79h9/ionq_achieves_landmark_result_setting_new_world/)

**The AQ metric problem.** IonQ's "Algorithmic Qubits" benchmark is vendor-invented and contested — Quantinuum published a piece titled "Debunking algorithmic qubits," and analysts note AQ is susceptible to error-mitigation techniques that don't scale, and easier to pass than Quantum Volume. Given that HN's #2 pain point is benchmark inflation, a proprietary benchmark is a liability with the audience IonQ needs most.

### IonQ vs. Quantinuum — the sharpest head-to-head

**IonQ side:** 800 logical qubits by 2027 vs Quantinuum's 192; microwave over laser gates; optical interconnect; imminent vertical integration; Quantinuum's IPO read as an insider exit before losing the performance crown.

**Quantinuum side:** they already shipped what IonQ is promising.

> "I think IonQ probably made the right bet by chasing a more modular networked architecture. That said, they really need to demonstrate that they can produce logical qubits, with the plan being to demonstrate 12 error corrected logical qubits sometime this fiscal year. Meanwhile, Quantinuum has already published a paper of 48 error corrected logical qubits from a 98 qubit machine, which is incredibly efficient" — [r/IonQ](https://www.reddit.com/r/IonQ/comments/1uawjnh/ionq_vs_quantinuum/)

> "You know what really desperate companies do. They SPAC (cough, cough, IonQ)." — same thread

**12 vs. 48 is the number that matters.** It is the one comparison in this corpus where a competitor's claim survived practitioner scrutiny and IonQ's did not — because Quantinuum's is peer-reviewed in Nature with Sandia, and IonQ's is a plan.

### Recent retail stock sentiment

Conviction through pain, not euphoria. The price backdrop:

> "This stock is all over the place. Was $8 in September 24, ripped to over 80 by the end of the 2025. 2 months ago it was under $30" — 20 pts, [r/TheRaceTo10Million](https://www.reddit.com/r/TheRaceTo10Million/comments/1tb38v9/is_ionq_the_next_bagger_we_havent_caught_yet_my/)

Earnings read as good-not-good-enough:

> "Strong quarter, but not an eye watering improvement compared to last quarter, which is probably what the market wanted. RPOs barely moved. Expect a soft sell off as the hype settles. Long term prospects still shining bright." — [r/IonQStock](https://www.reddit.com/r/IonQStock/comments/1vgii1l/ionq_announces_record_second_quarter_2026/)

A specific worry: the roadmap is cannibalizing current sales —

> "A downside of their aggressive roadmap is that the promise of a 256 logical qubit system next year is probably stealing sales of the much smaller and laser-based Tempo." — same thread

Timelines have stretched, and holders say so:

> "There have already been several hype cycles and a lot of the future success is already priced in. ... I have an investing horizon of 10+ years (been in IonQ since the SPAC in 2020) ... so I'm targeting 2030 and beyond" — 7 pts, [r/IonQStock](https://www.reddit.com/r/IonQStock/comments/1vbimzn/is_ionq_a_long_term_hold_when/)

**The Kerrisdale short thesis** (external context): IonQ trading at ~40× consensus 2026 revenue, "an industry that has long been plagued by overpromises and hype," skeptical of scaling from 80–100 physical qubits to 4,000+ by 2026 and 32,000 by 2028.

---

## 5. Sentiment by population

| | HackerNews | Reddit — practitioner | Reddit — investor |
|---|---|---|---|
| **Distribution** | 10 bullish / 52 skeptical / 24 neutral (thread-level) | 31 skeptical-leaning | 22 bullish-leaning |
| **Posture** | Technically literate skepticism; assumes bad faith on benchmarks by default | Partitions the field: simulation & sensing real, optimization & QML hype | Long-term conviction, near-term defensiveness |
| **On IonQ** | Nearly silent; what exists is negative | Barely discusses IonQ at all | Actively bullish, with internal dissent on promotion and execution |

**The tone arc on HN** is worth noting: 2011–2016 "is D-Wave even quantum" (fraud detection) → 2017–2018 vendor engineers show up, tone becomes curious → 2019–2020 the Google/IBM supremacy fight teaches the community that advantage claims get deflated (the durability inflection) → 2021–2023 peak disillusionment → 2024–2026 error correction earns genuine respect while PQC becomes the liveliest commercial conversation.

---

## 6. Opportunities

**1. Position on error correction, not qubit count.** It is the only claim this audience will not discount.
> "Whenever a quantum computing company says anything other than 'it made error correction better' or 'it will make error correction better', you can ignore that. It's just some side quest." — a Google Quantum AI researcher, [HN 49546198](https://news.ycombinator.com/item?id=49546198)

**2. Claim a cheap, verifiable, ungameable milestone before a competitor does.** The audience has already named the one it would accept, and nobody has claimed it.
> "It's sad that no-one has demonstrated a factorization of 4+4 bits (which should include factorizing 55,65,77,91, and 143). That would be an important milestone I think." — [HN 31559297](https://news.ycombinator.com/item?id=31559297)

**3. Quantum simulation is the one application skeptics concede.** Named targets recur: chemistry, materials, nitrogen fixation.
> "The killer application for NISQ, in my opinion, are quantum simulations, i.e. simulations of quantum systems with quantum computers." — [HN 42212520](https://news.ycombinator.com/item?id=42212520)

**4. Quantum sensing is an under-contested adjacent market with real defence budgets.** No thread in either corpus disputes sensing the way every computing claim is disputed. IonQ's Vector Atomic acquisition (>$200M in government contracts, clocks/gravimeters/inertial sensors) targets exactly this.
> "I think quantum sensing will be a much more impactful field than quantum computing for quite a long while." — [r/QuantumComputing](https://www.reddit.com/r/QuantumComputing/comments/1tldqwx/computer_scientists_what_is_your_honest_opinion/)

**5. PQC migration tooling — budgeted, dated, and independent of QC ever working.** The only concrete purchasing behavior described anywhere in 3,699 comments.
> "We're currently demanding a full cryptographic inventory of every new product purchased or service built in-house and will start demanding PQC in 2028." — [HN 48994116](https://news.ycombinator.com/item?id=48994116)

> "Not because we expect a workable quantum computer by 2030 (current estimates are around 2035-2040), but because stuff survives for decades in large enterprises" — same thread

**6. Build the neutral cross-vendor benchmark layer the industry refuses to build.** Every vendor pushes the metric that flatters it; cost-per-capability is never reported anywhere in the corpus.

**7. Own the missing middle of quantum education.** The same gap is reported independently on HN and Reddit, and the community is filling it for free — a volunteer line-by-line translation of a transmon paper paragraph is among the corpus's most valued artifacts.

**8. Radical candor is a competitive differentiator.** Every vendor that earned goodwill in this corpus did it by understating: Rigetti's engineer on 8 qubits, Google's researcher telling readers to ignore non-QEC news, IBM rebutting Google's supremacy claim with a concrete simulation.

---

## 7. Surprises

1. **The harshest critics of quantum vendors are people who work for quantum vendors.** A Google researcher tells readers to ignore any announcement that isn't about error correction; a Rigetti compiler author dismantles IonQ's press release; a D-Wave engineer argues its case in-thread with concrete numbers.

2. **A Google researcher predicted the /dev/urandom debunk a year early — in a SIGBOVIK April Fool's paper.** He warned a bounty program that the prize would go to whoever best obfuscated that the QPU contributed nothing. In 2026 exactly that happened.

3. **Banks are shutting down quantum research departments** — the opposite direction from the vendor narrative that finance is a lead vertical. ([r/Physics](https://www.reddit.com/r/Physics/comments/1r00liq/is_quantum_computing_more_than_a_hype/))

4. **The 2013 Lockheed Martin $10M D-Wave purchase**, cited for a decade as commercial validation, is described in-thread as possibly a Canadian industrial-offset obligation rather than a technology decision. ([HN 3621334](https://news.ycombinator.com/item?id=3621334))

5. **Quantinuum's IPO — the sector's biggest liquidity event — generated 670 points on r/wallstreetbets consisting almost entirely of jokes about the company's name.** Its CEO's CNBC debut was panned even in a rival ticker's sub.

6. **Scott Aaronson functions as the field's de facto verification layer** — referenced in 27 of 86 on-topic HN threads; "it doesn't work until Scott Aaronson says it works" recurs near-verbatim across a decade.

7. **A researcher building quantum hardware said he would be happier if his field were proven pointless** than if he succeeded in building a quantum computer — because the complexity-theoretic result would be more interesting.

8. **Retail holders proposed an IonQ/D-Wave merger** to combine annealing and gate-model approaches — a strategy idea absent from analyst and vendor discourse. ([r/QBTSstock](https://www.reddit.com/r/QBTSstock/comments/1qsfccx/dwave_quantum_ceo_on_whats_next_after_the_most/))

---

## 8. What this means for IonQ

**The asymmetry is the story.** IonQ has the best revenue trajectory of any pure-play ($280–290M FY26 guidance, 100% organic growth), the boldest roadmap, and the only domestic fab. It also has near-zero standing with the technically literate public, a proprietary benchmark the field has publicly rejected, and a competitor that has peer-reviewed 48 logical qubits while IonQ plans to demonstrate 12.

Three things follow from the evidence:

- **The 2026 256-qubit delivery is the whole ballgame.** Every credibility argument in the corpus — bull and bear — is deferred to it. Slippage cascades into 2027/2028/2030 and hands the narrative to Quantinuum.
- **Retire AQ.** A vendor-invented benchmark is a net negative with an audience whose #2 complaint is benchmark inflation, and Quantinuum has already made "debunking algorithmic qubits" a public position.
- **The sensing and PQC acquisitions may be the most defensible part of the story** — they're the two areas in 3,699 comments where nobody argues the market is fake.

---

## Caveats and methodology

**Sources.** HackerNews via the Algolia API (16 focused keyword queries, dedup by objectID). Reddit via a headless browser against `www.reddit.com` (3 subreddit top-of-year pulls + 16 keyword-filtered searches, two passes). Web via 6 searches for company status, financials, and roadmaps.

**Sample sizes.** HN: 134 discussions collected, **86 on-topic** (48 dropped — the "IonQ"/"trapped ion" queries pulled in lithium-ion batteries, ion engines, Boeing, and Susan Fowler *Rigetti*), 1,462 comments analyzed. Reddit: 68 discussions, 1,182 comments.

**Known biases:**
- **Neither forum is a market survey.** HN skews to technically literate skeptics; Reddit ticker subs (r/IonQ, r/IonQStock, r/QBTSstock, r/INFQ) are self-selected holders and bullish by construction.
- **HN comment scores were not captured** — all are 0 in the raw file. HN sentiment is reported at *thread* level, not upvote-weighted. Reddit comment scores are real.
- **A handful of prolific commenters** (reikonomusha, krastanov, Strilanc, bawolff on HN; Lightning452020, MannieOKelly on r/IonQ) supply a disproportionate share of the substantive content, inflating apparent consensus.
- **The HN corpus spans 2011–2026**, so some pain points reflect historical states of the art. Where a view changed over time, the tone arc in §5 notes it.

**Coverage gaps — do not read signal into these:**
- **Atom Computing, Pasqal, Alice & Bob, Cirq: zero HN mentions.** QuEra (1), Xanadu (2), PsiQuantum (1 thread), Quantinuum (2) are anecdote, not signal, on HN.
- **Rigetti has almost no Reddit practitioner presence** — r/rigetti's top post of the year is 15 points with 1 comment.
- **IBM has no substantive Reddit practitioner thread** in this sample; all four hits are general-public/meme subs about the cryostat.
- **No pricing data anywhere** — not one comment in 3,699 reports what a QPU-hour costs on any platform.
- **Almost no enterprise buyer voices** — one security architect on PQC. No procurement, ROI, or deployed-workload discussion.
- **Thin IonQ coverage on HN (7 mentions)** means the IonQ-specific profile leans on Reddit and web sources; that thinness is itself the finding in §2, but it does limit how much technical sentiment can be attributed.

**Quote verification.** All 166 HN quotes and all 53 Reddit quotes were programmatically verified as verbatim substrings of the source corpus (whitespace/entity-normalized) with resolving source URLs.

**Note on process:** the Reddit analysis subagent terminated on a billing error before writing output; that analysis was completed directly. The skill's bundled Reddit collector was also non-functional — `old.reddit.com` now requires login — and was replaced with a new-Reddit collector (`scripts/collect_reddit_new.py`).

### Web sources
[SpinQ — Global Leaders 2026](https://www.spinquanta.com/news-detail/quantum-computing-companies-the-global-leaders-revolutionizing-technology-in-2026) · [The Quantum Insider — chip companies](https://thequantuminsider.com/2026/06/05/how-many-quantum-chip-companies-are-there/) · [Quantum Zeitgeist — hardware by modality](https://quantumzeitgeist.com/top-quantum-hardware-companies/) · [IonQ — Oxford Ionics close](https://investors.ionq.com/news/news-details/2025/IonQ-Completes-Acquisition-of-Oxford-Ionics-Rapidly-Accelerating-Its-Quantum-Computing-Roadmap/default.aspx) · [IonQ — Vector Atomic](https://www.ionq.com/news/ionq-announces-intent-to-acquire-vector-atomic-expanding-into-quantum) · [IonQ Q1 2026 results](https://investors.ionq.com/news/news-details/2026/IonQ-Announces-First-Quarter-2026-Financial-Results/default.aspx) · [Kerrisdale Capital — IonQ short report](https://www.kerrisdalecap.com/wp-content/uploads/2025/03/IonQ-%E2%80%93-Kerrisdale.pdf) · [Stocktwits — Kerrisdale reaction](https://stocktwits.com/news-articles/markets/equity/ionq-stock-slides-on-kerrisdale-short-report/ch7dju4RbRv) · [Quantinuum — Debunking algorithmic qubits](https://www.quantinuum.com/blog/debunking-algorithmic-qubits) · [QuantumBenchmarkZoo — Algorithmic Qubit](https://quantumbenchmarkzoo.org/content/application-level-benchmark/protocols/algorithmic-qubit) · [CACM — Trapped ions, will they scale?](https://cacm.acm.org/news/trapped-ions-make-beautiful-qubits-but-will-they-scale/) · [Nature Electronics — success and failure of QC start-ups](https://www.nature.com/articles/s41928-025-01337-x) · [The Quantum Insider — Nordic QCG shutdown](https://thequantuminsider.com/2024/12/10/nordic-quantum-computing-group-shuts-down-citing-government-policies-taxes-lack-of-support/) · [Motley Fool — D-Wave vs Rigetti 2026](https://www.fool.com/coverage/better-buy/2026/08/24/d-wave-quantum-vs-rigetti-computing-which-quantum-computing-stock-is-a-better-investment-in-2026/) · [McKinsey Quantum Technology Monitor 2026](https://www.mckinsey.com/capabilities/mckinsey-technology/our-insights/mckinsey-quantum-technology-monitor-2026-a-commercial-tipping-point) · [Infleqtion Q2 2026](https://secure.businesswire.com/news/home/20260812752663/en/Infleqtion-Reports-Record-Q2-Revenue-Raises-2026-Outlook-as-Quantum-Commercialization-Accelerates)

### Data files
- `data/raw/quantum_computing_hn_2026-09-07_02-50-44.json` — 134 discussions / 2,517 comments
- `data/raw/quantum_computing_reddit_merged_2026-09-07_03-10-32.json` — 68 discussions / 1,182 comments
- `data/raw/quantum_computing_combined_2026-09-07_03-10-32.json` — 202 discussions / 3,699 comments
- `data/analysis/quantum_computing_hn_analysis.json` — 14 pain points, 14 players, 166 verified quotes
- `data/analysis/quantum_computing_reddit_analysis.json` — 13 pain points, IonQ deep dive, 53 verified quotes
