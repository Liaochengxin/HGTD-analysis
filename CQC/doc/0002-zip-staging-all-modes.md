# 0002 — All modes discover wafers from ZIPs and stage them into node scratch

Status: accepted (2026-10-20)

## Context

ADR 0001 made the IHEP batch chain ZIP-staged: wafer discovery from ZIP
names, per-job extraction into node scratch, validation, runtime config,
cleanup. It deliberately left mode=cern (reads the extracted tree directly
on EOS) and mode=local (static configs over an extracted tree) on the old
flow, pending a real IHEP run. That run succeeded on 2026-10-20, unblocking
the planned extension.

Keeping two flows has a cost: `unzip_cqc.py` extraction is still required
before any local/cern run, `generate_configs.py` carries two discovery
paths and a static-config writer, and the wrapper logic exists in only one
mode. The staging destination was also reconsidered: extracting into the
shared sample tree (instead of scratch) was rejected because it reintroduces
a concurrent small-file write storm on shared storage (lustrefs, EOS), can
strand half-populated `20WS...` directories on job failure, and is a
non-starter for EOS as a write target. Node-local scratch keeps every
failure job-local.

## Decision

One flow for all three modes; the wrapper shape is uniform, only the
destination environment differs:

1. Discovery: every mode builds the wafer list from `*.zip` under the
   batch dir (ZIP stem = serial, parent directory = wafer name; duplicate
   wafers are a generation-time error). Scanning extracted `20WS*`
   directories is removed, and with it the static per-wafer config files —
   the wrapper owns config generation in every mode.
2. Staging destination: `${TMPDIR:-/tmp}/CQC_<wafer>` everywhere. No
   per-mode special cases (`/tmp` for cern, `~/tmp` for local were
   considered and dropped — `$TMPDIR` is set on condor worker nodes and on
   macOS alike, and one expression covers all three).
3. mode=cern: `filelist.txt` shrinks to two columns (`wafer serial`);
   `dprefix` is derived inside the wrapper from the serial, as in ihep.
   The job reads the ZIP from `eos_input_dir/<wafer>/<serial>.zip` by full
   path (the same runtime EOS-read pattern as the temperature table it
   already used), stages, validates, runs, cleans up. `src.tar`,
   `transfer_input_files`, and the EosSubmit conventions (single
   `$(ClusterId)` log, relative paths from the EOS submit dir) are
   unchanged.
4. mode=local: `run_all.sh` loops the same generated `job.sh` over the
   wafer list; single-wafer runs invoke `job.sh <wafer>` directly. The
   `configs/` static tree and the `config_folder` generator key are
   retired.
5. `run_local.py` is untouched: it still reads `input_prefix` from a config
   and runs ROOT; it neither knows nor cares that the prefix now points at
   scratch.

## Consequences

`scirpt/unzip_cqc.py` is obsolete for the entire workflow; the extracted
trees are legacy inputs no consumer reads. Every retry pays one ~1.5 MB
sequential ZIP read per job instead of shared-tree state. A bad ZIP fails
its job at the entrance with member counts, never half-populates anything.
The generator's mode differences shrink to: run_all.sh shape (sequential
loop vs `hep_sub` cluster vs condor submit bundle) and where the wrapper's
preamble gets its paths (shared filesystem vs baked EOS locations after
ATLAS env setup).
