#!/usr/bin/env python3
"""Generate IHEP hep_sub or CERN EosSubmit jobs for the SQC sensor plan.

Usage:
    make_condor_jobs.py CONFIG

Run this on the target cluster after inputs have been copied to their final,
worker-accessible paths. The same build_plan helper is used by local runs.
"""

import argparse
import shlex
import tarfile
from pathlib import Path

import yaml

from run_all_sqc import build_plan, write_plan_manifest


def env_setup(cfg):
    atlas_root = shlex.quote(cfg.get(
        "atlas_local_root_base", "/cvmfs/atlas.cern.ch/repo/ATLASLocalRootBase"
    ))
    root_version = shlex.quote("root " + cfg.get("root_version", "6.40.02-x86_64-el9-gcc15-opt"))
    return f'''export ATLAS_LOCAL_ROOT_BASE={atlas_root}
source "$ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh"
lsetup {root_version}
'''


def generate_ihep(job_dir, plan, cfg, macro, output_root):
    fields = []
    for task in plan:
        fields.append("\t".join(str(task[key]) for key in
                                 ("label", "tp", "probe_tpl", "needle_tpl",
                                  "output_group", "output_sensor")))
    (job_dir / "sensors.list").write_text("\n".join(fields) + "\n")
    job_script = f'''#!/bin/bash
JOB_DIR={shlex.quote(str(job_dir))}
MACRO={shlex.quote(str(macro))}
TN={float(cfg.get('tn', 20.0))}
{env_setup(cfg)}
line=$(sed -n "$(( $1 + 1 ))p" "$JOB_DIR/sensors.list")
if [ -z "$line" ]; then echo "No sensor plan for ProcId=$1" >&2; exit 1; fi
IFS=$'\\t' read -r label tp probe_tpl needle_tpl output_group output_sensor <<< "$line"
out={shlex.quote(str(output_root))}/"$output_group"/"$output_sensor"
mkdir -p "$out"
macro_call="${{MACRO}}(${{tp}},${{TN}},\\\"${{probe_tpl}}\\\",\\\"${{needle_tpl}}\\\",\\\"${{out}}/\\\")"
root -b -q "$macro_call" > "$out/run.log" 2>&1
echo "done: $label -> $out"
'''
    (job_dir / "job.sh").write_text(job_script)

    options = cfg.get("hep_sub_options", "").strip()
    stdout = shlex.quote(str(job_dir / "logs" / "job_%{ProcId}.out"))
    stderr = shlex.quote(str(job_dir / "logs" / "job_%{ProcId}.err"))
    submit_script = f'''#!/bin/bash
cd "$(dirname "$0")"
mkdir -p logs
hep_sub {options} -o {stdout} -e {stderr} -argu "%{{ProcId}}" -n {len(plan)} job.sh
'''
    (job_dir / "submit_all.sh").write_text(submit_script)


def generate_cern(job_dir, plan, cfg, macro, output_root, jobs_name=None):
    if any(any(ch.isspace() for ch in str(task[key]))
           for task in plan for key in
           ("label", "probe_tpl", "needle_tpl", "output_group", "output_sensor")):
        raise SystemExit("CERN queue file paths/labels must not contain whitespace")
    rows = ["\t".join(str(task[key]) for key in
                      ("label", "tp", "probe_tpl", "needle_tpl",
                       "output_group", "output_sensor")) for task in plan]
    (job_dir / "sensors.list").write_text("\n".join(rows) + "\n")
    with tarfile.open(job_dir / "source.tar", "w") as archive:
        archive.add(macro, arcname="src/temp_vbdmin_cross_toIME_v2.C")

    job_script = f'''#!/bin/bash
{env_setup(cfg)}
tar -xf source.tar
label="$1"
tp="$2"
probe_tpl="$3"
needle_tpl="$4"
output_group="$5"
output_sensor="$6"
out={shlex.quote(str(output_root))}/"$output_group"/"$output_sensor"
mkdir -p "$out"
macro_call="$PWD/src/temp_vbdmin_cross_toIME_v2.C($tp,{float(cfg.get('tn', 20.0))},\\"$probe_tpl\\",\\"$needle_tpl\\",\\"$out/\\")"
root -b -q "$macro_call" > "$out/run.log" 2>&1
echo "done: $label -> $out"
'''
    (job_dir / "job.sh").write_text(job_script)
    submit = f'''universe     = vanilla
executable   = job.sh
arguments    = $(label) $(tp) $(probe_tpl) $(needle_tpl) $(output_group) $(output_sensor)
transfer_input_files = source.tar
output       = out/$(ClusterId).$(ProcId).out
error        = out/$(ClusterId).$(ProcId).err
log          = logs/$(ClusterId).log
+JobFlavour  = "{cfg.get('flavour', 'microcentury')}"
MY.WantOS    = "el9"
queue label, tp, probe_tpl, needle_tpl, output_group, output_sensor from sensors.list
'''
    (job_dir / "cern_batch.sub").write_text(submit)
    batch_name_option = (
        f"-batch-name {shlex.quote(jobs_name)} " if jobs_name else ""
    )
    (job_dir / "submit_all.sh").write_text(
        f'#!/bin/bash\ncd "$(dirname "$0")"\nmkdir -p out logs\n'
        f'condor_submit {batch_name_option}cern_batch.sub\n'
    )


def generate_collector(job_dir, output_root):
    template = Path(__file__).with_name("collect_results.py").read_text()
    script = template.replace("DEFAULT_ROOT = None", f"DEFAULT_ROOT = {str(output_root)!r}", 1)
    (job_dir / "collect_results.py").write_text(script)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument(
        "--jobs", metavar="NAME",
        help="override the CERN HTCondor batch name from job_folder",
    )
    args = parser.parse_args()
    config_file = Path(args.config)
    with config_file.open() as stream:
        cfg = yaml.safe_load(stream)
    mode = cfg.get("mode", "ihep").lower()
    if mode not in ("ihep", "cern"):
        raise SystemExit("cluster mode must be 'ihep' or 'cern' in config.yaml")
    if args.jobs is not None and mode != "cern":
        raise SystemExit("--jobs is supported only when mode: cern")
    if args.jobs is not None and not args.jobs.strip():
        raise SystemExit("--jobs NAME must not be empty")

    main_path = Path(cfg["main_path"])
    macro = main_path / cfg["macro"]
    if not macro.is_file():
        raise SystemExit(f"ROOT macro not found: {macro}")
    plan = build_plan(cfg)
    if not plan:
        raise SystemExit("no runnable sensors in plan")

    job_folder = cfg.get("job_folder", "HGTD-analysis/SQC/jobs")
    job_dir = main_path / job_folder
    jobs_name = args.jobs if args.jobs is not None else Path(job_folder).name
    if mode == "cern" and not jobs_name:
        raise SystemExit("job_folder must have a final directory name")
    output_root = main_path / cfg["output_path"]
    job_dir.mkdir(parents=True, exist_ok=True)
    write_plan_manifest(plan, output_root)
    if mode == "ihep":
        generate_ihep(job_dir, plan, cfg, macro, output_root)
    else:
        generate_cern(job_dir, plan, cfg, macro, output_root, jobs_name)
    generate_collector(job_dir, output_root)
    for name in ("job.sh", "submit_all.sh", "collect_results.py"):
        (job_dir / name).chmod(0o755)
    print(f"Generated {mode} package: {job_dir}")
    print(f"Tasks: {len(plan)}; results: {output_root}")


if __name__ == "__main__":
    main()
