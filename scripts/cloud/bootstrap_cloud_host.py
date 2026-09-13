#!/usr/bin/env python3
"""Idempotently prepare one configured cloud host for later sktlm workloads."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import posixpath
import re
import shlex
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from sktlm.cloud.contracts import Deployment, ExperimentContract


BRIDGE_PATH = Path(__file__).with_name("sktlm_bridge.py")
BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "_sktlm_bootstrap_bridge", BRIDGE_PATH
)
if BRIDGE_SPEC is None or BRIDGE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load cloud bridge: {BRIDGE_PATH}")
bridge = importlib.util.module_from_spec(BRIDGE_SPEC)
sys.modules[BRIDGE_SPEC.name] = bridge
BRIDGE_SPEC.loader.exec_module(bridge)


SCHEMA = "sktlm-cloud-host-bootstrap/v1"
PYTHON_VERSION = "3.11.9"
PYTHON_PREFIX = f"/opt/python-{PYTHON_VERSION}"
PYTHON_BIN = f"{PYTHON_PREFIX}/bin/python3.11"
PYTHON_SOURCE_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"Python-{PYTHON_VERSION}.tar.xz"
)
CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
DEVICE_RE = re.compile(r"/dev/[A-Za-z0-9._/+-]+\Z")


class BootstrapError(RuntimeError):
    """A controlled, receipt-safe host bootstrap failure."""


@dataclass(frozen=True, slots=True)
class LocalRelease:
    branch: str
    head: str


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _controlled_remote_failure(stage: str, result: Any) -> BootstrapError:
    detail = (result.stderr or result.stdout or "").strip()
    if len(detail) > 2_000:
        detail = detail[-2_000:]
    return BootstrapError(
        f"{stage} failed with return code {result.returncode}"
        + (f": {detail}" if detail else "")
    )


def _run_remote_stage(
    receipt: dict[str, Any],
    config: Any,
    runner: Any,
    name: str,
    script: str,
) -> dict[str, str]:
    stage = {"name": name, "started_at": bridge.utc_now(), "status": "RUNNING"}
    receipt["stages"].append(stage)
    result = bridge.run_ssh_stdin(config, script, runner)
    stage["finished_at"] = bridge.utc_now()
    stage["return_code"] = result.returncode
    if result.returncode != 0:
        stage["status"] = "FAILED"
        raise _controlled_remote_failure(name, result)
    stage["status"] = "PASS"
    values = _parse_key_values(result.stdout)
    if values:
        stage["result"] = values
    return values


def build_ssh_check_script() -> str:
    return """# sktlm-bootstrap-stage:ssh
set -eu
if [ "$(id -u)" -ne 0 ]; then
  printf 'bootstrap requires the root SSH user\n' >&2
  exit 10
fi
printf 'ssh=PASS\n'
printf 'hostname=%s\n' "$(hostname)"
""".strip()


def build_prerequisites_script() -> str:
    packages = (
        "git rsync build-essential wget xz-utils ca-certificates parted "
        "util-linux e2fsprogs libssl-dev zlib1g-dev libbz2-dev "
        "libreadline-dev libsqlite3-dev libffi-dev liblzma-dev "
        "libncursesw5-dev uuid-dev"
    )
    return f"""# sktlm-bootstrap-stage:prerequisites
set -eu
missing=false
for package in {packages}; do
  if ! dpkg-query -W -f='${{Status}}' "$package" 2>/dev/null | grep -q 'ok installed'; then
    missing=true
    break
  fi
done
if [ "$missing" = false ]; then
  printf 'prerequisites=REUSED\n'
  exit 0
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends {packages}
printf 'prerequisites=READY\n'
""".strip()


def build_disk_script(config: Any, data_device: str | None) -> str:
    if data_device is not None and (
        not DEVICE_RE.fullmatch(data_device)
        or ".." in PurePosixPath(data_device).parts
    ):
        raise BootstrapError("--data-device must be an absolute /dev path")
    device = data_device or ""
    return f"""# sktlm-bootstrap-stage:data_disk
set -eu
mount_path={shlex.quote(config.remote_data_mount)}
cloud={shlex.quote(config.remote_cloud_root)}
device={shlex.quote(device)}

mkdir -p -- "$mount_path"
if findmnt -rn -M "$mount_path" >/dev/null 2>&1; then
  target=$(findmnt -rn -o TARGET -M "$mount_path")
  source=$(findmnt -rn -o SOURCE -M "$mount_path")
  if [ "$target" = "/" ] || [ "$(readlink -f "$target")" != "$(readlink -f "$mount_path")" ]; then
    printf 'configured data mount is not an exact non-root mount\n' >&2
    exit 20
  fi
  mkdir -p -- "$cloud"
  printf 'data_disk=REUSED\n'
  printf 'data_source=%s\n' "$source"
  printf 'data_mount=%s\n' "$target"
  exit 0
fi

if [ -z "$device" ]; then
  printf 'data mount is absent and --data-device was not supplied\n' >&2
  exit 21
fi
if [ ! -b "$device" ]; then
  printf 'data device is not a block device: %s\n' "$device" >&2
  exit 22
fi
device=$(readlink -f "$device")
if [ "$(lsblk -dnro TYPE "$device")" != "disk" ]; then
  printf 'data device is not a whole disk\n' >&2
  exit 23
fi
root_source=$(readlink -f "$(findmnt -rn -o SOURCE /)")
if lsblk -nrpo NAME "$device" | grep -Fx -- "$root_source" >/dev/null; then
  printf 'refusing root/system backing device\n' >&2
  exit 24
fi

partition_count=$(lsblk -nrpo TYPE "$device" | awk '$1 == "part" {{n++}} END {{print n+0}}')
disk_signature=$(blkid -p -o value -s TYPE "$device" 2>/dev/null || true)
mounted_count=$(lsblk -nrpo MOUNTPOINT "$device" | awk 'NF {{n++}} END {{print n+0}}')
if [ "$mounted_count" -ne 0 ]; then
  printf 'unexpected mounted filesystem exists on data device\n' >&2
  exit 25
fi
if [ -n "$disk_signature" ]; then
  printf 'unexpected filesystem signature exists on whole data device\n' >&2
  exit 26
fi

partition=""
if [ "$partition_count" -eq 0 ]; then
  parted -s -- "$device" mklabel gpt
  parted -s -- "$device" mkpart primary ext4 1MiB 100%
  parted -s -- "$device" name 1 sktlm-data-bootstrap
  partprobe "$device"
  udevadm settle 2>/dev/null || true
elif [ "$partition_count" -eq 1 ]; then
  partition=$(lsblk -nrpo NAME,TYPE "$device" | awk '$2 == "part" {{print $1}}')
  part_name=$(lsblk -dnro PARTLABEL "$partition" 2>/dev/null || true)
  part_label=$(blkid -o value -s LABEL "$partition" 2>/dev/null || true)
  part_type=$(blkid -o value -s TYPE "$partition" 2>/dev/null || true)
  if ! {{ [ "$part_name" = "sktlm-data-bootstrap" ] && [ -z "$part_type" ]; }} &&
     ! {{ [ "$part_label" = "sktlm-data" ] && [ "$part_type" = "ext4" ]; }}; then
    printf 'unexpected existing partition/signature on data device\n' >&2
    exit 27
  fi
else
  printf 'unexpected existing partitions on data device\n' >&2
  exit 28
fi

if [ -z "$partition" ]; then
  partition=$(lsblk -nrpo NAME,TYPE "$device" | awk '$2 == "part" {{print $1}}')
fi
if [ -z "$partition" ] || [ "$(printf '%s\n' "$partition" | wc -l)" -ne 1 ]; then
  printf 'bootstrap partition was not uniquely created\n' >&2
  exit 29
fi
part_type=$(blkid -o value -s TYPE "$partition" 2>/dev/null || true)
part_label=$(blkid -o value -s LABEL "$partition" 2>/dev/null || true)
if [ -z "$part_type" ]; then
  mkfs.ext4 -L sktlm-data "$partition"
elif [ "$part_type" != "ext4" ] || [ "$part_label" != "sktlm-data" ]; then
  printf 'bootstrap partition has an unexpected filesystem\n' >&2
  exit 30
fi

uuid=$(blkid -o value -s UUID "$partition")
existing=$(awk -v target="$mount_path" '$2 == target {{print $1}}' /etc/fstab)
if [ -n "$existing" ] && [ "$existing" != "UUID=$uuid" ]; then
  printf 'fstab already assigns the configured mount to another source\n' >&2
  exit 31
fi
if [ -z "$existing" ]; then
  printf 'UUID=%s %s ext4 defaults,nofail 0 2\n' "$uuid" "$mount_path" >> /etc/fstab
fi
mount -a
target=$(findmnt -rn -o TARGET -M "$mount_path")
source=$(findmnt -rn -o SOURCE -M "$mount_path")
if [ "$target" = "/" ] || [ "$(readlink -f "$target")" != "$(readlink -f "$mount_path")" ]; then
  printf 'initialized filesystem did not mount at configured target\n' >&2
  exit 32
fi
mkdir -p -- "$cloud"
printf 'data_disk=INITIALIZED\n'
printf 'data_source=%s\n' "$source"
printf 'data_mount=%s\n' "$target"
""".strip()


def build_python_script() -> str:
    return f"""# sktlm-bootstrap-stage:python
set -eu
python_bin={shlex.quote(PYTHON_BIN)}
expected={shlex.quote(PYTHON_VERSION)}
if [ -x "$python_bin" ]; then
  actual=$("$python_bin" -c 'import platform; print(platform.python_version())')
  if [ "$actual" != "$expected" ]; then
    printf 'existing production Python has wrong version: %s\n' "$actual" >&2
    exit 40
  fi
  "$python_bin" -c 'import _posixsubprocess, subprocess'
  printf 'python=REUSED\n'
  printf 'python_version=%s\n' "$actual"
  exit 0
fi

build_dir=$(mktemp -d /tmp/sktlm-python-{PYTHON_VERSION}.XXXXXX)
cleanup() {{
  case "$build_dir" in /tmp/sktlm-python-{PYTHON_VERSION}.*) rm -rf -- "$build_dir";; esac
}}
trap cleanup EXIT HUP INT TERM
cd "$build_dir"
wget -q --https-only -- {shlex.quote(PYTHON_SOURCE_URL)}
tar -xf Python-{PYTHON_VERSION}.tar.xz
cd Python-{PYTHON_VERSION}
./configure --prefix={shlex.quote(PYTHON_PREFIX)} --with-ensurepip=install
make -j "$(nproc)"
make install
actual=$("$python_bin" -c 'import platform; print(platform.python_version())')
if [ "$actual" != "$expected" ]; then
  printf 'installed production Python has wrong version: %s\n' "$actual" >&2
  exit 41
fi
"$python_bin" -c 'import _posixsubprocess, subprocess'
printf 'python=INSTALLED\n'
printf 'python_version=%s\n' "$actual"
""".strip()


def build_layout_script(config: Any) -> str:
    repo = config.remote_repo
    cloud = config.remote_cloud_root
    links = (
        (posixpath.join(cloud, "artifacts"), posixpath.join(repo, "artifacts")),
        (
            posixpath.join(cloud, "data/canonical"),
            posixpath.join(repo, "data/canonical"),
        ),
        (
            posixpath.join(cloud, "data/representations"),
            posixpath.join(repo, "data/representations"),
        ),
        (posixpath.join(cloud, "venv-py311"), posixpath.join(repo, ".venv")),
    )
    link_commands = []
    for target, link in links:
        link_commands.append(
            f"ensure_link {shlex.quote(target)} {shlex.quote(link)}"
        )
    return f"""# sktlm-bootstrap-stage:layout
set -eu
mount_path={shlex.quote(config.remote_data_mount)}
cloud={shlex.quote(cloud)}
repo={shlex.quote(repo)}
target=$(findmnt -rn -o TARGET -M "$mount_path" 2>/dev/null || true)
if [ -z "$target" ] || [ "$target" = "/" ] || [ "$(readlink -f "$target")" != "$(readlink -f "$mount_path")" ]; then
  printf 'configured cloud root is not backed by its own data mount\n' >&2
  exit 50
fi
mkdir -p -- "$cloud" "$cloud/pip-cache" "$(dirname "$repo")"

ensure_link() {{
  target_path=$1
  link_path=$2
  mkdir -p -- "$target_path" "$(dirname "$link_path")"
  if [ -L "$link_path" ]; then
    if [ "$(readlink -f "$link_path")" != "$(readlink -f "$target_path")" ]; then
      printf 'existing symlink points elsewhere: %s\n' "$link_path" >&2
      exit 51
    fi
  elif [ -e "$link_path" ]; then
    printf 'refusing to replace conflicting path: %s\n' "$link_path" >&2
    exit 52
  else
    ln -s -- "$target_path" "$link_path"
  fi
}}
{os.linesep.join(link_commands)}
printf 'layout=READY\n'
""".strip()


def build_repo_probe_script(config: Any) -> str:
    return f"""# sktlm-bootstrap-stage:repo_probe
set -eu
repo={shlex.quote(config.remote_repo)}
if [ ! -e "$repo" ]; then
  printf 'repo_state=MISSING\n'
elif [ ! -d "$repo/.git" ]; then
  printf 'repo_state=CONFLICT\n'
elif [ -n "$(git -C "$repo" status --porcelain)" ]; then
  printf 'repo_state=DIRTY\n'
else
  printf 'repo_state=CLEAN\n'
  printf 'repo_head=%s\n' "$(git -C "$repo" rev-parse HEAD)"
fi
""".strip()


def build_dependencies_script(config: Any, expected_head: str) -> str:
    repo = config.remote_repo
    cloud = config.remote_cloud_root
    venv = posixpath.join(cloud, "venv-py311")
    marker = posixpath.join(cloud, "bootstrap-project-install.txt")
    return f"""# sktlm-bootstrap-stage:dependencies
set -eu
repo={shlex.quote(repo)}
venv={shlex.quote(venv)}
marker={shlex.quote(marker)}
expected_head={shlex.quote(expected_head)}
python_bin={shlex.quote(PYTHON_BIN)}
if [ "$(git -C "$repo" rev-parse HEAD)" != "$expected_head" ]; then
  printf 'dependency install repo HEAD mismatch\n' >&2
  exit 60
fi
if [ ! -x "$venv/bin/python" ]; then
  if [ ! -d "$venv" ] || [ -n "$(find "$venv" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    printf 'existing venv path is invalid\n' >&2
    exit 61
  fi
  "$python_bin" -m venv "$venv"
fi
base=$("$venv/bin/python" -c 'import os,sys; print(os.path.realpath(sys._base_executable))')
if [ "$base" != "$(readlink -f "$python_bin")" ]; then
  printf 'venv uses an unexpected base interpreter: %s\n' "$base" >&2
  exit 62
fi
pyproject_sha=$(sha256sum "$repo/pyproject.toml" | awk '{{print $1}}')
wanted=$(printf 'head=%s\npyproject_sha256=%s\npython=%s\n' "$expected_head" "$pyproject_sha" {shlex.quote(PYTHON_VERSION)})
if [ -f "$marker" ] && [ "$(cat "$marker")" = "$wanted" ] && "$venv/bin/python" -m pip check >/dev/null 2>&1; then
  printf 'dependencies=REUSED\n'
  exit 0
fi
export PIP_CACHE_DIR={shlex.quote(posixpath.join(cloud, 'pip-cache'))}
"$venv/bin/python" -m pip install --upgrade pip
"$venv/bin/python" -m pip install torch --index-url {shlex.quote(CPU_TORCH_INDEX)}
"$venv/bin/python" -m pip install -e "$repo[test]"
"$venv/bin/python" -m pip check
printf '%s' "$wanted" > "$marker.tmp"
mv -- "$marker.tmp" "$marker"
printf 'dependencies=INSTALLED\n'
""".strip()


def build_final_validation_script(config: Any, expected_head: str) -> str:
    repo = config.remote_repo
    cloud = config.remote_cloud_root
    return f"""# sktlm-bootstrap-stage:final_validation
set -eu
repo={shlex.quote(repo)}
cloud={shlex.quote(cloud)}
expected={shlex.quote(expected_head)}
actual=$(git -C "$repo" rev-parse HEAD)
if [ "$actual" != "$expected" ]; then exit 70; fi
if [ -n "$(git -C "$repo" status --porcelain)" ]; then exit 71; fi
version=$({shlex.quote(PYTHON_BIN)} -c 'import platform; print(platform.python_version())')
if [ "$version" != {shlex.quote(PYTHON_VERSION)} ]; then exit 72; fi
if [ ! -x "$repo/.venv/bin/python" ]; then exit 73; fi
for path in artifacts data/canonical data/representations .venv; do
  if [ ! -L "$repo/$path" ]; then exit 74; fi
done
if [ ! -f "$cloud/artifacts/cloud_input_verification.json" ]; then exit 75; fi
if ! grep -Eq '"valid"[[:space:]]*:[[:space:]]*true' "$cloud/artifacts/cloud_input_verification.json"; then exit 76; fi
printf 'status=READY\n'
printf 'repo_head=%s\n' "$actual"
printf 'python_version=%s\n' "$version"
printf 'venv=READY\n'
printf 'inputs=PASS\n'
""".strip()


def _bootstrap_contract(config: Any) -> ExperimentContract:
    machine = config.machine_id or config.host_profile or "host"
    return ExperimentContract(
        contract_id=f"bootstrap-{machine}",
        branch=bridge.require_branch(config),
        deployment=Deployment(mode="git_bundle", require_published_head=True),
        input_sets=(),
        remote_run_root="artifacts",
        optional_metrics_root=None,
        audit_argv=("true",),
        audit_inventory_key="scientific_artifacts",
        profiles={"report": None, "scientific": None, "full": None},
        required_audited_files=(),
        local_collection_root="artifacts/cloud_collected",
        completion_schema="bootstrap-only",
        host_registry=None,
        host_assignments=(),
    )


def validate_local_release(repo_root: Path, config: Any, runner: Any) -> LocalRelease:
    bridge.require_tool("git")
    local = bridge.local_git_status(repo_root, runner)
    branch = bridge.require_branch(config)
    if not local.get("available") or local.get("dirty"):
        raise BootstrapError("bootstrap requires a clean local Git checkout")
    if local.get("branch") != branch:
        raise BootstrapError(
            f"local branch {local.get('branch')!r} does not match {branch!r}"
        )
    head = str(local.get("head"))
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise BootstrapError("local HEAD is not a full SHA-1")
    published = runner.run(
        ["git", "ls-remote", "--heads", config.repository_url, f"refs/heads/{branch}"],
        cwd=repo_root,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    if published.returncode != 0:
        raise BootstrapError("could not verify the published branch HEAD")
    if bridge._parse_ls_remote_head(published.stdout, branch) != head:
        raise BootstrapError("local HEAD does not equal the published branch HEAD")
    return LocalRelease(branch=branch, head=head)


def _deploy_exact_head(
    receipt: dict[str, Any],
    repo_root: Path,
    config: Any,
    runner: Any,
    release: LocalRelease,
) -> None:
    probe = _run_remote_stage(
        receipt, config, runner, "repo_probe", build_repo_probe_script(config)
    )
    state = probe.get("repo_state")
    if state == "CLEAN" and probe.get("repo_head") == release.head:
        receipt["stages"].append(
            {"name": "deploy", "status": "REUSED", "head": release.head}
        )
        receipt["deployment_receipt"] = None
        return
    if state in {"CONFLICT", "DIRTY"}:
        receipt["stages"].append(
            {"name": "deploy", "status": "FAILED", "repo_state": state}
        )
        raise BootstrapError(f"remote repository is not safely deployable: {state}")
    deploy_stage: dict[str, Any] = {
        "name": "deploy",
        "status": "RUNNING",
        "started_at": bridge.utc_now(),
    }
    receipt["stages"].append(deploy_stage)
    artifact_root = repo_root / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="bootstrap-bundle-", dir=artifact_root
    ) as temporary:
        bundle_path = Path(temporary) / f"{release.head}.bundle"
        created = runner.run(
            [
                "git",
                "bundle",
                "create",
                str(bundle_path),
                f"refs/heads/{release.branch}",
            ],
            cwd=repo_root,
        )
        if created.returncode != 0:
            deploy_stage["status"] = "FAILED"
            deploy_stage["finished_at"] = bridge.utc_now()
            raise BootstrapError("failed to create exact-HEAD Git bundle")
        contract = _bootstrap_contract(config)
        deployed, path, error = bridge.execute_receipted(
            "bootstrap-deploy-code",
            "local_to_remote",
            repo_root,
            config,
            runner,
            lambda subreceipt: bridge.deploy_bundle_action(
                subreceipt,
                config,
                contract,
                repo_root,
                runner,
                bundle_path=bundle_path,
                expected_bundle_sha256=bridge.file_sha256(bundle_path),
            ),
            contract,
        )
        receipt["deployment_receipt"] = str(path.relative_to(repo_root))
        if error is not None or deployed.get("valid") is not True:
            deploy_stage["status"] = "FAILED"
            deploy_stage["finished_at"] = bridge.utc_now()
            raise BootstrapError("exact-HEAD bundle deployment failed")
        deploy_stage.update(
            status="PASS", head=release.head, finished_at=bridge.utc_now()
        )


def _push_inputs(
    receipt: dict[str, Any],
    repo_root: Path,
    config: Any,
    runner: Any,
) -> None:
    input_stage: dict[str, Any] = {
        "name": "inputs",
        "status": "RUNNING",
        "started_at": bridge.utc_now(),
    }
    receipt["stages"].append(input_stage)
    pushed, path, error = bridge.execute_receipted(
        "bootstrap-push-inputs",
        "local_to_remote",
        repo_root,
        config,
        runner,
        lambda subreceipt: bridge.push_inputs_action(
            subreceipt,
            config,
            repo_root,
            runner,
            verify_after=True,
        ),
    )
    receipt["input_receipt"] = str(path.relative_to(repo_root))
    if error is not None or pushed.get("valid") is not True:
        input_stage["status"] = "FAILED"
        input_stage["finished_at"] = bridge.utc_now()
        raise BootstrapError("frozen input transfer/validation failed")
    validation = pushed.get("remote_input_validation")
    if not isinstance(validation, Mapping) or validation.get("valid") is not True:
        input_stage["status"] = "FAILED"
        input_stage["finished_at"] = bridge.utc_now()
        raise BootstrapError("remote authoritative input validation is missing")
    input_stage["status"] = "PASS"
    input_stage["finished_at"] = bridge.utc_now()
    validation_text = json.dumps(
        validation, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    verification_path = posixpath.join(
        config.remote_cloud_root, "artifacts/cloud_input_verification.json"
    )
    persist_script = f"""# sktlm-bootstrap-stage:input_receipt
set -eu
path={shlex.quote(verification_path)}
mkdir -p -- "$(dirname "$path")"
printf '%s' {shlex.quote(validation_text)} > "$path.tmp"
mv -- "$path.tmp" "$path"
printf 'input_receipt=READY\n'
""".strip()
    _run_remote_stage(
        receipt, config, runner, "input_receipt", persist_script
    )


def bootstrap_host(
    *,
    repo_root: Path,
    config: Any,
    data_device: str | None,
    dry_run: bool,
    runner: Any,
) -> dict[str, Any]:
    bridge.require_remote_config(config)
    release = validate_local_release(repo_root, config, runner)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "operation": "bootstrap-cloud-host",
        "started_at": bridge.utc_now(),
        "finished_at": None,
        "host_profile": config.host_profile,
        "machine_id": config.machine_id,
        "host_role": config.host_role,
        "branch": release.branch,
        "exact_head": release.head,
        "data_device": data_device,
        "data_mount": config.remote_data_mount,
        "remote_repo": config.remote_repo,
        "remote_cloud_root": config.remote_cloud_root,
        "python_version": PYTHON_VERSION,
        "stages": [],
        "status": "PLANNED" if dry_run else "RUNNING",
    }
    if dry_run:
        receipt["stages"] = [
            {"name": name, "status": "PLANNED"}
            for name in (
                "ssh",
                "prerequisites",
                "data_disk",
                "python",
                "repo_probe",
                "deploy",
                "layout",
                "dependencies",
                "inputs",
                "input_receipt",
                "final_validation",
            )
        ]
        receipt["finished_at"] = bridge.utc_now()
        return receipt

    bridge.require_transfer_platform()
    for tool in ("git", "ssh", "scp", "rsync"):
        bridge.require_tool(tool)
    try:
        _run_remote_stage(receipt, config, runner, "ssh", build_ssh_check_script())
        _run_remote_stage(
            receipt, config, runner, "prerequisites", build_prerequisites_script()
        )
        _run_remote_stage(
            receipt,
            config,
            runner,
            "data_disk",
            build_disk_script(config, data_device),
        )
        _run_remote_stage(
            receipt, config, runner, "python", build_python_script()
        )
        _deploy_exact_head(receipt, repo_root, config, runner, release)
        _run_remote_stage(
            receipt, config, runner, "layout", build_layout_script(config)
        )
        _run_remote_stage(
            receipt,
            config,
            runner,
            "dependencies",
            build_dependencies_script(config, release.head),
        )
        _push_inputs(receipt, repo_root, config, runner)
        final = _run_remote_stage(
            receipt,
            config,
            runner,
            "final_validation",
            build_final_validation_script(config, release.head),
        )
        if final.get("status") != "READY":
            raise BootstrapError("remote final validation did not report READY")
        receipt["status"] = "READY"
    except BootstrapError as exc:
        receipt["status"] = "FAILED"
        receipt["failed_stage"] = next(
            (
                stage["name"]
                for stage in reversed(receipt["stages"])
                if stage["status"] == "FAILED"
            ),
            "orchestration",
        )
        receipt["failure"] = str(exc)
    finally:
        receipt["finished_at"] = bridge.utc_now()
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare one configured VM for later sktlm workloads"
    )
    parser.add_argument("--config", type=Path, default=Path(".sktlm-bridge.toml"))
    parser.add_argument("--host-profile", required=True)
    parser.add_argument("--data-device")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _print_summary(receipt: Mapping[str, Any], receipt_path: Path) -> None:
    results = {
        stage["name"]: stage.get("result", {}) for stage in receipt["stages"]
    }
    print(f"HOST_PROFILE={receipt.get('host_profile')}")
    print(f"SSH={results.get('ssh', {}).get('ssh', 'PLANNED')}")
    print(
        "DATA_DISK="
        + results.get("data_disk", {}).get(
            "data_disk", "PLANNED" if receipt.get("status") == "PLANNED" else "UNKNOWN"
        )
    )
    print(f"PYTHON={results.get('python', {}).get('python_version', PYTHON_VERSION)}")
    print(f"REPO_HEAD={receipt.get('exact_head')}")
    print(f"VENV={results.get('final_validation', {}).get('venv', 'PLANNED')}")
    print(f"INPUTS={results.get('final_validation', {}).get('inputs', 'PLANNED')}")
    print(
        "REMOTE_VALIDATION="
        + ("PASS" if receipt.get("status") == "READY" else str(receipt.get("status")))
    )
    print(f"STATUS={receipt.get('status')}")
    if receipt.get("failed_stage"):
        print(f"FAILED_STAGE={receipt['failed_stage']}")
    print(f"RECEIPT={receipt_path}")


def main(argv: Sequence[str] | None = None, *, runner: Any | None = None) -> int:
    args = build_parser().parse_args(argv)
    active_runner = runner or bridge.SystemRunner()
    repo_root = bridge.discover_repo_root(active_runner)
    config_path = args.config
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = bridge.load_config(
        config_path,
        explicit=True,
        host_profile=args.host_profile,
    )
    receipt: dict[str, Any] | None = None
    error: Exception | None = None
    try:
        receipt = bootstrap_host(
            repo_root=repo_root,
            config=config,
            data_device=args.data_device,
            dry_run=args.dry_run,
            runner=active_runner,
        )
    except (BootstrapError, bridge.BridgeError, OSError) as exc:
        error = exc
        if receipt is None:
            receipt = {
                "schema": SCHEMA,
                "operation": "bootstrap-cloud-host",
                "started_at": bridge.utc_now(),
                "finished_at": bridge.utc_now(),
                "host_profile": args.host_profile,
                "machine_id": config.machine_id,
                "branch": config.branch,
                "exact_head": None,
                "data_device": args.data_device,
                "data_mount": config.remote_data_mount,
                "stages": [],
                "status": "FAILED",
                "failed_stage": "preflight",
                "failure": str(exc),
            }
    assert receipt is not None
    receipt_path = bridge.write_receipt(
        repo_root,
        receipt,
        sensitive_values=bridge.config_sensitive_values(config),
    )
    _print_summary(receipt, receipt_path)
    if error is not None or receipt.get("status") == "FAILED":
        print(str(error or receipt.get("failure", "bootstrap failed")), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
