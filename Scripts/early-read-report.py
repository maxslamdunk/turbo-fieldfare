#!/usr/bin/env python3
"""Turn benchmark-results/ from Scripts/benchmark-early-read.sh into a
benchmark report in the repository's [Benchmark] issue format.

Writes benchmark-results/issue.md and prints a link that opens the
repository's benchmark issue form with every field filled in.

Usage: Scripts/early-read-report.py [results-dir] [owner/repo]
"""
import glob
import hashlib
import os
import re
import statistics
import sys
import urllib.parse

OUT = sys.argv[1] if len(sys.argv) > 1 else "benchmark-results"
REPO = sys.argv[2] if len(sys.argv) > 2 else "maxslamdunk/turbo-fieldfare"
CASES = ["short-explanation", "medium-review", "long-synthesis"]
URL_LIMIT = 7000

FOOTER = re.compile(r"\[stop=(\S+) prefill=(\d+)tok new=(\d+)tok "
                    r"decode=([\d.]+)s tok/s=([\d.]+)\]")
EARLY = re.compile(r"guess=(\S+) needed/tok=([\d.]+) loaded-early/tok=([\d.]+) "
                   r"reads/tok=([\d.]+) precision=([\d.]+)")


def system_field(text, label):
    match = re.search(rf"^\s*{label}:\s*(.+)$", text, re.M)
    return match.group(1).strip() if match else "?"


def mean(values):
    return sum(values) / len(values) if values else None


def label(setting):  # "router2" -> "router ×2"
    match = re.fullmatch(r"([a-z]+)(\d+)", setting)
    return f"{match.group(1)} ×{match.group(2)}" if match else setting


def guess_of(setting):
    return re.sub(r"\d+$", "", setting)


with open(os.path.join(OUT, "system", "system.txt")) as f:
    system = f.read()
lines = system.splitlines()
commit = next((l for l in lines if re.fullmatch(r"[0-9a-f]{40}", l)), "?")
chip = system_field(system, "Chip")
memory = system_field(system, "Memory")
model = system_field(system, "Model Name")
macos = system_field(system, "ProductVersion")
build = system_field(system, "BuildVersion")
swift = re.search(r"Apple Swift version (\S+)", system)
swift = swift.group(1) if swift else "?"
power = "on power" if "AC Power" in system else "on battery"
order = system_field(system, "Settings").split()
pair_order = system_field(system, "Pairs")
pair_order = [] if pair_order == "?" else pair_order.split()


def load(stage):  # -> list of runs, in run order
    runs = []
    for path in glob.glob(os.path.join(OUT, stage, "*.stderr")):
        name = os.path.basename(path)[:-len(".stderr")]
        case = next((c for c in CASES if name.startswith(c + "-")), None)
        if case is None:
            continue
        n, setting = name[len(case) + 1:].split("-", 1)
        with open(path) as f:
            err = f.read()
        footer = FOOTER.search(err)
        if not footer:
            continue
        run = {"case": case, "n": int(n), "setting": setting, "stop": footer.group(1),
               "prefill": int(footer.group(2)), "new": int(footer.group(3)),
               "tps": float(footer.group(5))}
        early = EARLY.search(err)
        if early:
            run.update(guess=early.group(1), needed=float(early.group(2)),
                       loaded=float(early.group(3)), precision=float(early.group(5)))
        with open(path[:-len(".stderr")] + ".stdout", "rb") as f:
            run["text"] = hashlib.sha256(f.read()).hexdigest()
        runs.append(run)
    return sorted(runs, key=lambda r: (CASES.index(r["case"]), r["n"]))


measured, pairs = load("measured"), load("pairs")
everything = measured + pairs
# A fitted run that fell back to the router guess (the model's snapshot does
# not match the bundled guess file) prints guess=router; flag it.
fallbacks = [r for r in everything
             if "guess" in r and r["guess"] != guess_of(r["setting"])]


def settings_of(runs):
    seen = []
    for r in runs:
        if r["setting"] not in seen:
            seen.append(r["setting"])
    return seen


def cell(runs, case, setting, field, fmt):
    value = mean([r[field] for r in runs
                  if r["case"] == case and r["setting"] == setting and field in r])
    return fmt.format(value) if value is not None else "—"


def counters_table(runs, settings, cases):
    on = [s for s in settings if s != "off"]
    table = ["| case | needed/tok | " + " | ".join(
        f"{label(s)}: loaded early, precision" for s in on) + " |",
             "| --- | ---: |" + " ---: |" * len(on)]
    for case in cases:
        needed = cell(runs, case, on[0], "needed", "{:.2f}") if on else "—"
        table.append(f"| {case} | {needed} | " + " | ".join(
            cell(runs, case, s, "loaded", "{:.2f}") + ", "
            + cell(runs, case, s, "precision", "{:.3f}") for s in on) + " |")
    return table


sections = []
if measured:
    stage1 = settings_of(measured)
    cases1 = [c for c in CASES if any(r["case"] == c for r in measured)]
    speed = ["| case | " + " | ".join(map(label, stage1)) + " |",
             "| --- |" + " ---: |" * len(stage1)]
    for case in cases1:
        speed.append(f"| {case} | " + " | ".join(
            cell(measured, case, s, "tps", "{:.3f}") for s in stage1) + " |")
    sections.append(
        "**Stage 1.** Decode tok/s, mean of the runs per setting. Order per case: "
        f"{', '.join(map(label, order))}.\n\n" + "\n".join(speed)
        + "\n\nExpert reads per token with the early read on:\n\n"
        + "\n".join(counters_table(measured, stage1, cases1)))

if pairs:
    a, b = (settings_of(pairs) + [None])[:2]
    rows = ["| pair | runs | " + f"{label(a)} | {label(b)} | {label(b)} vs {label(a)} |",
            "| --- | --- | ---: | ---: | ---: |"]
    changes = []
    for i in range(0, len(pairs) - 1, 2):
        pair = {r["setting"]: r for r in pairs[i:i + 2]}
        if set(pair) != {a, b}:
            continue
        change = pair[b]["tps"] / pair[a]["tps"] - 1
        changes.append(change)
        rows.append(f"| {len(changes)} | {pairs[i]['n']}–{pairs[i + 1]['n']} | "
                    f"{pair[a]['tps']:.3f} | {pair[b]['tps']:.3f} | {change:+.1%} |")
    case = pairs[0]["case"]
    verdict = (f"{label(b)} faster in {sum(c > 0 for c in changes)} of {len(changes)} "
               f"pairs; median {statistics.median(changes):+.1%}, "
               f"range {min(changes):+.1%} to {max(changes):+.1%}." if changes else "")
    sections.append(
        f"**Stage 2.** {case} only, adjacent {label(a)} / {label(b)} pairs, decode tok/s. "
        f"Order: {', '.join(map(label, pair_order))}.\n\n" + "\n".join(rows)
        + f"\n\n{verdict}\n\nExpert reads per token:\n\n"
        + "\n".join(counters_table(pairs, [a, b], [case])))

results = ("\n\n".join(sections)
           + "\n\n2-minute pause before each run; one discarded warmup per case "
           f"(router ×2). {model}, {power}.")
if fallbacks:
    results += ("\n\n**Warning:** {} fitted run(s) used the router guess "
                "(guess=router in the footer): the model does not match the bundled "
                "guess file.".format(len(fallbacks)))

first = {}
for r in everything:
    first.setdefault(r["case"], r)
workload = "\n".join(
    f"{c}: prompt {first[c]['prefill']} tok, generated {first[c]['new']} tok, "
    f"stop={first[c]['stop']}" for c in CASES if c in first)
workload += ("\nFresh process per run (cold expert cache), "
             "docs/benchmark-prompts/real-generation-v1 with their seeds.")
parity = []
for c in CASES:
    texts = {r["text"] for r in everything if r["case"] == c}
    if texts:
        count = sum(r["case"] == c for r in everything)
        parity.append(f"{c}: {len(texts)} distinct output(s) across {count} runs"
                      + (f" (SHA-256 {next(iter(texts))[:16]}…)" if len(texts) == 1 else ""))
parity = "\n".join(parity)
command = ("Scripts/benchmark-early-read.sh (docs/COMMUNITY_BENCHMARKS.md settings: "
           "--max-new 1024 --max-context 4096 --temperature 0.2 --top-k 64 --top-p 0.95, "
           "defaults otherwise), with --early-expert-read off | router | fitted; "
           "\"×N\" sets TURBO_FIELDFARE_EARLY_EXPERT_READS=N.")
fields = {
    "title": f"[Benchmark]: {chip}, {memory}, macOS {macos} — early expert read",
    "commit": commit,
    "hardware": f"{model}, {chip}, {memory}",
    "environment": f"macOS {macos} ({build}), Swift {swift}",
    "command": command,
    "workload": workload,
    "results": results,
    "parity": parity,
}

with open(os.path.join(OUT, "issue.md"), "w") as f:
    f.write(f"# {fields['title']}\n\n")
    for key, heading in [("commit", "Commit"), ("hardware", "Mac hardware and memory"),
                         ("environment", "macOS and Swift versions"),
                         ("command", "Command and runtime controls"),
                         ("workload", "Workload"), ("results", "Results"),
                         ("parity", "Correctness and output")]:
        f.write(f"## {heading}\n\n{fields[key]}\n\n")

url = (f"https://github.com/{REPO}/issues/new?"
       + urllib.parse.urlencode({"template": "benchmark.yml", **fields},
                                quote_via=urllib.parse.quote))
print("\n" + results + "\n\n" + parity + "\n")
if len(url) <= URL_LIMIT:
    print("Open this link, check the report, and press Submit:\n")
    print(url)
else:
    print(f"Open https://github.com/{REPO}/issues/new?template=benchmark.yml and "
          f"paste the sections of {OUT}/issue.md into the matching fields.")
