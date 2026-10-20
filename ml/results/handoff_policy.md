# Identity continuity policy (handoff_v2)

Script: `ml/scripts/tune_handoff_policy.py`. Raw numbers: `handoff_policy.json`. The policy itself is `POLICY` in `services/api/domain/tracks.py`, and the script runs that exact code.

## Setup

- Footage: 8-Calves test video `pmfeed_4_3_16`, first 10 minutes (12,000 frames, 20 fps), tracked by `calf_detector_v1` + BoT-SORT with re-ID.
- Two five-minute segments. At the start of each, every calf's identity is locked to its track, as a scan-zone handoff would do. Each labelled calf box after that is scored as correct, wrong (another calf's identity), or uncertain (no identity).
- Grid: `max_gap_s` {0.5, 1, 2, 5}, `crowd_iou` {0.3, 0.4, 0.5, 0.6, 0.7}, `crowd_s` {0.25, 0.5, 0.75, 1, 2, off}.
- Selection, safety first: the fewest wrong identities in the worse segment, then the most correct identities in the worse segment.

## Result

Chosen: `max_gap_s = 1.0`, `crowd_iou = 0.6`, `crowd_s = 0.25`. The identity is dropped when the track is missing for more than 1 s, or when it overlaps another calf at IoU > 0.6 for 0.25 s. The release counts from the start of the overlap.

| Rule | Minutes 0-5 correct | 0-5 wrong | Minutes 5-10 correct | 5-10 wrong |
| --- | --- | --- | --- | --- |
| Naive (keep identity forever) | 0.704 | 0.000 | 0.679 | **0.023** |
| Previous rule (drop on any overlap IoU > 0.3) | 0.103 | 0.000 | 0.182 | 0.000 |
| **handoff_v2 (chosen)** | **0.676** | **0.000** | **0.545** | **0.000** |

The remaining share is uncertain, never wrong. Under 0.4% of calves were not detected.

## Caveats

- The first segment has no identity swap, so it cannot separate safe policies from unsafe ones. Selection therefore used both segments, and there is **no held-out estimate**. The naive rule's 2.3% wrong comes from one swap in minutes 5-10, after an overlap lasting between 0.5 and 1 s.
- One pen, one camera angle, eight calves. Other barns may have different crowding patterns. Revalidate on the target farm's footage before relying on the numbers.
- A released identity is never re-attached automatically. Re-attaching it safely needs a cattle-specific appearance embedding (planned: MultiCamCows2024).
