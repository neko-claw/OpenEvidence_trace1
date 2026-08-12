# A4 calibration and same-pool ablation

Runtime already enforces one immutable `InitialCandidatePool` per question and
separates query-local ranking from calibrated cross-query quality. This folder
is the missing formal evidence boundary. Populate reviewed qrels/gold and a
separate calibration split, record ECE/Brier and reliability outputs, and only
then set `calibrated=true`. Raw logits or fixed fixture values are forbidden.

R2/R3 and live Gate2 quality remain PENDING/UNKNOWN while preflight is not READY.
