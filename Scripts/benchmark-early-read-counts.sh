#!/bin/bash
# How many experts per layer to read early: the early-read benchmark with the
# fitted guess at 1, 2, 3 and 4 reads per layer
# (TURBO_FIELDFARE_EARLY_EXPERT_READS), each case in the order
#   x1, x2, x3, x4, x4, x3, x2, x1
# Same steps and protocol as Scripts/benchmark-early-read.sh; results go to
# benchmark-results-counts/, so both scripts can run in one checkout.
SETTINGS="fitted fitted2 fitted3 fitted4 fitted4 fitted3 fitted2 fitted" \
OUT=${OUT:-benchmark-results-counts} \
  exec "$(dirname "$0")/benchmark-early-read.sh"
