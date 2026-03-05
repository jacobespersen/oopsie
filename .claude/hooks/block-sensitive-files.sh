#!/bin/bash

# PreToolUse hook: block edits to .env and lock files
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# Block .env files (but allow .env.example)
if [[ "$BASENAME" == .env ]] || [[ "$BASENAME" == .env.local ]] || [[ "$BASENAME" == .env.production ]]; then
  echo "Blocked: refusing to edit sensitive file $BASENAME" >&2
  exit 2
fi

# Block lock files
if [[ "$BASENAME" == *.lock ]] || [[ "$BASENAME" == poetry.lock ]] || [[ "$BASENAME" == uv.lock ]]; then
  echo "Blocked: refusing to edit lock file $BASENAME" >&2
  exit 2
fi

exit 0
