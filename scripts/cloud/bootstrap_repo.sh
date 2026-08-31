#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 EXPECTED_HEAD DATA_MOUNT" >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required; install it before repository bootstrap" >&2
  exit 1
fi
if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 is required; install it using the host's approved package source" >&2
  exit 1
fi

expected_head=$1
data_mount_input=$2
branch=exp/m0-core-methods
repo_root=$(git rev-parse --show-toplevel)

if [[ -n $(git -C "$repo_root" status --porcelain) ]]; then
  echo "refusing bootstrap from a dirty working tree: $repo_root" >&2
  exit 1
fi
if [[ ! -d "$data_mount_input" ]]; then
  echo "data mount does not exist: $data_mount_input" >&2
  exit 1
fi
data_mount=$(readlink -f "$data_mount_input")

data_source=$(findmnt -n -o SOURCE -T "$data_mount")
data_target=$(findmnt -n -o TARGET -T "$data_mount")
if [[ -z "$data_source" || "$data_target" == "/" ]]; then
  echo "data mount resolves to the root/system filesystem: $data_source" >&2
  echo "mount the confirmed 300-GB data device before continuing" >&2
  exit 1
fi
if [[ $(readlink -f "$data_target") != "$data_mount" ]]; then
  echo "data path is not itself a mount point: $data_mount" >&2
  echo "resolved filesystem mount point: $data_target" >&2
  exit 1
fi

available_bytes=$(df -PB1 --output=avail "$data_mount" | tail -n 1 | tr -d ' ')
minimum_bytes=$((100 * 1024 * 1024 * 1024))
if (( available_bytes < minimum_bytes )); then
  echo "data mount has less than 100 GiB free: $available_bytes bytes" >&2
  exit 1
fi

git -C "$repo_root" fetch --prune origin \
  "$branch:refs/remotes/origin/$branch"
git -C "$repo_root" switch "$branch"
git -C "$repo_root" merge --ff-only "origin/$branch"
actual_head=$(git -C "$repo_root" rev-parse HEAD)
if [[ "$actual_head" != "$expected_head" ]]; then
  echo "HEAD mismatch: expected $expected_head, found $actual_head" >&2
  exit 1
fi

cloud_root="$data_mount/sktlm"
mkdir -p "$cloud_root"

link_directory() {
  local target=$1
  local link=$2
  mkdir -p "$target"
  if [[ -L "$link" ]]; then
    if [[ $(readlink -f "$link") != $(readlink -f "$target") ]]; then
      echo "existing symlink points elsewhere: $link" >&2
      exit 1
    fi
  elif [[ -e "$link" ]]; then
    echo "refusing to replace existing path: $link" >&2
    exit 1
  else
    ln -s "$target" "$link"
  fi
}

link_directory "$cloud_root/artifacts" "$repo_root/artifacts"
link_directory "$cloud_root/data/canonical" "$repo_root/data/canonical"
link_directory "$cloud_root/data/representations" "$repo_root/data/representations"
link_directory "$cloud_root/venv-py311" "$repo_root/.venv"

python3.11 -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version'
if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
  python3.11 -m venv "$cloud_root/venv-py311"
fi

export PIP_CACHE_DIR="$cloud_root/pip-cache"
mkdir -p "$PIP_CACHE_DIR"
"$repo_root/.venv/bin/python" -m pip install --upgrade pip
"$repo_root/.venv/bin/python" -m pip install -e "${repo_root}[test]"
"$repo_root/.venv/bin/python" -m pip check

echo "bootstrap_complete"
echo "head=$actual_head"
echo "data_source=$data_source"
echo "data_target=$data_target"
echo "data_mount=$data_mount"
echo "available_bytes=$available_bytes"
echo "next: transfer the frozen canonical and representation trees into $cloud_root/data"
