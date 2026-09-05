#!/bin/bash

# Frigate Development Environment Setup Script
# This script initializes Docker Compose for development with frontend and backend

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect the container runtime (podman or docker). Sets CONTAINER_CMD,
# COMPOSE_CMD and CONTAINER_LABEL; override with CONTAINER_RUNTIME=podman|docker.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=container-runtime.sh
source "${SCRIPT_DIR}/container-runtime.sh"

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if required commands exist
check_requirements() {
    print_info "Checking requirements..."
    
    # The container runtime and compose provider were already validated when
    # container-runtime.sh was sourced, so nothing to re-check here.
    print_info "Using ${CONTAINER_LABEL} (${CONTAINER_CMD}) with '${COMPOSE_CMD}'"
}

# Function to create necessary directories
create_directories() {
    print_info "Creating necessary directories..."
    
    # Create data directories
    mkdir -p data/frigate-config
    mkdir -p data/frigate-storage
    mkdir -p debug/media
    
    # Create config directory if it doesn't exist
    mkdir -p config
    
    print_success "Directories created"
}

# Function to check Docker daemon
check_docker_daemon() {
    # container-runtime.sh already probed the engine with `info`, so if we got
    # here it is responding.
    print_success "${CONTAINER_LABEL} is running"
}

# Function to build the development container
build_dev_container() {
    print_info "Building development container..."
    
    $COMPOSE_CMD build devcontainer
    
    print_success "Development container built"
}

# Function to install frontend dependencies
install_frontend_deps() {
    if [ -d "web" ]; then
        print_info "Installing frontend dependencies inside container..."

        # Check if container is running
        if compose_service_running devcontainer; then
            $COMPOSE_CMD exec -T devcontainer bash -c "cd /workspace/frigate/web && npm install"
            print_success "Frontend dependencies installed in container"
        else
            print_warning "Container not running. Dependencies will be installed when container starts."
        fi
    else
        print_warning "web directory not found"
    fi
}

# Function to start services
start_services() {
    print_info "Starting Docker Compose services..."
    
    # Start services in detached mode
    $COMPOSE_CMD up -d
    
    print_success "Docker Compose services started"
}

# Function to wait for services to be ready
wait_for_services() {
    print_info "Waiting for services to be ready..."

    # Wait for MQTT
    print_info "Waiting for MQTT service..."
    timeout=30
    while [ $timeout -gt 0 ]; do
        if $COMPOSE_CMD exec -T mqtt mosquitto_pub -h localhost -p 1883 -t test/topic -m "test" 2>/dev/null; then
            break
        fi
        sleep 1
        timeout=$((timeout - 1))
    done

    if [ $timeout -eq 0 ]; then
        print_warning "MQTT service may not be ready yet"
    else
        print_success "MQTT service is ready"
    fi
}

# How long to give s6 to bring a supervised process up before starting it here.
SUPERVISED_START_TIMEOUT=45

# How many processes in the devcontainer match a `pgrep -f` pattern.
count_container_procs() {
    local pattern="$1"
    local count
    count="$($COMPOSE_CMD exec -T devcontainer pgrep -f "${pattern}" 2>/dev/null \
        | tr -d "\r" | grep -c "^[0-9]" || true)"
    echo "${count:-0}"
}

# Wait for an s6-supervised process to appear. Returns 0 once it does, 1 if it
# never shows up within the timeout -- the caller then starts it by hand.
#
# The devcontainer supervises frigate, frigate-extras and vite
# (docker/main/devcontainer_s6/), but s6 needs several seconds after
# `compose up -d` to get to them. A single pgrep check right after the `up`
# answers "not running" and this script starts a *second* copy. Two Frigate
# mains then fight over the MQTT client id -- connect/disconnect once a second
# -- and over the API port, so nginx answers 500 on every /api request and the
# whole stack looks dead. Poll instead of checking once.
wait_for_supervised() {
    local pattern="$1"
    local label="$2"
    local timeout="${3:-$SUPERVISED_START_TIMEOUT}"
    local waited=0

    while [ "$waited" -lt "$timeout" ]; do
        if [ "$(count_container_procs "$pattern")" -gt 0 ]; then
            print_info "${label} already running (started by s6-supervise)"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done

    return 1
}

# Warn if a process we may have started by hand now has a supervised twin.
warn_if_duplicated() {
    local pattern="$1"
    local label="$2"

    if [ "$(count_container_procs "$pattern")" -gt 1 ]; then
        print_warning "More than one ${label} is running in the container."
        print_warning "Duplicates fight over the MQTT client id and the API port;"
        print_warning "expect 500s from /api. Recover with:"
        print_warning "  $COMPOSE_CMD down && $0 --docker-only"
    fi
}

# Function to start Frigate backend service
start_frigate_backend() {
    print_info "Starting Frigate backend service..."

    # Check if container is running
    if compose_service_running devcontainer; then
        # Give s6 a chance to start Frigate before starting a second one here.
        if ! wait_for_supervised "python3.*-m frigate$" "Frigate main process"; then
            print_warning "No supervised Frigate after ${SUPERVISED_START_TIMEOUT}s; starting it by hand"
            compose_exec_detached devcontainer bash -c "cd /workspace/frigate && python3 -m frigate"
        fi

        if ! wait_for_supervised "frigate\.extras\.main" "Frigate-extras"; then
            print_warning "No supervised frigate-extras after ${SUPERVISED_START_TIMEOUT}s; starting it by hand"
            compose_exec_detached devcontainer bash -c "cd /workspace/frigate && python3 -m frigate.extras.main"
        fi

        # Wait for Frigate to start
        print_info "Waiting for Frigate to be ready..."
        sleep 10

        # Check if Frigate is running
        if [ "$(count_container_procs "python3.*-m frigate$")" -gt 0 ]; then
            print_success "Frigate backend service started"
            print_info "API available at http://localhost:5001/api"
        else
            print_warning "Frigate may not have started correctly"
            print_info "Check logs with: $COMPOSE_CMD exec devcontainer cat /dev/shm/logs/frigate/current"
        fi

        warn_if_duplicated "python3.*-m frigate$" "Frigate main process"
        warn_if_duplicated "frigate\.extras\.main" "frigate-extras process"
    else
        print_error "Container is not running"
        return 1
    fi
}

# Function to start frontend development server
start_frontend_dev() {
    if [ -d "web" ]; then
        # Check if container is running
        if compose_service_running devcontainer; then
            print_info "Starting frontend development server inside container..."
            print_info "Frontend will be available at http://localhost:5173"
            print_info "Use Ctrl+C to stop the frontend server"

            $COMPOSE_CMD exec devcontainer bash -c "cd /workspace/frigate/web && npm run dev"
        else
            print_error "Container is not running. Please start it with: $COMPOSE_CMD up -d"
            exit 1
        fi
    else
        print_error "web directory not found"
        exit 1
    fi
}

# Function to show access information
show_access_info() {
    echo
    echo "=============================================="
    print_success "Frigate Development Environment Ready!"
    echo "=============================================="
    echo
    echo "Access URLs:"
    echo "• Frontend (Development): http://localhost:5173"
    # docker-compose.yml publishes the container's port 5000 on host 5001, so
    # the built UI and the API are both served from 5001. Nothing binds host
    # port 5000 -- on macOS it is taken by Control Center's AirPlay Receiver,
    # which answers 403 and used to look like a broken frontend.
    echo "• Frontend (Production):  http://localhost:5001"
    echo "• Backend API:           http://localhost:5001/api"
    echo "• Frontend (Authenticated): https://localhost:8971  (self-signed TLS)"
    echo "• Home Assistant:        http://localhost:8123"
    echo "• MQTT Broker:           localhost:1883"
    echo
    echo "Docker Services:"
    $COMPOSE_CMD ps
    echo
    echo "Configuration:"
    echo "• Main config: ./config/config.yml"
    echo "• Data directory: ./data/"
    echo
    echo "Frontend Development:"
    echo "• The frontend dev server will start automatically if Node.js is installed"
    echo "• For manual frontend development, run:"
    echo "  cd web && npm run dev"
    echo
    echo "To stop the environment:"
    echo "  $COMPOSE_CMD down"
    echo "=============================================="
}

# Function to show help
show_help() {
    echo "Frigate Development Environment Setup"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help          Show this help message"
    echo "  -b, --build         Force build the development container"
    echo "  -f, --frontend-only Start only frontend development server"
    echo "  -d, --docker-only   Start only container services (no frontend)"
    echo "  --no-deps           Skip frontend dependency installation"
    echo
    echo "This script sets up the Frigate development environment with:"
    echo "• Docker Compose services (devcontainer, MQTT, homeassistant)"
    echo "• Frontend development server (if Node.js available)"
    echo "• Proper directory structure"
    echo
    echo "Default behavior: Full development environment"
}

# Parse command line arguments
BUILD_ONLY=false
FRONTEND_ONLY=false
DOCKER_ONLY=false
SKIP_DEPS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -b|--build)
            BUILD_ONLY=true
            shift
            ;;
        -f|--frontend-only)
            FRONTEND_ONLY=true
            shift
            ;;
        -d|--docker-only)
            DOCKER_ONLY=true
            shift
            ;;
        --no-deps)
            SKIP_DEPS=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
echo "=============================================="
print_info "Frigate Development Environment Setup"
echo "=============================================="

# Check requirements
check_requirements

# Check Docker daemon
check_docker_daemon

# Create directories
create_directories

# Install frontend dependencies if not skipped and not frontend-only
if [ "$SKIP_DEPS" = false ] && [ "$FRONTEND_ONLY" = false ]; then
    install_frontend_deps
fi

# Handle different modes
if [ "$FRONTEND_ONLY" = true ]; then
    print_info "Frontend-only mode: Starting development server..."
    install_frontend_deps
    start_frontend_dev
else
    # Build container if requested or if it doesn't exist
    if [ "$BUILD_ONLY" = true ] || ! $CONTAINER_CMD images | grep -q devcontainer; then
        build_dev_container
    fi
    
    # Start services if not docker-only
    if [ "$DOCKER_ONLY" = false ]; then
        start_services
        wait_for_services

        # Generate version.py if it doesn't exist
        if [ ! -f "frigate/version.py" ]; then
            print_info "Generating version.py..."
            make version 2>/dev/null || {
                COMMIT_HASH=$(git log -1 --pretty=format:"%h" 2>/dev/null || echo "dev")
                echo "VERSION = \"0.17.0-${COMMIT_HASH}\"" > frigate/version.py
                print_success "version.py created"
            }
        fi

        # Start Frigate backend service
        start_frigate_backend

        show_access_info

        # Start frontend development server inside the Docker container
        print_info "Starting frontend development server inside container..."
        # Vite is an s6 service on the devcontainer, so it is usually already
        # up. Starting a second one would fight over port 5173. Match on
        # "vite --host" rather than "vite": the bare pattern also matches the
        # `s6-supervise vite` process, which exists even when Vite itself is
        # down.
        if ! wait_for_supervised "vite --host" "Vite" 20; then
            compose_exec_detached devcontainer bash -c "cd /workspace/frigate/web && npm run dev" > /dev/null 2>&1
        fi

        # Wait a moment for the frontend to start
        sleep 5

        # Check if frontend is running
        if $COMPOSE_CMD exec -T devcontainer pgrep -f "vite.*--host" > /dev/null 2>&1; then
            print_success "Frontend development server started inside container"
            print_info "Frontend available at http://localhost:5173"
            print_info "Backend API available at http://localhost:5001/api"

            # Keep the script running and show logs
            echo
            print_info "Press Ctrl+C to stop all services"
            echo

            # Wait for user interrupt
            trap 'print_info "Stopping services..."; $COMPOSE_CMD exec -T devcontainer pkill -f "vite.*--host" 2>/dev/null; $COMPOSE_CMD exec -T devcontainer pkill -f "python3.*frigate" 2>/dev/null; $COMPOSE_CMD down 2>/dev/null; print_success "All services stopped"; exit 0' INT

            # Show logs or keep running
            $COMPOSE_CMD logs -f
        else
            print_warning "Frontend development server may not have started correctly"
            print_info "You can start it manually with: $COMPOSE_CMD exec devcontainer bash -c 'cd /workspace/frigate/web && npm run dev'"
            show_access_info

            # Keep running to show logs
            $COMPOSE_CMD logs -f
        fi
    else
        # Containers-only mode: bring up the services and the backend, but skip
        # the frontend dev server and the blocking log tail.
        start_services
        wait_for_services

        if [ ! -f "frigate/version.py" ]; then
            print_info "Generating version.py..."
            make version 2>/dev/null || {
                COMMIT_HASH=$(git log -1 --pretty=format:"%h" 2>/dev/null || echo "dev")
                echo "VERSION = \"0.17.0-${COMMIT_HASH}\"" > frigate/version.py
                print_success "version.py created"
            }
        fi

        start_frigate_backend
        show_access_info

        print_success "Container services started in background"
        print_info "Use './logs-dev.sh -f' to view logs"
        print_info "Use './stop-dev.sh' to stop services"
    fi
fi