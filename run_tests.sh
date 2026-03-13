#!/usr/bin/env zsh
# =============================================================================
# run_tests.sh — Ejecuta los tests del proyecto bstelegramuser
#
# Uso:
#   zsh run_tests.sh                    → solo tests unitarios (sin credenciales)
#   zsh run_tests.sh --integration      → tests de autenticación con Telegram
#   zsh run_tests.sh --sms-only         → solo el test de envío de código por SMS
#   zsh run_tests.sh --discovery        → tests de get_user_channels y get_channel_username_by_name
#   zsh run_tests.sh --all              → unitarios + integración + discovery
#   zsh run_tests.sh --phone=+34600000000 --integration
#   zsh run_tests.sh --phone=+34600000000 --discovery
#   zsh run_tests.sh --phone=+34600000000 --channel-name="Mi Canal" --discovery
# =============================================================================

set -e

SCRIPT_DIR="${0:A:h}"
VENV="$SCRIPT_DIR/.venv/bin/python"
EXTRA_ARGS=()
RUN_INTEGRATION=false
RUN_ALL=false
RUN_SMS_ONLY=false
RUN_DISCOVERY=false

# --- Parseo de argumentos ---
for arg in "$@"; do
  case $arg in
    --integration)
      RUN_INTEGRATION=true
      ;;
    --all)
      RUN_ALL=true
      ;;
    --sms-only)
      RUN_SMS_ONLY=true
      ;;
    --discovery)
      RUN_DISCOVERY=true
      ;;
    --phone=*)
      EXTRA_ARGS+=("$arg")
      ;;
    --sms)
      EXTRA_ARGS+=("$arg")
      ;;
    --channel-name=*)
      EXTRA_ARGS+=("$arg")
      ;;
    *)
      echo "⚠️  Argumento desconocido: $arg"
      echo "    Uso: $0 [--integration] [--sms-only] [--discovery] [--all] [--phone=+XXXXXXXXXXX] [--sms] [--channel-name=\"Nombre\"]"
      exit 1
      ;;
  esac
done

# --- Comprobación del entorno virtual ---
if [[ ! -x "$VENV" ]]; then
  echo "❌ No se encontró el entorno virtual en .venv/"
  echo "   Créalo con: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  exit 1
fi

echo ""
echo "=============================================="
echo "  bstelegramuser — Test Runner"
echo "=============================================="
echo ""

# --- Tests unitarios ---
run_unit_tests() {
  echo "▶️  Ejecutando tests unitarios..."
  echo ""
  "$VENV" -m pytest tests/test_auth_flow.py -v --tb=short
  echo ""
  echo "✅ Tests unitarios completados."
}

# --- Test de integración (todos) ---
run_integration_test() {
  echo "▶️  Ejecutando tests de integración real con Telegram..."
  echo "   (Se necesita conexión a internet y un código de verificación)"
  echo ""
  "$VENV" -m pytest tests/test_auth_integration.py -v -s -m integration "${EXTRA_ARGS[@]}"
  echo ""
  echo "✅ Tests de integración completados."
}

# --- Test de SMS ---
run_sms_test() {
  echo "▶️  Ejecutando test de envío de código por SMS..."
  echo "   (Se necesita conexión a internet y un teléfono que reciba SMS)"
  echo ""
  "$VENV" -m pytest tests/test_auth_integration.py::test_sms_code_delivery -v -s -m integration "${EXTRA_ARGS[@]}"
  echo ""
  echo "✅ Test SMS completado."
}

# --- Tests de discovery de canales ---
run_discovery_tests() {
  echo "▶️  Ejecutando tests de discovery de canales (get_user_channels / get_channel_username_by_name)..."
  echo "   (Se necesita conexión a internet y credenciales de Telegram)"
  echo ""
  "$VENV" -m pytest tests/test_channel_discovery_integration.py -v -s -m integration "${EXTRA_ARGS[@]}"
  echo ""
  echo "✅ Tests de discovery completados."
}

# --- Lógica de ejecución ---
if $RUN_ALL; then
  run_unit_tests
  echo ""
  run_integration_test
  echo ""
  run_discovery_tests
elif $RUN_SMS_ONLY; then
  run_sms_test
elif $RUN_INTEGRATION; then
  run_integration_test
elif $RUN_DISCOVERY; then
  run_discovery_tests
else
  run_unit_tests
fi

echo ""
echo "=============================================="
echo "  Todos los tests seleccionados han pasado ✅"
echo "=============================================="
echo ""

