# Training and hybrid AI design

13 September 2026. Targeted research performed after the project-direction and initial experiment-plan updates. Proposed methods have not been implemented or benchmarked here.

## Answer

Yes, a model constructed from fly connectivity can be trained. A connectome is an anatomical graph, not a pretrained language model or a financial policy. We must choose mathematical dynamics, inputs, outputs, trainable parameters and feedback. Updating simulated activity is not itself learning; learning changes parameters or another persistent learned representation.

## Evidence and boundaries

1. **Task optimization with biological constraints:** Lappalainen et al. trained a fly visual-system model with gradient-based optimization while retaining measured connectivity. Their approximately 45,669 model neurons used 734 shared neural parameters, including neuron time constants, resting potentials and synaptic scale factors; a decoder was trained too. This is direct evidence that connectome constraints and deep learning can coexist. The specialized visual circuit and its parameter-sharing assumptions are not a recipe for a whole-brain market agent. [Nature, 2024](https://www.nature.com/articles/s41586-024-07939-3). Relevant construction and training passages re-read in this session.

2. **Training spiking models:** Neftci, Mostafa and Zenke explain surrogate-gradient methods for learning in spiking networks despite discontinuous spike generation. This establishes a candidate optimization approach, not financial effectiveness or a claim that real fly synapses use backpropagation. [Author paper, 2019](https://arxiv.org/abs/1901.09948). Abstract and method framing checked; implementation details need a full-methods review before choosing a spiking learner.

3. **Learned connectomic control:** The FlyGM preprint reports reinforcement-learned locomotion control using a whole-brain graph. The original literature review examined v1 methods; this session checked the v3 abstract, revised June 2026. Do not transfer v1 method details to v3 without comparison. Neither version establishes trading performance. [FlyGM, 2026 preprint](https://arxiv.org/abs/2602.17997).

4. **Frozen reservoir:** The original review examined Costi et al.'s connectome-derived reservoir for physical time-series prediction. Its conditional results motivate readout-only training and matched random controls. Full text was previously reviewed; current re-access encountered an access challenge. [Costi et al., 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12109256/).

## Recommended training progression

| Experiment | What changes during training | What it tests |
|---|---|---|
| Frozen reservoir | Small output layer; recurrent weights fixed | Whether graph dynamics provide useful temporal features |
| Constrained tuning | Selected encoder, time constants, gains or synaptic scales, plus output layer | Whether task adaptation improves the biologically structured model |
| Policy learning | Action policy optimized using a defined replay environment and reward | Whether better predictions become better decisions after costs |
| Online plasticity | Explicit update rules change allowed parameters from newly available feedback | Adaptation, stability, delayed credit assignment and retention |

Select progression by evidence, not model size. A differentiable non-spiking recurrent model is a reasonable initial engineering candidate: spiking is neither necessary for recurrence nor sufficient for biological fidelity. There is no pretrained trading checkpoint here that can simply receive an LLM-style fine-tuning dataset.

For the first task, present market observations only up to time t, preserve recurrent state, predict predeclared future outcomes, and train the readout from labels once their horizon has elapsed. Freeze parameters for evaluation while continuing ordinary activity updates. Record state reset/warm-up rules across assets and episodes. Fit input normalization only on training data. Use identical labels and decision rules across model variants.

## Combine tools and LLMs through defined interfaces

**Tools:** obtain events, quote/execution information, contract facts and LP observations. Preserve source and arrival timestamps. Robinhood execution support must be established separately from data support.

**LLM:** translate public text into structured, source-linked observations such as narrative category, explicit claims, contradictions and uncertainty. Support research and explanation. Initially use retrieval and schema validation; no LLM fine-tuning is required. Fine-tuning becomes a separate option only if a labeled dataset and evaluation demonstrate a recurring extraction or classification problem.

**Numerical neural model:** consume market sequences and optional text features, maintain state and estimate outcomes or action preferences. The model need not receive raw prose or call a tool for each neural update.

**Policy and execution software:** convert outputs into feasible actions, enforce allocation and loss constraints, perform exact accounting and eventually construct transactions. Model output does not override these constraints.

This is modular integration, not a literal merger of an LLM's weights and a fly connectome. Joint training is a possible later research problem, but should not obscure which component creates value.

## First hybrid comparison

Run the same chronological experiment with: market features alone; market plus LP behavior; market plus timestamped LLM features; and both additions. Repeat the most promising configuration with ordinary and fly-derived sequence models. This separates data improvements from architectural improvements.

Historical LLM knowledge may leak later token outcomes even when supplied text is timestamped. Mask identities where practical, avoid future retrieval, and use prospective shadow evaluation when contamination cannot be excluded. Do not train on LLM-generated profit labels. Use observed and explicitly modeled outcomes, retaining failed and unresolved exits.

## Current recommendation

Start with reliable observations, a complete ledger and strong baseline models. Test a fixed fly-derived reservoir with a trained readout next. Add LP features and LLM interpretation as separate, measured improvements. Only then decide whether internal fine-tuning or reinforcement learning is worth its added complexity.
