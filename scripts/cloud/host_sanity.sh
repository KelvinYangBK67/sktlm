#!/usr/bin/env bash
set -euo pipefail

echo "timestamp_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hostname: $(hostname)"
echo "kernel:"
uname -a
echo "cpu:"
lscpu
echo "memory:"
free -h
echo "block_devices:"
lsblk -e 7 -o NAME,PATH,SIZE,TYPE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
echo "mounted_filesystems:"
df -hT
echo "mount_topology:"
findmnt -D
echo "tool_versions:"
if command -v git >/dev/null 2>&1; then
  git --version
else
  echo "git: MISSING"
fi
if command -v python3.11 >/dev/null 2>&1; then
  python3.11 --version
else
  echo "python3.11: MISSING"
fi
if command -v iostat >/dev/null 2>&1; then
  iostat -V
else
  echo "iostat: MISSING (install sysstat before scaling runs)"
fi
