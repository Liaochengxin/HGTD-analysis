#!/usr/bin/env python3
"""Generate run_local.py inputs for each wafer.

local and cern modes read wafer folders extracted beforehand by
scirpt/unzip_cqc.py: each wafer dir contains a data subfolder named after
its serial number (e.g. B33_17/20WS0013300017/*.csv). ihep mode instead
discovers the per-wafer ZIPs directly (ZIP stem = serial, parent directory
= wafer name) and generates a job.sh wrapper that stages each ZIP into
node scratch at run time. No unzip happens here in either case.
"""

import shlex
import sys
import tarfile
from pathlib import Path

import yaml


with Path(sys.argv[1]).open() as file:
    config = yaml.safe_load(file)

main_path = Path(config["main_path"])
wafer_folder = main_path / config["wafer_folder"]
config_folder = main_path / config["config_folder"]
script_folder = main_path / config["script_folder"]
run_local = main_path / config["run_local"]
config_folder.mkdir(parents=True, exist_ok=True)
script_folder.mkdir(parents=True, exist_ok=True)

wafer_configs = []
cern_rows = []  # (config_name, serial_number, csv filename prefix) for cern mode

if config["mode"] == "ihep":
    # the ZIP is the only staged raw form: the job wrapper extracts it into
    # node scratch at run time, so discovery reads the ZIP names alone
    seen = set()
    for zip_path in sorted(wafer_folder.glob("*/*.zip")):
        wafer_name = zip_path.parent.name
        if wafer_name in seen:
            raise ValueError(f"multiple ZIPs found for wafer {wafer_name}")
        seen.add(wafer_name)
        wafer_configs.append((wafer_name, wafer_name.replace("-", "_"), None))
else:
    for wafer_path in sorted(path for path in wafer_folder.iterdir() if path.is_dir()):
        # extracted data subfolder, named after the wafer serial number
        data_dirs = [
            path for path in wafer_path.iterdir()
            if path.is_dir() and path.name.startswith("20WS")
        ]
        if not data_dirs:
            continue  # not a wafer dir (e.g. aggregate folders)
        data_dir = data_dirs[0]
        wafer_name = wafer_path.name
        config_name = wafer_name.replace("-", "_")
        serial_number = data_dir.name
        data_prefix = f"20WS20{serial_number[7:9]}{serial_number[-4:]}"

        output_file = config_folder / f"config_{config_name}.yaml"
        # cern mode ships no static configs: the sandbox absolute path only
        # exists inside the job, so job.sh writes the config there at run time.
        if config["mode"] == "local":
            wafer_config = {
                "main_path": str(main_path),
                "wafer_name": wafer_name,
                "serial_number": serial_number,
                "input_prefix": str(data_dir.relative_to(main_path) / data_prefix),
                "temp_file": config["temp_file"],
                "root_macro": config["root_macro"],
                "output_path": config["output_path"],
            }
            with output_file.open("w") as file:
                yaml.safe_dump(wafer_config, file, sort_keys=False)
        wafer_configs.append((wafer_name, config_name, output_file))
        if config["mode"] == "cern":
            cern_rows.append((config_name, serial_number, data_prefix))

if config["mode"] == "local":
    print(f"Configs: {config_folder}")

if config["mode"] == "local":
    shell_file = script_folder / "run_all.sh"
    commands = ["#!/bin/bash", "set -e", ""]
    for _, _, wafer_config in wafer_configs:
        commands.append(
            f"python3 {shlex.quote(str(run_local))} {shlex.quote(str(wafer_config))}"
        )

elif config["mode"] == "ihep":
    log_folder = main_path / config["log_folder"]
    log_folder.mkdir(parents=True, exist_ok=True)
    submit_options = config["hep_sub_options"].strip()
    submit_command = "hep_sub" if not submit_options else f"hep_sub {submit_options}"

    # runtime wrapper following the cern-mode job.sh heredoc practice: the
    # scratch path only exists inside the job, so the wrapper stages the ZIP,
    # validates it, and writes the config there at run time
    job_sh = script_folder / "job.sh"
    job_sh.write_text(f"""#!/bin/bash
# CQC job wrapper for the IHEP hep_sub cluster: one wafer per job.
# The per-wafer ZIP is the only staged raw form: the wrapper reads the ZIP
# straight from the shared filesystem, extracts it into node scratch,
# validates it, writes the runtime config and runs the analysis. The shared
# tree is never unpacked, and the scratch copy is removed on exit.
# argument: wafer directory name under ZIP_DIR
set -euo pipefail
wafer="${{1:-}}"
log_msg() {{ printf '[%s] %s\\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }}
if [ -z "$wafer" ]; then log_msg "ERROR usage: job.sh <wafer-dir-name>"; exit 2; fi
log_msg "START wafer=$wafer host=$(hostname)"
ZIP_DIR={shlex.quote(str(wafer_folder))}
TEMP_FILE={shlex.quote(str(main_path / config["temp_file"]))}
ROOT_MACRO={shlex.quote(str(main_path / config["root_macro"]))}
OUTPUT_PATH={shlex.quote(str(main_path / config["output_path"]))}
RUN_LOCAL={shlex.quote(str(run_local))}
MAIN_PATH={shlex.quote(str(main_path))}
CURRENT_STEP="resolve wafer ZIP"
shopt -s nullglob
zips=("$ZIP_DIR/$wafer"/*.zip)
shopt -u nullglob
if [ "${{#zips[@]}}" -ne 1 ]; then
    log_msg "ERROR expected exactly one ZIP under $ZIP_DIR/$wafer, found ${{#zips[@]}}"
    exit 1
fi
zip_path="${{zips[0]}}"
serial="${{zip_path##*/}}"
serial="${{serial%.zip}}"
data_prefix="20WS20${{serial:7:2}}${{serial: -4}}"
scratch="${{TMPDIR:-/tmp}}/CQC_$wafer"
trap 'status=$?; rm -rf "$scratch"; if [ "$status" -ne 0 ]; then log_msg "FAILED wafer=$wafer step=$CURRENT_STEP status=$status"; else log_msg "SUCCESS wafer=$wafer"; fi; exit "$status"' EXIT
CURRENT_STEP="extract and validate $serial"
python3 - "$zip_path" "$scratch" "$data_prefix" <<'PY'
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
log_msg "scratch ready: $scratch"
CURRENT_STEP="write runtime config"
cat > "$scratch/config_$wafer.yaml" <<EOF
main_path: $MAIN_PATH
wafer_name: $wafer
serial_number: $serial
input_prefix: $scratch/$data_prefix
temp_file: $TEMP_FILE
root_macro: $ROOT_MACRO
output_path: $OUTPUT_PATH
EOF
CURRENT_STEP="run analysis for $wafer"
cd "$MAIN_PATH"
python3 "$RUN_LOCAL" "$scratch/config_$wafer.yaml"
""")
    job_sh.chmod(0o755)

    shell_file = script_folder / "run_all.sh"
    commands = [
        "#!/bin/bash",
        "set -e",
        f"JOB_SH={shlex.quote(str(job_sh))}",
        "WAFERS=(",
    ]
    for wafer_name, _, _ in wafer_configs:
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
        f"-n {len(wafer_configs)} {shlex.quote(str(shell_file))}"
    )
elif config["mode"] == "cern":
    atlas_local_root_base = config["atlas_local_root_base"]
    python_version = config["python_version"]
    root_version = config["root_version"]
    venv_path = config["venv_path"].rstrip("/")
    eos_input_dir = config["eos_input_dir"].rstrip("/")
    eos_output_dir = config["eos_output_dir"].rstrip("/")

    # three columns: wafer name, serial dir, CSV filename prefix — all known
    # at generation time, so jobs need no runtime discovery
    list_file = script_folder / "filelist.txt"
    list_file.write_text("".join(f"{row[0]} {row[1]} {row[2]}\n" for row in cern_rows))

    job_sh = script_folder / "job.sh"
    job_sh.write_text(f"""#!/bin/bash
# CQC job wrapper for the CERN EosSubmit schedds: one wafer per job.
# All data I/O goes to EOS by full path: inputs (CSVs + temperature table)
# are read from {eos_input_dir}, results are written straight into
# {eos_output_dir}/<wafer>/ — nothing packed, nothing transferred.
# The only declared input is the frozen code snapshot src.tar: the pool runs
# the packaged code, external edits never touch running jobs.
# arguments come from: queue wafer, serial, dprefix from filelist.txt
set +e
set -o pipefail
wafer="$1"
serial="$2"
dprefix="$3"
log_msg() {{ printf '[%s] %s\\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }}
log_msg "START wafer=$wafer serial=$serial dprefix=$dprefix host=$(hostname)"
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
trap 'status=$?; log_msg "ERROR step=$CURRENT_STEP line=$LINENO exit=$status command=$BASH_COMMAND"; exit "$status"' ERR
set -e
tar xf src.tar
log_msg "Source archive unpacked"
# The sandbox absolute path is only known inside the job, so the config is
# written here instead of shipped statically; EOS locations are baked in.
CURRENT_STEP="write runtime config"
cat > "config_${{wafer}}.yaml" <<EOF
main_path: $PWD
wafer_name: ${{wafer}}
serial_number: ${{serial}}
input_prefix: {eos_input_dir}/${{wafer}}/${{serial}}/${{dprefix}}
temp_file: {eos_input_dir}/wafer_temperature_template.csv
root_macro: ${{PWD}}/src/Card52_v3.C
output_path: {eos_output_dir}
EOF
log_msg "Runtime config ready; launching analysis for wafer=$wafer"
CURRENT_STEP="run analysis for $wafer"
python3 src/run_local.py "config_${{wafer}}.yaml"
log_msg "SUCCESS wafer=$wafer"
""")
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
arguments    = $(wafer) $(serial) $(dprefix)
transfer_input_files  = src.tar
output       = out/$(ClusterId).$(ProcId).out
error        = out/$(ClusterId).$(ProcId).err
log          = logs/$(ClusterId).log
+JobFlavour  = "{config.get("flavour", "microcentury")}"
MY.WantOS    = "el9"
queue wafer, serial, dprefix from filelist.txt
""")
else:
    raise ValueError(f"Unknown mode: {config['mode']}")

if config["mode"] == "cern":
    print(f"CERN submit files: {list_file}, {job_sh}, {sub_file}")
else:
    shell_file.write_text("\n".join(commands) + "\n")
    shell_file.chmod(0o755)
    if config["mode"] == "ihep":
        print(f"IHEP submit files: {job_sh}, {shell_file}")
    else:
        print(f"Shell: {shell_file}")
