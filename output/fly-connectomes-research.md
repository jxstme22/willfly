# Fly Connectomes and Crypto Liquidity Provision

> **Scope update — 13 September 2026:** This is the original literature review. The project now prioritizes Robinhood Chain new launches, memecoins and spot-trading decisions, with selective LP as a separate action. Its LP-first recommendations below are historical. See [current direction](../docs/project-direction.md), [experiment plan](../docs/experiment-plan.md) and [build roadmap](../docs/build-roadmap.md) for the active scope. The updated PDF places the active plan first and preserves this review as a historical appendix.

**A feasible experiment, with an unproven financial advantage.** The useful opportunity is to test whether connectivity measured from a fly nervous system improves a small, stateful controller for DEX liquidity decisions. The reviewed evidence does not establish profitable fly-brain liquidity provision, a complete digital animal, or a conscious uploaded mind.

FlyWire Codex is an explorer of reconstructed nervous-system data. It is one part of a stack: anatomical data, simulation equations, a learning rule, an input/output interface and an environment. Those parts must be chosen and validated separately. Public source code for Codex is available; the website itself is not a running brain.[1,6]

The recommendation

Use the **FAFB/FlyWire dataset with the original Shiu implementation** as the scientific reference for reproducing published sensorimotor results. For an LP prototype intended to leave room for commercial use, prefer **MaleCNS v1.0 as the initial data candidate**, because its official release uses CC BY rather than the FAFB public release's noncommercial license. Porting between these datasets requires fresh validation.[2,3,8]

The first experiment should ask one narrow question: **does a fly-derived recurrent network help choose liquidity ranges after realistic costs, beyond what the same inputs and ordinary models can do?** Start with historical replay and a fixed recurrent network plus a small trained output layer. Add online plasticity only after there is a measurable reason to do so. This is a proposed research design, not a result.

Can we download and use real fly wiring? | Yes, subject to the particular data license and release.

Can it support learning and control? | Yes, with explicitly engineered dynamics, training and interfaces.

Does that make it a real biological brain? | It makes a computational model using biological measurements.

Can it outperform ordinary LP strategies? | Unknown. The decisive market experiment has not been established by the reviewed evidence.

**Scope.** Literature and public resources were checked through 13 September 2026. This is a targeted deep review of foundational connectomics, simulation, vision, learning, embodiment, reservoir computing and LP economics. It does not claim to read every FlyWire-related paper. The bibliography distinguishes methods reviewed, abstract screening, inaccessible full text and unvalidated project disclosures. No simulations or financial backtests were run for this report.

# 1. The correct data and software

FAFB v783 | Adult female brain; 139,255 reconstructed neurons.[1,10] | Published brain-model reference; FAFB data are CC BY-NC 4.0.[2]

MaleCNS v1.0 | Male brain plus ventral nerve cord; 166,700 neurons, 11,710 types.[4] | Preferred data candidate for an extensible LP prototype; CC BY 4.0.[3,39]

BANC v888 | Female brain plus nerve cord; 158,262 neurons shown in Codex.[1] | Useful later for distributed sensorimotor-control comparisons.[23]

MANC / MAOL | Nerve cord only / right optic lobe only.[1] | Useful specialized datasets; neither is an entire brain.

The original female brain is the appropriate answer when someone means the widely reported 2024 FlyWire brain. The newer complete central-nervous-system releases broaden the choices. The MaleCNS site records a 2026 release and links its Cell paper; its publisher full text was not accessible during this review, so current dataset facts here come from the official release documentation.[24]

Codex applies dataset-specific thresholds to weak connections. Displayed graph edges are not individual synapse counts or an unfiltered connectivity inventory.[40]

What we actually need to download

For FAFB v783, the official Zenodo release offers an approximately 852 MB connection table and a 1.1 MB proofread-ID list. The 9.5 GB synapse table includes a broader population of segments and approximately 130 million contacts; that is not the same population as the roughly 50 million proofread-brain contacts commonly reported. A graph experiment generally does not need the underlying electron-microscopy image volume.[5,10]

MaleCNS offers a 1.1 GB connection-weight table, 13 MB curated annotations and 42 MB transmitter predictions. The graph includes segments outside the curated neuronal set; filtering and ID joins are essential. Its bulk-download route avoids dependence on an interactive account, while the documented neuPrint API requires a token.[3]

Choose code independently from data

**Codex:** Apache-2.0 explorer code. **Shiu model:** MIT simulation code, with Brian2 and separate v630/v783 configurations; the default v630 path reproduces the paper. **Eon fly-brain:** accelerated simulation implementations, chiefly GPL-2.0-or-later with an upstream MIT exception, and Linux/NVIDIA-oriented GPU paths. Code licensing does not replace data licensing.[6,8,9]

Recommendation: preserve an untouched paper-reference environment and create a separately named LP model. Keep a release manifest containing data URLs, hashes, licenses, filtering rules and software commits. An LP model using MaleCNS must not be presented as an exact reproduction of a FAFB experiment.

# 2. What “a real brain” would mean

A connectome records reconstructed anatomical connectivity from a biological specimen. It does not record a complete functioning state: moment-to-moment electrical activity, all effective synaptic strengths, receptor distributions, internal chemical state and learned dynamics are not supplied as a ready-to-resume nervous system. Whole-brain annotation also reveals both shared organization and differences between animals.[10,11]

Biological origin | The connectivity was measured from actual fly tissue.

Biological tissue | A computer simulation contains mathematical state, not living cells.

Biological function | Specific responses can be tested against experiments. A correct response on one task does not validate all internal mechanisms.

Learning and autonomy | Possible engineered properties, requiring defined learning rules and an environment.

Conscious experience | Not demonstrated by neuron count, spiking, animal-like motion or trading performance.

Calling the system a “connectome-derived neural controller” is accurate. Calling it a complete uploaded fly would require evidence that substantially exceeds the studies reviewed here. This distinction does not make the experiment less useful: biological connectivity might be a valuable constraint even if its engineered dynamics differ from the original animal.

How this differs from an LLM

Our proposed controller would receive numerical observations, maintain a recurrent state and output a few constrained actions. It would have no pretrained language interface or stock of textual knowledge. We could test it without an LLM anywhere in the decision loop. Its learning would still be computational learning; biological inspiration does not place it outside artificial intelligence.

Consciousness and living-neuron alternatives

Butlin and colleagues propose assessing artificial systems using properties motivated by competing scientific theories of consciousness. That is a framework for investigation, not evidence that a FlyWire simulation has experience. The appropriate conclusion is **undetermined and unvalidated**, rather than certainty in either direction.[25]

DishBrain is a different category: Kagan and colleagues coupled living cultured neurons to a simplified game environment. It is a wet-laboratory system with specialized interfaces, not a downloadable fly brain. The paper's use of “sentience” should not be treated as a settled demonstration of subjective experience. It supplies no evidence of DEX liquidity skill.[26]

For this project, biological fidelity and financial usefulness should be evaluated on separate axes. A financially successful simplified reservoir would establish useful computation, not consciousness. A biologically informative simulation could be financially useless.

# 3. What the strongest neuroscience establishes

An anatomical map is powerful, but it is not a functional specification

The Dorkenwald reconstruction provides the foundational whole-adult-brain wiring resource. Schlegel and colleagues add extensive cell typing and comparisons between connectomes. The visual-system parts-list work organizes specialized visual circuitry. Together these provide experimentally grounded structure for selecting neurons, pathways and hypotheses; they do not assign those circuits a meaning such as “ETH price” or “profitable range.”[10,11,38]

Whole-brain spiking: Shiu et al., 2024

The Shiu model uses simplified leaky integrate-and-fire neurons to study selected sensorimotor pathways, including feeding-related inputs and grooming. The paper reports agreement for 91% of 164 empirically tested predictions. That denominator is a selected experimental set, not all fly behavior and certainly not financial decisions.[7]

Its limitations matter directly to adaptation: simplified cell dynamics and synaptic scaling, omitted physiological detail, uncertain neurotransmitter effects and a zero-activity baseline that can limit inhibitory effects. The published implementation does not supply a general plasticity mechanism. Reproducing its results is therefore a useful sanity check, not proof that a new learning controller is biologically faithful.[7,8]

Vision: Lappalainen et al., 2024

This study combines visual-connectome constraints with task optimization to predict neuronal responses. Its model uses a specialized, tiled visual network of 64 cell types, with 45,669 model neurons and relatively few shared neural parameters. It is neither a generic visual language model nor a full FAFB brain wired directly to a camera. The released flyvis implementation is a relevant starting point for visual experiments.[13,37]

A candlestick chart is a human encoding convention. Giving its pixels to simulated visual cells would introduce an additional learning problem and sensitivity to colors, scales and chart layout. For the first LP test, numerical features provide a more interpretable interface. A later chart experiment should randomize visual styling while preserving the underlying market series.

Chemical labels and effective influence remain uncertain

Eckstein and colleagues predict transmitter identity from electron-microscopy images; the reported accuracy differs at synapse, neuron and cell-type levels. These are predictions, not complete receptor-dependent synaptic effects.[12] Pospisil and colleagues distinguish anatomical connectivity from causal effective influence and propose experimental methods to infer the latter.[14]

Engineering implication: neurotransmitter-to-sign mappings, weight transformations and background activity must be explicit model assumptions. Test their sensitivity. Papers in this area do not all use the same sign or weight conventions, so mixing implementations can silently change the scientific hypothesis.

# 4. Memory, learning and useful computation

The closest evidence to a market application is reservoir computing

A reservoir is a recurrent dynamical system whose changing activity summarizes recent inputs. A small trained readout converts that activity into predictions or actions. Keeping recurrent weights fixed makes the first experiment easier to interpret: any advantage can be investigated without simultaneously changing the entire graph.

Costi and colleagues tested fly-connectome-derived echo-state networks on orbital time series from a restricted three-body problem. They examined smaller subsets and a filtered full network. Some settings showed resistance to overfitting, but a random reservoir performed better under stronger regularization; weight distributions appeared more influential than topology in important comparisons. This is evidence for a testable computational prior, not market forecasting or universal superiority.[16]

Earlier Morra-Daley studies also investigate connectome-constrained echo-state networks and report conditional results across synthetic dynamical tasks.[17,18] A 2026 optimization preprint uses a Drosophila representation with only 49 nodes. Its title should not be read as evidence about a full adult fly brain or financial performance.[36]

Three different kinds of memory

Recurrent state | Activity while weights stay fixed | How long past observations remain recoverable; benefit over a state-reset control.

Readout learning | Parameters that map activity to actions | Held-out prediction or net LP performance after a fixed training period.

Synaptic plasticity | Connections or their effective strengths | Improvement from feedback, retention, interference and adaptation after regime changes.

Learning-circuit research in the larval mushroom body shows recurrent organization around dopamine-related teaching pathways. That gives biological motivation for studying structured feedback; it does not establish that an adult whole-brain simulator learns automatically when a “dopamine” input is stimulated.[15]

Why profit-as-reward is not enough

A learning rule must specify which connections change, their eligibility traces, the delayed feedback signal, learning rates and stability constraints. LP rewards are delayed and confounded by price exposure and unrelated market moves. A positive portfolio return can occur despite a poor liquidity decision. Directly labeling gains “sugar” and losses “bitter” supplies a stimulus mapping, not causal credit assignment.

Recommendation: begin with a frozen recurrent network and supervised readout. If it adds measurable value, test reward-modulated plasticity as a separate intervention, against frozen-learning and shuffled-reward controls. A learned market task would then be an engineered capability that we can measure, rather than an assumed property of the source animal.

# 5. Embodiment: what moving flies demonstrate

A convincing animated animal can combine several systems: a physics model, trained motor policies, sensory preprocessing and some connectome-derived activity. We need to identify which component controls each behavior before attributing the result to the reconstructed nervous system.

Peer-reviewed body platforms

NeuroMechFly v2 provides a body-and-environment framework with vision, olfaction, motor feedback and challenging terrain. Its demonstrations include designed and reinforcement-learned controllers. It is useful for testing closed-loop hypotheses, but a body platform alone does not provide a complete brain model.[19]

The flybody work produces realistic walking and flight using whole-body physics and trained neural controllers. Its use of learned control is a concrete reason that natural-looking movement cannot by itself identify the biological mechanism generating it.[20]

Whole-connectome control models and company demonstrations

FlyGM, a 2026 preprint, places trainable neural components around a connectomic graph and uses expert imitation followed by reinforcement learning for locomotion. Its comparisons do not cleanly isolate topology alone: biological weighted/signed connections and some unweighted control graphs differ in more than wiring. The result is an interesting trained architecture, not evidence that an untouched connectome already contains a working digital animal.[21]

Eon's March 2026 technical disclosure describes a hybrid system using existing brain, vision and body components with selected interfaces and motor controllers. It acknowledges substantial missing learning and internal-state mechanisms, limited behavioral influence of the implemented visual pathway, and important unvalidated neural dynamics. This disclosure is more informative than treating a “brain upload” headline as an established scientific conclusion.[22]

What the newer brain-and-cord data change

The BANC study maps distributed control circuitry across brain and nerve cord. That improves the anatomical basis for studying interactions between descending commands, ascending feedback and local motor circuits. It does not automatically solve the dynamics of those interactions.[23] MaleCNS similarly supplies a complete central-nervous-system data resource for new modeling work.[24]

For an LP agent, a simulated fly body is optional. Its environment can be a pool state and portfolio; its actions can be bounded liquidity adjustments. This would be computational embodiment in a financial task, not a faithful reproduction of fly locomotion. A 3D fly visualization may help explain activity, but should never serve as evidence that the policy learned anything.

The most valuable later body experiment would ask whether a specific connectome-based control hypothesis reproduces both behavior and relevant neuronal activity under perturbation. Financial tests should instead evaluate decision quality and accounting. Keeping those targets separate prevents a visual demonstration from standing in for either form of validation.

# 6. What a DEX liquidity controller could do

The smart contract already performs automated market making. Our experimental controller would decide how to allocate a portfolio around it: whether to supply liquidity, where to place a range, how wide it should be, how much to deploy and when to adjust. It would not need to understand a protocol in language to select these actions.

Uniswap v3 permits bounded liquidity ranges. Fees accrue while a position participates in active liquidity; outside its interval it becomes one-sided and stops earning swap fees until price returns. Narrow ranges concentrate exposure as well as fee participation. Fee allocation depends on active liquidity along the swap path, not simply the pool's total value locked.[27]

The scientific opportunity

A recurrent controller might recognize changing volatility, persistent flow or a rising probability of leaving a range. These are hypotheses. Its useful role could be selecting a conservative range or avoiding an unfavorable interval, rather than forecasting the next token price. A transparent numeric interface also lets us determine which observations matter.

Range width | Trailing volatility, recent range exits, liquidity concentration and estimated adjustment cost.

Recenter or wait | Distance to range boundaries, current inventory, expected fee opportunity and transaction delay.

Deploy or remain idle | Available capital, recent external/pool price divergence, flow conditions and risk limits.

Fees are not the same as investment skill

The LVR literature separates market exposure from the economics of supplying liquidity against better-informed arbitrage. Loss-versus-rebalancing compares with a dynamic benchmark; loss-versus-holding compares with retaining initial assets. These are different counterfactuals. Neither is a generic extra invoice to subtract twice from an already complete portfolio ledger.[28]

Fritsch and Canidio find historical pools where estimated arbitrage losses exceeded fee earnings. That is evidence that high activity can coexist with unattractive liquidity economics, not a statement that every present-day pool loses money.[29]

Online-learning LP research offers a useful simpler benchmark, although the Bar-On-Mansour formulation adopts simplifying assumptions such as omitted gas costs.[30] The Zhang-Chen-Yang reinforcement-learning study reports simulated LP improvements and includes a hedging formulation, but assumes flat adjustment gas, frictionless hedging, no adjustment slippage and no impact on other traders. Its results are not live profitability evidence.[31]

Recommendation: use one historical WETH/USDC Uniswap v3 pool as a research case after data-quality checks. Keep futures hedging out of the first experiment so that the contribution from liquidity decisions is easier to identify. This is a proposed benchmark environment, not a recommendation to deposit funds.

# 7. Existing “fly traders” and our proposed design

Public prior art exists, but it does not settle the question

Stonkfly connects a MaleCNS-derived simulation to a spot-trading environment. Its documentation describes chart-based input, a fixed trading readout and candidate reward-driven plasticity. The authors explicitly state that profitable learning has not been demonstrated. This is relevant implementation prior art, not a verified DEX LP result.[32,33]

Traderfly-brain describes market features converted through predetermined thresholds into sensory stimuli, with biological outputs mapped to trading decisions. It restarts activity for decisions and keeps parts of the surrounding strategy private. Its repository states all rights reserved, so public visibility should not be confused with an open-source license. It is not evidence of a learned, persistent LP controller.[34]

The research gap is therefore specific: establish whether connectivity itself adds reproducible, cost-adjusted value after controlling for the engineered features, readout and surrounding strategy. A profitable wrapper could conceal a neural component that contributes little or nothing.

Proposed architecture

1. Market observations | Only timestamped numeric data available before the action: price changes, flow, volatility, active liquidity and costs.

2. Fixed input encoder | A documented mapping from standardized observations to model inputs. No hand-coded buy/sell or narrow/wide recommendation hidden inside it.

3. Recurrent network | Sparse fly-derived graph with explicitly chosen dynamics. Preserve state across observations within an episode.

4. Small trained readout | Predict range-exit probabilities or select among a few permitted liquidity actions.

5. Deterministic controls | Enforce maximum allocation, minimum holding time, transaction budgets and allowed ticks.

6. Historical pool replay | Account for balances, fees, transactions and delayed execution; return observations and evaluable outcomes.

Initially fix the range center at the observed pool price when entering, use a constant deployment fraction, and let the model choose only width or remaining idle. This isolates a manageable question. Add range-center shifts, variable capital and continuous actions only if the restricted policy demonstrates value.

The first task can predict whether price leaves each candidate range over a fixed future horizon. Every model then uses the same deterministic range-selection rule. This separates a representation benefit from a complicated policy-training benefit. Direct reward optimization is a later experiment, not a prerequisite for learning something useful.

# 8. A test that can produce a credible answer

Pre-register two hypotheses

**H1: useful temporal representation.** With identical observations and training budgets, a fly-derived reservoir predicts range exits or volatility better on unseen market periods than a readout without the reservoir. **H2: useful liquidity decisions.** Those improvements translate into better net portfolio outcomes than strong simple LP strategies, at comparable exposure and drawdown. H1 can succeed while H2 fails.

Hold initial assets; cash reference | Whether apparent gains mainly follow asset prices or a change in exposure.

Fixed wide-range LP | Whether adaptation adds anything beyond passive liquidity.

Volatility-based range rule; online learner | Whether a straightforward adaptive strategy is already sufficient.

Readout on the same raw features | Whether engineered observations explain the result without recurrence.

Ordinary random reservoir | Whether recurrence helps but biological structure is unnecessary.

Degree/sign/weight-controlled shuffled graph | Whether biological topology helps after other graph properties are controlled.

Conventional small recurrent model | Whether a standard trained model uses the available data and compute more effectively.

Chronological evaluation

Use rolling training and validation windows followed by untouched test windows. Freeze normalization, feature choices, hyperparameters and action definitions before each test. Separate windows by the prediction horizon where overlapping labels would leak information. Preserve a final holdout that is not inspected while deciding the model. Report every pre-specified market period, including adverse ones.

Repeat initialization and input-mapping seeds. These measure training sensitivity, not independent financial histories. Estimate uncertainty across suitable time blocks or market episodes, and compare strategies on the same periods. Match both tuning opportunities and practical computation; matching neuron counts alone is not a fair comparison.

Interventions that expose a decorative brain

Reset recurrent state, shuffle input-channel assignments, freeze learning, shuffle rewards, and perturb graph organization while matching key degree, sign and weight statistics. Where feasible, also match stability scaling. If performance survives removal of the neural component, attribute it to the surviving system rather than to biological wiring. For a plasticity claim, verify actual parameter changes and retention on a later test.

A promising result should improve the pre-specified primary metric against both a strong simple LP baseline and a matched nonbiological network, remain useful across multiple unseen periods, and survive realistic cost stress. If the uncertainty interval remains wide or the advantage disappears with modest costs, the answer is inconclusive or negative. Do not keep changing the metric until a positive result appears.

# 9. The accounting is part of the experiment

Use an event-based replay where practical: swaps, liquidity additions/removals, ticks, active liquidity and fee growth, together with block timestamps and an external reference price. Candles can support an initial prediction task, but do not contain enough information for precise path-dependent fee attribution. The replay should be validated on simple positions before any neural policy is evaluated.[27]

Maintain one complete portfolio ledger

Define equity as the marked value of every token balance, active position, idle holding and uncollected fee. Account for gas, swap fees, slippage and execution delay when they occur. Record rejected or failed actions. Withdrawing a position leaves its underlying token inventory; becoming “idle” does not automatically turn that inventory into stablecoin.

A possible training objective is **change in net equity minus change in a stated benchmark, normalized by starting capital**, with optional pre-declared drawdown or inventory penalties. Evaluate the unpenalized financial ledger as well. The penalty is an engineering preference, not a measured economic expense.

Do not subtract “impermanent loss” and “LVR” as additional costs from a ledger that already contains all token-value changes. Report those concepts separately, with their respective holding and rebalancing benchmarks. A model must not appear profitable merely because a diagnostic loss was omitted or counted inconsistently.[28]

Counterfactual and execution limitations

Historical swaps occurred under historical liquidity. Inserting our LP changes fee shares and potentially price paths and trader behavior. Begin with an explicitly small, price-taking hypothetical position; recalculate its local fee participation and state the unmodeled feedback. Larger deployments require a more demanding impact model. The small-position assumption is a limit of the experiment, not proof of scalability.

Use realistic tick rounding, required token ratios, rebalance timing and transaction costs. Test delayed execution and higher cost scenarios. Include external-price dislocations, stablecoin deviations and periods with poor fee opportunity where present in the data. Treat additional transaction-ordering or MEV costs as explicit modeled assumptions if historical data cannot identify them.

Metrics to publish together

Net excess return against the stated baseline | Absolute equity return; maximum drawdown; distribution of period returns.

Paired advantage over adaptive LP controls | Token exposure; fees; transaction costs; turnover; fraction of time active.

Stability under cost and delay stress | Results by market regime and seed; prediction calibration; reward and graph ablations.

An attractive annualized return from one favorable interval is not sufficient. The experiment should produce a reproducible decision ledger so that every action can be traced to past inputs and every gain can be traced to inventory changes or earned fees.

# 10. Implementation path and further experiments

A staged path with explicit stopping points

**Stage 1: reference and data integrity.** Reproduce a small published Shiu stimulus-response example in its own environment. Separately ingest the selected LP graph, validate IDs, signs, duplicate aggregation and matrix orientation. Do not claim that running a new dataset reproduces a paper's old dataset.

**Stage 2: inexpensive prediction benchmark.** Start with a documented subnetwork of roughly 1,000 nodes, then test a larger one if justified. Measure out-of-sample representation value before building an expensive whole-network training system. A subnetwork is an engineering approximation and must be labeled as such.

**Stage 3: LP replay.** Validate the accounting independently, compare restricted range policies and run the interventions described above. **Stage 4: shadow operation.** If replay results remain convincing, observe live inputs and record hypothetical actions to test latency and data reliability. Any funded deployment would be a separate decision after those results.

Practical computational choices

Store graphs sparsely. A dense 139,255 by 139,255 float32 matrix alone would require approximately 77.6 GB in decimal units, before simulation state or training memory. Preserve neuron IDs as integers; never route large IDs through floating-point values. Document whether matrix rows represent receiving or sending neurons. Estimate actual memory from the filtered edge set.

The original Brian2 code is a portable starting point for reference experiments. Accelerated implementations may introduce operating-system and hardware constraints.[8,9] A Loihi 2 preprint demonstrates another hardware route for large connectome simulation, but does not establish learning, consciousness or a financial advantage.[35] No runtime or hardware budget has been benchmarked for this project.

Biological milliseconds and market minutes are not automatically equivalent. Input presentation duration, update frequency, state decay and learning timescale are experiment parameters. Fix and test them. For large reservoirs, avoid accidentally constructing dense training matrices or inverses that erase the memory benefit of sparse simulation.

Other worthwhile experiments

Regime-shift detection | Does recurrence detect changing conditions earlier than an ordinary filter?

Learning and forgetting | Does explicit plasticity adapt and retain useful behavior without excessive interference?

Circuit perturbation | Are identifiable graph components necessary for the measured computation?

Embodied navigation | Do specified circuits predict both movement and neural responses under perturbation?

The recommended next discussion is to choose the main objective: financial performance, learning mechanisms or biological fidelity. For the stated DEX goal, start with the frozen-reservoir range experiment. Its value is that a positive, negative or inconclusive result can each be scientifically informative.

# Sources and reading coverage


1. [FlyWire Codex](https://codex.flywire.ai/). Official dataset explorer. Dataset catalogue inspected; current release names and displayed counts.

2. [FlyWire public-data guidelines](https://flywire.ai/guidelines). Official release terms. Public-release and license statements inspected.

3. [MaleCNS: download the dataset](https://male-cns.janelia.org/download/). Official data documentation. File descriptions, filtering context, API and CC-BY license inspected.

4. [MaleCNS media gallery](https://male-cns.janelia.org/media/). Official dataset description. Neuron and cell-type counts verified.

5. [FlyWire whole-brain connectome, v783.0](https://zenodo.org/records/10676866). Zenodo, 2024. File manifests, sizes and release descriptions inspected.

6. [murthylab/codex](https://github.com/murthylab/codex). Official source repository. README and Apache-2.0 license inspected; software not executed.

7. [Shiu et al. A Drosophila computational brain model reveals sensorimotor processing](https://www.nature.com/articles/s41586-024-07763-9). Nature, 2024. Main results, selected methods and limitations reviewed.

8. [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model). Paper implementation. README, release configuration and MIT license inspected; not executed.

9. [eonsystemspbc/fly-brain](https://github.com/eonsystemspbc/fly-brain). Simulation software repository. README, hardware requirements and licensing inspected; not benchmarked.

10. [Dorkenwald et al. Neuronal wiring diagram of an adult brain](https://doi.org/10.1038/s41586-024-07558-y). Nature, 2024. Abstract and accessible main-text excerpts reviewed; full-page access was intermittent.

11. [Schlegel et al. Whole-brain annotation and multi-connectome cell typing of Drosophila](https://www.nature.com/articles/s41586-024-07686-5). Nature, 2024. Main text, selected methods and data availability reviewed.

12. [Eckstein et al. Neurotransmitter classification from electron microscopy images at synaptic sites in Drosophila melanogaster](https://doi.org/10.1016/j.cell.2024.03.016). Cell, 2024. Abstract and accessible results screened; not a full-methods audit.

13. [Lappalainen et al. Connectome-constrained networks predict neural activity across the fly visual system](https://www.nature.com/articles/s41586-024-07939-3). Nature, 2024. Main results and model-construction methods reviewed.

14. [Pospisil et al. The fly connectome reveals a path to the effectome](https://www.nature.com/articles/s41586-024-07982-0). Nature, 2024. Accessible main-text excerpts and causal-inference proposal reviewed.

15. [Eschbach et al. Recurrent architecture for adaptive regulation of learning in the insect brain](https://www.nature.com/articles/s41593-020-0607-9). Nature Neuroscience, 2020. Abstract screened; larval learning-circuit evidence, not adult whole-brain validation.

16. [Costi et al. The Drosophila Connectome as a Computational Reservoir for Time-Series Prediction](https://pmc.ncbi.nlm.nih.gov/articles/PMC12109256/). Biomimetics, 2025; 10(5):341. Full accessible article reviewed, including methods, comparisons and limitations.

17. [Morra and Daley. Imposing Connectome-Derived Topology on an Echo State Network](https://arxiv.org/abs/2201.09359). arXiv:2201.09359, 2022. Abstract screened; earlier connectome-derived reservoir work.

18. [Morra and Daley. Using Connectome Features to Constrain Echo State Networks](https://arxiv.org/abs/2206.02094v2). arXiv:2206.02094v2, revised 2023. Abstract screened; conditional benefits and adverse topology modifications.

19. [Wang-Chen et al. NeuroMechFly v2: simulating embodied sensorimotor control in adult Drosophila](https://www.nature.com/articles/s41592-024-02497-y). Nature Methods, 2024. Abstract, figure descriptions and code/data availability reviewed; subscription body unavailable.

20. [Vaxenburg et al. Whole-body physics simulation of fruit fly locomotion](https://www.nature.com/articles/s41586-025-09029-4). Nature, 2025. Accessible main-text results and controller description reviewed.

21. [Jin et al. Whole-Brain Connectomic Graph Model Enables Whole-Body Locomotion Control in Fruit Fly](https://arxiv.org/html/2602.17997v1). arXiv:2602.17997v1, 2026; preprint. Methods, training pipeline and comparison tables reviewed.

22. [Eon Systems. Embodied brain emulation: technical disclosure](https://eon.systems/updates/embodied-brain-emulation). Company technical report, March 2026. Full disclosure reviewed; company demonstration, not independent validation.

23. [Bates et al. Distributed control circuits across a brain-and-cord connectome](https://www.nature.com/articles/s41586-026-10735-w). Nature, 2026. Abstract and selected main-text passages reviewed.

24. [Male CNS Connectome](https://male-cns.janelia.org/). Official release site, 2026. Release information and paper links inspected; Cell full text not accessible.

25. [Butlin et al. Consciousness in Artificial Intelligence: Insights from the Science of Consciousness](https://arxiv.org/abs/2308.08708). arXiv:2308.08708v3, 2023. Abstract and indicator-based framing screened; not a consciousness test of FlyWire.

26. [Kagan et al. In vitro neurons learn and exhibit sentience when embodied in a simulated game-world](https://doi.org/10.1016/j.neuron.2022.09.001). Neuron, 2022. Primary-paper summary and experimental setup screened; living cultured neurons.

27. [Adams et al. Uniswap v3 Core](https://app.uniswap.org/whitepaper-v3.pdf). Protocol whitepaper, 2021. Concentrated-liquidity mechanics and fee-accounting sections reviewed.

28. [Milionis et al. Automated Market Making and Loss-Versus-Rebalancing](https://arxiv.org/html/2208.06046v6). arXiv:2208.06046v6, 2026 revision of 2022 work. Return decomposition, assumptions and LVR/LVH distinction reviewed.

29. [Fritsch and Canidio. Measuring Arbitrage Losses and Profitability of AMM Liquidity](https://arxiv.org/html/2404.05803v2). ACM Web Conference Companion, 2024. Abstract, empirical setup and discussion/conclusion reviewed.

30. [Bar-On and Mansour. Uniswap Liquidity Provision: An Online Learning Approach](https://arxiv.org/html/2302.00610v2). arXiv:2302.00610v2, 2023. Learning formulation and simplifying assumptions reviewed.

31. [Zhang, Chen and Yang. Adaptive Liquidity Provision in Uniswap V3 with Deep Reinforcement Learning](https://arxiv.org/html/2309.10129v1). arXiv:2309.10129v1, 2023; preprint. Reward, simulation assumptions, baselines and evaluation setup reviewed.

32. [nftechie/stonkfly](https://github.com/nftechie/stonkfly). Public experimental repository. README and stated limitations inspected; no independent performance verification.

33. [Stonkfly: model documentation](https://github.com/nftechie/stonkfly/blob/main/docs/model.md). Project technical disclosure. Encoder, decoder, learning claims and limitations reviewed.

34. [SotoAlt/traderfly-brain](https://github.com/SotoAlt/traderfly-brain). Public project repository. README, decision pipeline and rights statement inspected; not executed.

35. [Neuromorphic Simulation of Drosophila Melanogaster Brain Connectome on Loihi 2](https://arxiv.org/abs/2508.16792). arXiv:2508.16792, 2025; preprint. Abstract screened; hardware mapping evidence only.

36. [Guragain et al. The Whale That Outswam Evolution: Swarm Intelligence Maximises Memory in Connectome Reservoirs](https://arxiv.org/abs/2606.09902). arXiv:2606.09902, 2026; preprint. Abstract screened; the Drosophila representation contains only 49 nodes.

37. [TuragaLab/flyvis](https://github.com/TuragaLab/flyvis). Visual-model source repository. Official implementation identified; not executed.

38. [Matsliah, Yu et al. Neuronal parts list and wiring diagram for a visual system](https://www.nature.com/articles/s41586-024-07981-1). Nature, 2024. Accessible main-text and data-availability passages reviewed.

39. [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Official license deed. License permissions and attribution conditions inspected.

40. [Codex frequently asked questions](https://codex.flywire.ai/faq). Official documentation. Connection thresholds, data interpretation and access guidance inspected.
