#!/bin/bash
# shellcheck shell=bash
#
# Container runtime detection, shared by run-dev.sh / stop-dev.sh / logs-dev.sh.
#
# Sourced, not executed. Exports:
#   CONTAINER_CMD   podman | docker
#   COMPOSE_CMD     the compose invocation, may contain a space ("podman compose")
#   CONTAINER_LABEL human-readable name for messages
#
# Override detection with:
#   CONTAINER_RUNTIME=podman ./run-dev.sh
#
# Detection probes the *engine*, not just the binary. A machine can have a
# docker-compose binary on PATH with no docker at all -- `docker-compose version`
# still succeeds there, so checking for the binary alone picks a runtime that
# fails on the first real command.

detect_container_runtime() {
    local requested="${CONTAINER_RUNTIME:-}"

    if [[ -n "${requested}" ]]; then
        case "${requested}" in
            podman|docker) ;;
            *)
                echo "[ERROR] CONTAINER_RUNTIME must be 'podman' or 'docker', got '${requested}'" >&2
                return 1
                ;;
        esac
        if ! command -v "${requested}" &> /dev/null; then
            echo "[ERROR] CONTAINER_RUNTIME=${requested} but ${requested} is not installed" >&2
            return 1
        fi
        if ! "${requested}" info &> /dev/null; then
            echo "[ERROR] ${requested} is installed but not responding." >&2
            if [[ "${requested}" == "podman" ]]; then
                echo "[ERROR] Start the VM with: podman machine start" >&2
            else
                echo "[ERROR] Start Docker Desktop, or the docker daemon." >&2
            fi
            return 1
        fi
        CONTAINER_CMD="${requested}"
    elif command -v podman &> /dev/null && podman info &> /dev/null; then
        CONTAINER_CMD="podman"
    elif command -v docker &> /dev/null && docker info &> /dev/null; then
        CONTAINER_CMD="docker"
    else
        echo "[ERROR] No working container runtime found." >&2
        echo "[ERROR] Install podman (brew install podman podman-compose) or Docker." >&2
        if command -v podman &> /dev/null; then
            echo "[ERROR] podman is installed but not responding -- try: podman machine start" >&2
        fi
        if command -v docker &> /dev/null; then
            echo "[ERROR] docker is installed but not responding -- is Docker Desktop running?" >&2
        fi
        return 1
    fi

    if [[ "${CONTAINER_CMD}" == "podman" ]]; then
        CONTAINER_LABEL="Podman"
        if command -v podman-compose &> /dev/null; then
            COMPOSE_CMD="podman-compose"
        elif podman compose version &> /dev/null; then
            COMPOSE_CMD="podman compose"
        else
            echo "[ERROR] podman found but no compose provider." >&2
            echo "[ERROR] Install one with: brew install podman-compose" >&2
            return 1
        fi
    else
        CONTAINER_LABEL="Docker"
        if docker compose version &> /dev/null; then
            COMPOSE_CMD="docker compose"
        elif command -v docker-compose &> /dev/null && docker-compose version &> /dev/null; then
            COMPOSE_CMD="docker-compose"
        else
            echo "[ERROR] docker found but no compose provider (need 'docker compose' or docker-compose)." >&2
            return 1
        fi
    fi

    export CONTAINER_CMD COMPOSE_CMD CONTAINER_LABEL
    return 0
}

# Is a compose service's container running?
#
# `docker compose ps <service>` accepts a service name but `podman-compose ps`
# does not -- it errors with "unrecognized arguments". Query the runtime
# directly instead; `ps --filter name=` does substring matching, so it matches
# whatever prefix the compose provider gave the container
# (project_service_1 vs project-service-1).
compose_service_running() {
    local service="$1"
    [[ -n "$($CONTAINER_CMD ps --filter "name=${service}" --filter "status=running" \
        --format '{{.Names}}' 2>/dev/null)" ]]
}

detect_container_runtime || exit 1
