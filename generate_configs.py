#!/usr/bin/env python3
"""Generate one run_local.py config for each wafer ZIP."""

import shlex
import sys
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

for wafer_path in sorted(path for path in wafer_folder.iterdir() if path.is_dir()):
    zip_path = next(path for path in wafer_path.glob("*.zip") if not path.name.startswith("._"))
    wafer_name = wafer_path.name
    config_name = wafer_name.replace("-", "_")
    serial_number = zip_path.stem
    data_prefix = f"20WS20{serial_number[7:9]}{serial_number[-4:]}"
    unzip_path = Path(config["unzip_folder"]) / wafer_name

    wafer_config = {
        "main_path": str(main_path),
        "wafer_name": wafer_name,
        "zip_path": str(zip_path.relative_to(main_path)),
        "unzip_path": str(unzip_path),
        "input_prefix": str(unzip_path / data_prefix),
        "temp_file": config["temp_file"],
        "root_macro": config["root_macro"],
        "output_path": config["output_path"],
    }

    output_file = config_folder / f"config_{config_name}.yaml"
    with output_file.open("w") as file:
        yaml.safe_dump(wafer_config, file, sort_keys=False)
    wafer_configs.append((wafer_name, config_name, output_file))

print(f"Configs: {config_folder}")

#run_local = main_path / "HGTD-analysis/run_local.py"

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
    shell_file = script_folder / "run_all.sh"
    commands = [
        "#!/bin/bash",
        "set -e",
        f"MAIN_PATH={shlex.quote(str(main_path))}",
        f"CONFIG_FOLDER={shlex.quote(str(config_folder))}",
        f"RUN_LOCAL={shlex.quote(str(run_local))}",
        "WAFERS=(",
    ]
    for _, config_name, _ in wafer_configs:
        commands.append(f"    {shlex.quote(config_name)}")
    commands += [
        ")",
        "",
        "if [ \"$#\" -eq 1 ]; then",
        "    CONFIG_NAME=\"${WAFERS[$1]}\"",
        "    cd \"$MAIN_PATH\"",
        "    python3 \"$RUN_LOCAL\" \"$CONFIG_FOLDER/config_${CONFIG_NAME}.yaml\"",
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
else:
    raise ValueError(f"Unknown mode: {config['mode']}")

shell_file.write_text("\n".join(commands) + "\n")
shell_file.chmod(0o755)
print(f"Shell: {shell_file}")
