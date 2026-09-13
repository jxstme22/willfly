# Neural experiment runbook

1. Verify and freeze the connectome release, license, source hash and curated
   node/edge filters. Keep node IDs as text and reconcile excluded records.
2. Build the sparse directed graph and record orientation, sign and weight
   transforms. Generate random/shuffled controls with matching properties.
3. Run the rate-based reservoir with a fresh state per token episode. Confirm
   impulse decay, constant-input boundedness and graph hash stability.
4. Fit only the readout on the training split. Keep graph weights frozen and
   record the before/after graph hashes.
5. Compare fly, random, shuffled, raw-feature and ordinary recurrent models
   under the same ledger, labels, policy and cost scenarios for five seeds.
6. Run reset-state, no-reservoir, input-mapping and graph-organization
   ablations. Publish negative and inconclusive results.

No model result authorizes trading. The current release remains inconclusive
until the data, sample, uncertainty and evidence gates pass.
