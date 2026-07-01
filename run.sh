#!/usr/bin/env bash
#
# run.sh — sobe o projeto inteiro de uma vez.
#
# Faz tudo: MongoDB (docker), virtualenv + dependências, .env, pipeline ETL
# e, por fim, a aplicação de visualização (Flask) em http://127.0.0.1:5000.
#
# Uso:
#   ./run.sh            # setup completo + ETL + sobe a aplicação
#   ./run.sh --no-app   # só prepara tudo e roda o ETL, sem subir a aplicação
#   ./run.sh --reset    # recria o banco do zero (--drop-db no ETL)
#
set -euo pipefail

# Sempre executa a partir da raiz do projeto (onde este script está).
cd "$(dirname "$(readlink -f "$0")")"

VENV_DIR=".venv"
START_APP=1
DROP_DB=""

for arg in "$@"; do
  case "$arg" in
    --no-app) START_APP=0 ;;
    --reset)  DROP_DB="--drop-db" ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '2,12p'
      exit 0
      ;;
    *) echo "Argumento desconhecido: $arg" >&2; exit 1 ;;
  esac
done

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 1. Pré-requisitos
# --------------------------------------------------------------------------- #
log "Verificando pré-requisitos (docker, python3)"
command -v docker  >/dev/null 2>&1 || die "Docker não encontrado. Instale o Docker e tente de novo."
command -v python3 >/dev/null 2>&1 || die "python3 não encontrado."

# docker compose (v2) ou docker-compose (v1)
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "Nem 'docker compose' nem 'docker-compose' disponíveis."
fi

# --------------------------------------------------------------------------- #
# 2. .env
# --------------------------------------------------------------------------- #
if [ ! -f .env ]; then
  log "Criando .env a partir de .env.example"
  cp .env.example .env
else
  log ".env já existe — mantendo"
fi

# --------------------------------------------------------------------------- #
# 3. MongoDB
# --------------------------------------------------------------------------- #
log "Subindo MongoDB (docker compose up -d)"
$COMPOSE up -d

log "Aguardando o MongoDB aceitar conexões (porta 27017)"
for i in $(seq 1 30); do
  if docker exec mptibd_mongodb mongosh --quiet --eval 'db.runCommand({ ping: 1 }).ok' >/dev/null 2>&1; then
    echo "MongoDB pronto."
    break
  fi
  [ "$i" -eq 30 ] && die "MongoDB não respondeu a tempo."
  sleep 1
done

# --------------------------------------------------------------------------- #
# 4. Virtualenv + dependências
# --------------------------------------------------------------------------- #
if [ ! -d "$VENV_DIR" ]; then
  log "Criando virtualenv em $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Instalando dependências (requirements.txt)"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# --------------------------------------------------------------------------- #
# 5. Pipeline ETL (Bronze -> Silver -> Gold -> MongoDB)
# --------------------------------------------------------------------------- #
log "Executando o pipeline ETL${DROP_DB:+ (recriando o banco)}"
python src/main.py $DROP_DB

# --------------------------------------------------------------------------- #
# 6. Aplicação
# --------------------------------------------------------------------------- #
if [ "$START_APP" -eq 1 ]; then
  log "Subindo a aplicação em http://127.0.0.1:5000  (Ctrl+C para encerrar)"
  python src/app.py
else
  log "Setup e ETL concluídos. Para subir a aplicação: source $VENV_DIR/bin/activate && python src/app.py"
fi
