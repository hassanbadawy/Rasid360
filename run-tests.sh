#!/bin/bash
# shellcheck shell=bash
# Run the Python test suite inside a container.
#
# The tests need Frigate's full dependency stack (opencv, tensorflow, peewee,
# fastapi...), which is impractical to install on a dev machine, so they run in
# a container. Works with podman or docker -- see container-runtime.sh.
#
#   ./run-tests.sh                                  # everything
#   ./run-tests.sh frigate.test.extras.test_dsl_rules
#   ./run-tests.sh frigate.test.http_api.test_http_dashboard

set -o errexit -o nounset -o pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
print_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=container-runtime.sh
source "${SCRIPT_DIR}/container-runtime.sh"

# Prefer a locally built devcontainer image; otherwise use the published one,
# which carries the same dependency stack.
TEST_IMAGE="${TEST_IMAGE:-ghcr.io/blakeblackshear/frigate:stable}"

if ! $CONTAINER_CMD image exists "${TEST_IMAGE}" 2>/dev/null && \
   ! $CONTAINER_CMD image inspect "${TEST_IMAGE}" &> /dev/null; then
    print_info "Pulling ${TEST_IMAGE} (~4.6 GB, first run only)..."
    $CONTAINER_CMD pull "${TEST_IMAGE}"
fi

TARGET="${1:-}"
if [[ -n "${TARGET}" ]]; then
    UNITTEST_ARGS="${TARGET}"
    print_info "Running ${TARGET} via ${CONTAINER_LABEL}..."
else
    UNITTEST_ARGS="discover -s frigate/test -t ."
    print_info "Running the full suite via ${CONTAINER_LABEL}..."
fi

# The published image tracks upstream, whose peewee_migrate is newer than the
# 1.13.* this repo pins. Without the pin every migration-backed test errors with
# "'Migrator' object has no attribute 'change_columns'" -- an environment
# mismatch, not a test failure.
if $CONTAINER_CMD run --rm \
    -v "${SCRIPT_DIR}":/workspace/frigate:z \
    -w /workspace/frigate \
    --entrypoint bash \
    "${TEST_IMAGE}" -c "
        set -o pipefail
        pip install -q --break-system-packages --root-user-action=ignore 'peewee_migrate==1.13.*' 2>/dev/null
        python3 -m unittest ${UNITTEST_ARGS} 2>&1 | grep -vE '^(INFO|WARNING|DEBUG):' 
    "; then
    print_success "Tests passed"
else
    print_error "Tests failed"
    exit 1
fi
