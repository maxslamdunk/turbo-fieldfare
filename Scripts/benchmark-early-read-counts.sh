#!/bin/bash
# More early reads per layer: the early-read benchmark with the fitted guess at
# 3 and 4 reads per layer (TURBO_FIELDFARE_EARLY_EXPERT_READS), each case in
# the order x3, x4, x4, x3. Run it right after Scripts/benchmark-early-read.sh,
# whose fitted x2 runs are the comparison. Same protocol; results go to
# benchmark-results-counts/, so both scripts can run in one checkout.
SETTINGS="fitted3 fitted4 fitted4 fitted3" \
OUT=${OUT:-benchmark-results-counts} \
  exec "$(dirname "$0")/benchmark-early-read.sh"
