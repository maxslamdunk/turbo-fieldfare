#!/bin/bash
# The community benchmark (docs/COMMUNITY_BENCHMARKS.md), measuring the early
# expert read in two stages. See EARLY_READ_BENCHMARK.md.
#
#   1. Each case in the order off, router, router x2, router x2, router, off:
#      what the early read gives, with one and with two reads per layer.
#   2. short-explanation only, (router x2, fitted x2, fitted x2, router x2)
#      four times: eight adjacent router/fitted pairs, so slow drift over the
#      run cancels within each pair.
#
# "x2" reads 2 experts per layer early (TURBO_FIELDFARE_EARLY_EXPERT_READS=2).
#
# Run from the repository root after
#   swift build -c release --product TurboFieldfareCLI
# with the model at scratch/gemma4.gturbo (or MODEL=<path>).
# Results go to benchmark-results/. About 3 hours on an M1; a 2-minute pause
# precedes each measured run (PAUSE=<seconds> to change it).
# SETTINGS=<order> and PAIRS=<order> change the two stages' settings
# (off, router, fitted, routerN, fittedN; PAIRS= skips stage 2); OUT=<dir>
# changes the results folder.
set -u
MODEL=${MODEL:-scratch/gemma4.gturbo}
PAUSE=${PAUSE:-120}
OUT=${OUT:-benchmark-results}
SETTINGS=${SETTINGS-off router router2 router2 router off}
PAIRS=${PAIRS-router2 fitted2 fitted2 router2 router2 fitted2 fitted2 router2 \
router2 fitted2 fitted2 router2 router2 fitted2 fitted2 router2}
CLI=.build/release/TurboFieldfareCLI
PROMPTS=docs/benchmark-prompts/real-generation-v1

preflight() {
  if pgrep -fl 'TurboFieldfareServer|TurboFieldfareMac|TurboFieldfareDecodeService|TurboFieldfareCLI|TurboFieldfarePackageTests|swiftpm-testing-helper|mlx_lm|mlx-lm'; then
    echo "Another model process is running; stopping." >&2
    exit 1
  fi
}

run_case() {  # <dir> <case> <seed> <label> <setting: off|router|fitted, optionally with a read count>
  local setting=${5%[0-9]} reads=${5##*[a-z]}
  reads=${reads:-1}
  preflight
  echo "$(date '+%H:%M:%S') $1 $2 $4" | tee -a "$OUT/progress.txt"
  { date; pmset -g therm; memory_pressure -Q; } > "$OUT/$1/$2-$4.conditions" 2>&1
  TURBO_FIELDFARE_EARLY_EXPERT_READS=$reads "$CLI" \
    --model "$MODEL" \
    --messages-file "$PROMPTS/$2.json" \
    --max-new 1024 \
    --max-context 4096 \
    --temperature 0.2 \
    --top-k 64 \
    --top-p 0.95 \
    --seed "$3" \
    --early-expert-read "$setting" \
    > "$OUT/$1/$2-$4.stdout" \
    2> "$OUT/$1/$2-$4.stderr"
}

if [ ! -x "$CLI" ]; then
  echo "Build first: swift build -c release --product TurboFieldfareCLI" >&2
  exit 1
fi
mkdir -p "$OUT/system" "$OUT/warmup" "$OUT/measured" "$OUT/pairs"
preflight
{
  git status --short
  git rev-parse HEAD
  echo "Settings: $SETTINGS"
  echo "Pairs: $PAIRS"
  sw_vers
  swift --version
  system_profiler SPHardwareDataType |
    awk -F': ' '/Model Name|Model Identifier|Chip|Total Number of Cores|Memory/ { print $1 ": " $2 }'
  (cd "$MODEL" && shasum -a 256 manifest.json)
  shasum -a 256 "$PROMPTS"/*.json
  pmset -g batt
  df -h / | tail -1
} 2>&1 | tee "$OUT/system/system.txt"

CASES="short-explanation:20260721 medium-review:20260722 long-synthesis:20260723"

for case_seed in $CASES; do
  run_case warmup "${case_seed%%:*}" "${case_seed##*:}" warmup router2
done

for case_seed in $CASES; do
  n=0
  for setting in $SETTINGS; do
    n=$((n + 1))
    sleep "$PAUSE"
    run_case measured "${case_seed%%:*}" "${case_seed##*:}" "$n-$setting" "$setting"
  done
done

n=0
for setting in $PAIRS; do
  n=$((n + 1))
  sleep "$PAUSE"
  run_case pairs short-explanation 20260721 "$n-$setting" "$setting"
done

# One line per run: the timing footer and the early-read line.
for f in "$OUT"/measured/*.stderr "$OUT"/pairs/*.stderr; do
  [ -e "$f" ] || continue
  printf '%s %s %s\n' "$(basename "$(dirname "$f")")/$(basename "$f" .stderr)" \
    "$(grep -h '^\[stop=' "$f")" "$(grep -h '^\[early-read' "$f")"
done | tee "$OUT/summary.txt"

# Generated text must be identical across the runs of each case, both stages.
for case_seed in $CASES; do
  c=${case_seed%%:*}
  files=()
  for f in "$OUT"/measured/"$c"-*.stdout "$OUT"/pairs/"$c"-*.stdout; do
    [ -e "$f" ] && files+=("$f")
  done
  [ ${#files[@]} -gt 0 ] || continue
  echo "$c: $(shasum -a 256 "${files[@]}" | awk '{print $1}' | sort -u |
    wc -l | tr -d ' ') distinct output(s) of ${#files[@]}"
done | tee -a "$OUT/summary.txt"

# A zip of everything, and the pre-filled benchmark issue.
ditto -c -k --keepParent "$OUT" "$OUT.zip"
python3 Scripts/early-read-report.py "$OUT"
