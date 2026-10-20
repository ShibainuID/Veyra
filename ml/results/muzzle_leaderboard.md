# Muzzle leaderboard (test animals, split muzzle_v1.json)

|                                   |   rank1 |   top5 |   correct_match |   wrong_match_registered |   unknown_fmr |   threshold | threshold_holds   |
|:----------------------------------|--------:|-------:|----------------:|-------------------------:|--------------:|------------:|:------------------|
| hybrid_dinov3_sift                |  0.9271 | 0.9271 |          0.9251 |                   0.0051 |        0.0142 |      5      | True              |
| sift_ransac                       |  0.9251 | 0.9251 |          0.924  |                   0.001  |        0.017  |      5      | True              |
| dinov3_arcface                    |  0.9661 | 0.9764 |          0.9517 |                   0.0051 |        0.3239 |      0.4797 | False             |
| zeroshot_vit_small_patch16_dinov3 |  0.9394 | 0.961  |          0.8429 |                   0.0021 |        0.1449 |      0.9597 | False             |
| zeroshot_vit_small_patch14_dinov2 |  0.9251 | 0.9528 |          0.8265 |                   0.0072 |        0.1534 |      0.9108 | False             |
