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
        standard) MODEL="qwen3:4b" ;;
        full) MODEL="qwen3:8b" ;;
        remote) echo "PROFILE=remote: nothing to pull."; exit 0 ;;
        *) echo "Unknown PROFILE '$PROFILE'"; exit 1 ;;
    esac
fi

if ollama list | awk 'NR > 1 { print $1 }' | grep -qx -e "$MODEL" -e "$MODEL:latest"; then
    echo "Model $MODEL is already available."
else
    echo "Pulling $MODEL (first start only, this can take a while)..."
    # A failed download must not keep the bot from starting: it answers with the API models (or
    # in basic mode), and the next `docker compose up -d` tries again (a pull resumes).
    ollama pull "$MODEL" || ollama pull "$MODEL" || {
        echo "Could not download $MODEL: the bot starts without the local model."
        echo "Try again later with 'docker compose up -d' (blocked downloads: API_PROXY, docs/INSTALL.md)."
    }
fi
