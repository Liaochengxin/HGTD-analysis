#!/usr/bin/env python3
"""Generate run_local.py inputs for each wafer.

Every mode discovers wafers from the per-wafer ZIPs alone (ZIP stem =
serial, parent directory = wafer name) and generates a job.sh wrapper that
stages each ZIP into node scratch at run time: extract, validate the 780
per-channel CSVs, write the runtime config, run the macro, clean up.
Nothing is unpacked on the submission side or inside the sample tree
(ADR 0001 and 0002).
"""

import re
import shlex
import sys
import tarfile
from pathlib import Path

import yaml


# scratch setup + exit handling shared by every mode's wrapper; expects
# WAFER, DATA_PREFIX and log_msg() to be defined by the preamble
TRAP_BLOCK = """
SCRATCH="${TMPDIR:-/tmp}/CQC_$WAFER"
trap 'status=$?; rm -rf "$SCRATCH"; if [ "$status" -ne 0 ]; then log_msg "FAILED wafer=$WAFER step=$CURRENT_STEP status=$status"; else log_msg "SUCCESS wafer=$WAFER"; fi; exit "$status"' EXIT
"""

# wrapper steps shared by every mode; expects WAFER, SERIAL, ZIP_PATH,
# DATA_PREFIX, SCRATCH, MAIN_PATH, TEMP_FILE, ROOT_MACRO, OUTPUT_PATH and
# RUN_LOCAL to be defined by the preamble
STAGED_JOB_STEPS = """CURRENT_STEP="extract and validate $SERIAL"
python3 - "$ZIP_PATH" "$SCRATCH" "$DATA_PREFIX" <<'PY'
import re
import sys
import zipfile

zip_path, dest, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
pattern = re.compile(
    re.escape(prefix) + r"(0[1-9]|[1-4][0-9]|5[0-2])-([1-9]|1[0-5])\\.csv$"
)
with zipfile.ZipFile(zip_path) as archive:
    names = archive.namelist()
    matched = [name for name in names if pattern.fullmatch(name)]
    if len(names) != 780 or len(matched) != 780:
        unmatched = sorted(set(names) - set(matched))[:10]
        sys.stderr.write(
            "ERROR " + zip_path + ": expected 52x15=780 members named "
            "<serial-prefix><sensor 01-52>-<column 1-15>.csv, found "
            + str(len(names)) + " members, " + str(len(matched))
            + " matching; unmatched: " + repr(unmatched) + "\\n"
        )
        sys.exit(1)
    archive.extractall(dest)
print("validated 780 CSVs from " + zip_path)
PY
log_msg "scratch ready: $SCRATCH"
CURRENT_STEP="write runtime config"
cat > "$SCRATCH/config_$WAFER.yaml" <<EOF
main_path: $MAIN_PATH
wafer_name: $WAFER
serial_number: $SERIAL
input_prefix: $SCRATCH/$DATA_PREFIX
temp_file: $TEMP_FILE
root_macro: $ROOT_MACRO
output_path: $OUTPUT_PATH
EOF
CURRENT_STEP="run analysis for $WAFER"
cd "$MAIN_PATH"
python3 "$RUN_LOCAL" "$SCRATCH/config_$WAFER.yaml"
"""


with Path(sys.argv[1]).open() as file:
    config = yaml.safe_load(file)

main_path = Path(config["main_path"])
wafer_folder = main_path / config["wafer_folder"]
script_folder = main_path / config["script_folder"]
run_local = main_path / config["run_local"]
script_folder.mkdir(parents=True, exist_ok=True)

# the ZIP is the only staged raw form: discovery reads the ZIP names alone
wafers = []  # (wafer directory name, serial number) per wafer ZIP
seen = set()
for zip_path in sorted(wafer_folder.glob("*/*.zip")):
    wafer_name = zip_path.parent.name
    serial_number = zip_path.stem
    if wafer_name in seen:
        raise ValueError(f"multiple ZIPs found for wafer {wafer_name}")
    if not re.fullmatch(r"20WS\d+", serial_number):
        raise ValueError(f"unexpected wafer ZIP name {zip_path.name}: "
                         f"stem must be 20WS<digits>")
    seen.add(wafer_name)
    wafers.append((wafer_name, serial_number))


def shared_job_sh() -> Path:
    """Wrapper for local and ihep: the wafer ZIP is resolved by directory glob."""
    job_sh = script_folder / "job.sh"
    job_sh.write_text(f"""#!/bin/bash
# CQC job wrapper: one wafer per job.
# The per-wafer ZIP is the only staged raw form: the wrapper reads the ZIP
# straight from the shared filesystem, extracts it into node scratch,
# validates it, writes the runtime config and runs the analysis. The shared
# tree is never unpacked, and the scratch copy is removed on exit.
# argument: wafer directory name under ZIP_DIR
set -euo pipefail
WAFER="${{1:-}}"
log_msg() {{ printf '[%s] %s\\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }}
if [ -z "$WAFER" ]; then log_msg "ERROR usage: job.sh <wafer-dir-name>"; exit 2; fi
log_msg "START wafer=$WAFER host=$(hostname)"
ZIP_DIR={shlex.quote(str(wafer_folder))}
TEMP_FILE={shlex.quote(str(main_path / config["temp_file"]))}
ROOT_MACRO={shlex.quote(str(main_path / config["root_macro"]))}
OUTPUT_PATH={shlex.quote(str(main_path / config["output_path"]))}
RUN_LOCAL={shlex.quote(str(run_local))}
MAIN_PATH={shlex.quote(str(main_path))}
CURRENT_STEP="resolve wafer ZIP"
shopt -s nullglob
zips=("$ZIP_DIR/$WAFER"/*.zip)
shopt -u nullglob
if [ "${{#zips[@]}}" -ne 1 ]; then
    log_msg "ERROR expected exactly one ZIP under $ZIP_DIR/$WAFER, found ${{#zips[@]}}"
    exit 1
fi
ZIP_PATH="${{zips[0]}}"
SERIAL="${{ZIP_PATH##*/}}"
SERIAL="${{SERIAL%.zip}}"
DATA_PREFIX="20WS20${{SERIAL:7:2}}${{SERIAL: -4}}"{TRAP_BLOCK}
""" + STAGED_JOB_STEPS)
    job_sh.chmod(0o755)
    return job_sh


if config["mode"] == "local":
    job_sh = shared_job_sh()
    shell_file = script_folder / "run_all.sh"
    commands = [
        "#!/bin/bash",
        "set -e",
        f"JOB_SH={shlex.quote(str(job_sh))}",
        "WAFERS=(",
    ]
    for wafer_name, _ in wafers:
        commands.append(f"    {shlex.quote(wafer_name)}")
    commands += [
        ")",
        "",
        'for WAFER in "${WAFERS[@]}"; do',
        '    bash "$JOB_SH" "$WAFER"',
        "done",
        "",
    ]

elif config["mode"] == "ihep":
    log_folder = main_path / config["log_folder"]
    log_folder.mkdir(parents=True, exist_ok=True)
    submit_options = config["hep_sub_options"].strip()
    submit_command = "hep_sub" if not submit_options else f"hep_sub {submit_options}"
    job_sh = shared_job_sh()
    shell_file = script_folder / "run_all.sh"
    commands = [
        "#!/bin/bash",
        "set -e",
        f"JOB_SH={shlex.quote(str(job_sh))}",
        "WAFERS=(",
    ]
    for wafer_name, _ in wafers:
        commands.append(f"    {shlex.quote(wafer_name)}")
    commands += [
        ")",
        "",
        "if [ \"$#\" -eq 1 ]; then",
        "    WAFER=\"${WAFERS[$1]}\"",
        "    bash \"$JOB_SH\" \"$WAFER\"",
        "    exit $?",
        "fi",
        "",
    ]
    stdout = log_folder / "job_%{ProcId}.out"
    stderr = log_folder / "job_%{ProcId}.err"
    commands.append(
        f"{submit_command} -o {shlex.quote(str(stdout))} "
        f"-e {shlex.quote(str(stderr))} -argu \"%{{ProcId}}\" "
        f"-n {len(wafers)} {shlex.quote(str(shell_file))}"
    )
elif config["mode"] == "cern":
    atlas_local_root_base = config["atlas_local_root_base"]
    python_version = config["python_version"]
    root_version = config["root_version"]
    venv_path = config["venv_path"].rstrip("/")
    eos_input_dir = config["eos_input_dir"].rstrip("/")
    eos_output_dir = config["eos_output_dir"].rstrip("/")
    flavour = config.get("flavour", "microcentury")

    # two columns: wafer directory and serial (ZIP stem) — all known at
    # generation time; the wrapper derives the CSV filename prefix from the
    # serial, so no jobs need runtime discovery
    list_file = script_folder / "filelist.txt"
    list_file.write_text("".join(f"{row[0]} {row[1]}\n" for row in wafers))

    job_sh = script_folder / "job.sh"
    job_sh.write_text(f"""#!/bin/bash
# CQC job wrapper for the CERN EosSubmit schedds: one wafer per job.
# The per-wafer ZIP is the only staged raw form: the wrapper reads the ZIP
# straight from {eos_input_dir}, extracts it into node scratch, validates it,
# writes the runtime config and runs the analysis. The EOS tree is never
# unpacked, and the scratch copy is removed on exit.
# The only declared input is the frozen code snapshot src.tar: the pool runs
# the packaged code, external edits never touch running jobs.
# arguments come from: queue wafer, serial from filelist.txt
set +e
set -o pipefail
WAFER="$1"
SERIAL="$2"
log_msg() {{ printf '[%s] %s\\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }}
log_msg "START wafer=$WAFER serial=$SERIAL host=$(hostname)"
export ATLAS_LOCAL_ROOT_BASE={shlex.quote(atlas_local_root_base)}
log_msg "Loading ATLAS local environment"
source "$ATLAS_LOCAL_ROOT_BASE/user/atlasLocalSetup.sh"
status=$?
if [ "$status" -ne 0 ]; then log_msg "ERROR ATLAS setup failed (exit=$status)"; exit "$status"; fi
log_msg "Loading Python {python_version}"
lsetup {shlex.quote(f"python {python_version}")}
status=$?
if [ "$status" -ne 0 ]; then log_msg "ERROR Python setup failed (exit=$status)"; exit "$status"; fi
log_msg "Loading ROOT {root_version}"
lsetup {shlex.quote(f"root {root_version}")}
status=$?
if [ "$status" -ne 0 ]; then log_msg "ERROR ROOT setup failed (exit=$status)"; exit "$status"; fi
log_msg "Activating Python environment {venv_path}"
source {shlex.quote(venv_path + "/bin/activate")}
status=$?
if [ "$status" -ne 0 ]; then log_msg "ERROR venv activation failed (exit=$status)"; exit "$status"; fi
log_msg "Environment ready: Python=$(python3 --version 2>&1), ROOT=$(root-config --version 2>&1)"
CURRENT_STEP="unpack src.tar"
set -e
tar xf src.tar
log_msg "Source archive unpacked"
# the submit-dir absolute path is only known inside the job, and the scratch
# path only exists at run time, so the config is written by this wrapper;
# EOS locations are baked in
ZIP_PATH={shlex.quote(eos_input_dir)}/$WAFER/$SERIAL.zip
TEMP_FILE={shlex.quote(eos_input_dir)}/wafer_temperature_template.csv
ROOT_MACRO=${{PWD}}/src/Card52_v3.C
OUTPUT_PATH={shlex.quote(eos_output_dir)}
RUN_LOCAL=${{PWD}}/src/run_local.py
MAIN_PATH=$PWD
CURRENT_STEP="resolve wafer ZIP"
if [ ! -f "$ZIP_PATH" ]; then
    log_msg "ERROR no ZIP at $ZIP_PATH"
    exit 1
fi
DATA_PREFIX="20WS20${{SERIAL:7:2}}${{SERIAL: -4}}"{TRAP_BLOCK}
""" + STAGED_JOB_STEPS)
    job_sh.chmod(0o755)

    # code snapshot frozen at generation time: the pool runs exactly this copy,
    # so src.tar must be regenerated with the submit files after every edit
    src_tar = script_folder / "src.tar"
    cqc_dir = Path(__file__).resolve().parent
    with tarfile.open(src_tar, "w") as tar:
        for fname in ("Card52_v3.C", "run_local.py"):
            tar.add(cqc_dir / fname, arcname=f"src/{fname}")

    sub_file = script_folder / "cern_batch.sub"
    sub_file.write_text(f"""universe     = vanilla
executable   = job.sh
arguments    = $(wafer) $(serial)
transfer_input_files  = src.tar
output       = out/$(ClusterId).$(ProcId).out
error        = out/$(ClusterId).$(ProcId).err
log          = logs/$(ClusterId).log
+JobFlavour  = "{flavour}"
MY.WantOS    = "el9"
queue wafer, serial from filelist.txt
""")
else:
    raise ValueError(f"Unknown mode: {config['mode']}")

if config["mode"] == "cern":
    print(f"CERN submit files: {list_file}, {job_sh}, {sub_file}")
else:
    shell_file.write_text("\n".join(commands) + "\n")
    shell_file.chmod(0o755)
    print(f"Submit files: {job_sh}, {shell_file}")
