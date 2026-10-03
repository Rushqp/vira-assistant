#!/bin/sh
# Pulls the LLM for the selected PROFILE into the Ollama volume (runs once, then exits).
# Keep the model names in sync with PROFILE_DEFAULTS in app/config.py (a test checks this).
set -e

PROFILE="${PROFILE:-standard}"

if [ -n "$LLM_MODEL" ]; then
    MODEL="$LLM_MODEL"
else
    case "$PROFILE" in
        lite) MODEL="gemma3:1b" ;;
        standard) MODEL="qwen2.5:3b" ;;
        full) MODEL="qwen2.5:7b" ;;
        remote) echo "PROFILE=remote: nothing to pull."; exit 0 ;;
        *) echo "Unknown PROFILE '$PROFILE'"; exit 1 ;;
    esac
fi

if ollama list | awk 'NR > 1 { print $1 }' | grep -qx -e "$MODEL" -e "$MODEL:latest"; then
    echo "Model $MODEL is already available."
else
    echo "Pulling $MODEL (first start only, this can take a while)..."
    ollama pull "$MODEL"
fi
