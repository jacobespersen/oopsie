#!/bin/bash

# PostToolUse hook: auto-format and lint Python files after Edit/Write
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only process Python files
if [[ "$FILE_PATH" == *.py ]]; then
  cd "$CLAUDE_PROJECT_DIR"
  ruff check --fix "$FILE_PATH" 2>/dev/null
  ruff format "$FILE_PATH" 2>/dev/null
fi

exit 0
