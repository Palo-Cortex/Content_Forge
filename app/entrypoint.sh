#!/bin/bash
set -e

mkdir -p /workspace /workspace/ingest /workspace/output

if [ ! -d "/workspace/secops-framework/.git" ]; then
  echo "Cloning secops-framework..."
  git clone https://github.com/Palo-Cortex/secops-framework.git /workspace/secops-framework
else
  echo "secops-framework already present."
fi

exec "$@"