#!/usr/bin/env bash
# Vira installer for Linux servers (Ubuntu / Debian …): Docker, the code, a .env, then the bot.
#
#   curl -fsSL https://raw.githubusercontent.com/Rushqp/vira-assistant/main/install.sh | bash
#
# Running it again updates the code and restarts the bot; your .env and data are kept.
# Every question can be answered in advance with an environment variable of the same name
# (BOT_TOKEN, OWNER_ID, GEMINI_API_KEY, GROQ_API_KEY, PROFILE, TELEGRAM_PROXY, API_PROXY,
# REGISTRY_MIRROR, PIP_INDEX_URL), e.g. for an unattended install. Guide: docs/INSTALL.md
set -euo pipefail

REPO="${VIRA_REPO:-https://github.com/Rushqp/vira-assistant.git}"
DIR="${VIRA_DIR:-$HOME/vira-assistant}"
BRANCH="${VIRA_BRANCH:-main}"
DRY_RUN="${VIRA_DRY_RUN:-}" # set to 1 to stop before Docker is installed or started (tests)

say() { printf '\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
die() {
    printf '\033[1;31m%s\033[0m\n' "$*" >&2
    exit 1
}

# ask VAR "question" [default]: keeps a value given in the environment, else asks.
ask() {
    local var=$1 question=$2 default=${3:-} answer=""
    if [ -n "${!var:-}" ]; then return; fi
    if [ -n "$default" ]; then question="$question [$default]"; fi
    if [ -r /dev/tty ]; then
        read -r -p "$question: " answer </dev/tty || true
    fi
    printf -v "$var" '%s' "${answer:-$default}"
}

# set_env KEY VALUE: writes KEY=VALUE into .env (replacing the example's line).
set_env() {
    local key=$1 value=$2 escaped
    escaped=${value//\\/\\\\}
    escaped=${escaped//|/\\|}
    escaped=${escaped//&/\\&}
    if grep -q "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${escaped}|" .env
    else
        printf '%s=%s\n' "$key" "$value" >>.env
    fi
}

suggest_profile() {
    local ram_mb
    ram_mb=$(awk '/MemTotal/ { print int($2 / 1024) }' /proc/meminfo 2>/dev/null || echo 4096)
    if [ "$ram_mb" -ge 7500 ]; then echo full
    elif [ "$ram_mb" -ge 3500 ]; then echo standard
    elif [ "$ram_mb" -ge 1800 ]; then echo lite
    else echo remote
    fi
}

install_docker() {
    say "Installing Docker…"
    if curl -fsSL https://get.docker.com | $SUDO sh; then return 0; fi
    # download.docker.com refuses some countries (e.g. Iran): the distribution's packages instead
    warn "The official Docker installer failed; trying the distribution's packages…"
    command -v apt-get >/dev/null || return 1
    $SUDO rm -f /etc/apt/sources.list.d/docker.list
    $SUDO apt-get update -qq || true
    $SUDO apt-get install -y -qq docker.io || return 1
    $SUDO apt-get install -y -qq docker-compose-v2 || $SUDO apt-get install -y -qq docker-compose || true
    $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
}

[ "$(uname -s)" = Linux ] || die "This installer is for Linux servers (Ubuntu, Debian …)."
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

# --- 1. Tools: git ---
if ! command -v git >/dev/null; then
    command -v apt-get >/dev/null || die "Please install git first."
    say "Installing git…"
    $SUDO apt-get update -qq && $SUDO apt-get install -y -qq git
fi

# --- 2. The code ---
if [ -d "$DIR/.git" ]; then
    say "Updating the code in $DIR…"
    git -C "$DIR" fetch -q origin
    git -C "$DIR" checkout -q "$BRANCH"
    git -C "$DIR" pull -q --ff-only
else
    say "Downloading Vira into $DIR…"
    git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

# --- 3. Settings (.env), only on the first install ---
FIRST_INSTALL=""
if [ -f .env ]; then
    say "Keeping your existing settings (.env)."
else
    FIRST_INSTALL=1
    SUGGESTED=$(suggest_profile)
    say "Setting up (the answers go into $DIR/.env; you can edit it later)."
    ask BOT_TOKEN "Bot token from @BotFather"
    ask OWNER_ID "Your numeric Telegram ID (from @userinfobot)"
    ask GEMINI_API_KEY "Free Gemini API key (aistudio.google.com/apikey) — Enter to skip"
    ask GROQ_API_KEY "Free Groq API key, also for voice messages (console.groq.com/keys) — Enter to skip"
    ask PROFILE "Hardware profile: lite (2 GB), standard (4 GB), full (8 GB+), remote (API only)" "$SUGGESTED"
    ask TELEGRAM_PROXY "Proxy for Telegram, only if Telegram is blocked here (socks5://host:port) — Enter to skip"
    ask API_PROXY "Proxy for the AI services, only if they are blocked here — Enter to skip"
    ask PIP_INDEX_URL "PyPI mirror for building, only if pypi.org is blocked — Enter to skip"

    [ -n "${BOT_TOKEN:-}" ] || die "The bot token is required."
    [[ "${OWNER_ID:-}" =~ ^[0-9]+$ ]] || die "Your Telegram ID must be a number."
    case "$PROFILE" in lite | standard | full | remote) ;; *) die "Unknown profile '$PROFILE'." ;; esac
    if [ "$PROFILE" = remote ] && [ -z "${GEMINI_API_KEY:-}${GROQ_API_KEY:-}" ]; then
        die "The remote profile needs at least one API key (Gemini or Groq)."
    fi

    cp .env.example .env
    chmod 600 .env
    set_env BOT_TOKEN "$BOT_TOKEN"
    set_env OWNER_ID "$OWNER_ID"
    set_env PROFILE "$PROFILE"
    set_env GEMINI_API_KEY "${GEMINI_API_KEY:-}"
    set_env GROQ_API_KEY "${GROQ_API_KEY:-}"
    set_env TELEGRAM_PROXY "${TELEGRAM_PROXY:-}"
    set_env API_PROXY "${API_PROXY:-}"
    set_env PIP_INDEX_URL "${PIP_INDEX_URL:-}"
    if [ "$PROFILE" = remote ]; then set_env COMPOSE_PROFILES ""; else set_env COMPOSE_PROFILES ollama; fi
    say "Settings saved to .env."
fi

if [ -n "$DRY_RUN" ]; then
    say "Dry run: stopping before Docker."
    exit 0
fi

# --- 4. Docker ---
if ! command -v docker >/dev/null; then
    install_docker || die "Couldn't install Docker: see docs/INSTALL.md (Docker by hand)."
fi
DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="$SUDO docker"
$DOCKER compose version >/dev/null 2>&1 ||
    die "Docker Compose v2 is missing (the 'docker compose' command): see docs/INSTALL.md."

# A Docker Hub mirror, for servers where Docker Hub is blocked (asked on the first install)
if [ -n "$FIRST_INSTALL" ]; then
    ask REGISTRY_MIRROR "Docker Hub mirror, only if Docker Hub is blocked here (https://…) — Enter to skip"
fi
if [ -n "${REGISTRY_MIRROR:-}" ]; then
    if [ ! -s /etc/docker/daemon.json ]; then
        say "Using the Docker registry mirror $REGISTRY_MIRROR…"
        printf '{\n  "registry-mirrors": ["%s"]\n}\n' "$REGISTRY_MIRROR" | $SUDO tee /etc/docker/daemon.json >/dev/null
        $SUDO systemctl restart docker
    elif ! grep -qF "$REGISTRY_MIRROR" /etc/docker/daemon.json; then
        warn "/etc/docker/daemon.json exists already: add \"registry-mirrors\": [\"$REGISTRY_MIRROR\"] to it, then: sudo systemctl restart docker"
    fi
fi

# --- 5. Start ---
say "Building and starting Vira (the first time takes a few minutes)…"
$DOCKER compose up -d --build

cat <<EOF

Vira is running. Open your bot in Telegram and send /start (then /status).

  Logs:      cd $DIR && $DOCKER compose logs -f bot
  Settings:  $DIR/.env (then: $DOCKER compose up -d)
  Update:    run this installer again, or: cd $DIR && git pull && $DOCKER compose up -d --build
EOF
