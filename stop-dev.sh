#!/bin/bash

# Frigate Development Environment Stop Script
# This script cleanly shuts down all development services

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

# Function to stop Docker Compose services
stop_docker_services() {
    print_info "Stopping Docker Compose services..."
    
    $COMPOSE_CMD down
    
    print_success "Docker Compose services stopped"
}

# Function to kill frontend development server
kill_frontend_server() {
    print_info "Checking for frontend development server..."

    # The dev server runs INSIDE the devcontainer, so kill it there.
    #
    # Do not kill by host port or by a bare `pkill -f vite` on the host. Host
    # port 5173 is held by the runtime's port-forwarder, not by vite -- under
    # `podman machine` on macOS that is gvproxy, and killing it takes down all
    # podman connectivity, so the `down` below then fails with a traceback. A
    # host-wide `pkill -f "vite"` / `pkill -f "npm.*dev"` is just as wrong: it
    # matches unrelated projects the user happens to have running.
    if compose_service_running devcontainer; then
        if $COMPOSE_CMD exec -T devcontainer pkill -f "vite" > /dev/null 2>&1; then
            print_info "Killed Vite development server in container"
        else
            print_info "No frontend development server running in container"
        fi
    else
        print_info "devcontainer not running; nothing to stop"
    fi
}

# Function to clean up Docker resources
cleanup_docker() {
    print_info "Cleaning up Docker resources..."
    
    # Remove stopped containers
    $CONTAINER_CMD container prune -f
    
    # Remove unused images (optional, comment out if you want to keep them)
    # $CONTAINER_CMD image prune -f
    
    print_success "Docker cleanup completed"
}

# Function to show help
show_help() {
    echo "Frigate Development Environment Stop Script"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help          Show this help message"
    echo "  -c, --cleanup       Clean up Docker resources after stopping"
    echo "  -f, --frontend-only Stop only frontend development server"
    echo "  -d, --docker-only   Stop only container services"
    echo "  --force             Force stop without confirmation"
    echo
    echo "This script stops all Frigate development services cleanly."
}

# Parse command line arguments
CLEANUP=false
FRONTEND_ONLY=false
DOCKER_ONLY=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--cleanup)
            CLEANUP=true
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
        --force)
            FORCE=true
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
print_info "Frigate Development Environment Shutdown"
echo "=============================================="

if [ "$FORCE" = false ]; then
    print_warning "This will stop all Frigate development services."
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Shutdown cancelled."
        exit 0
    fi
fi

# Handle different stop modes
if [ "$FRONTEND_ONLY" = true ]; then
    kill_frontend_server
elif [ "$DOCKER_ONLY" = true ]; then
    stop_docker_services
else
    # Stop everything
    kill_frontend_server
    stop_docker_services
fi

# Clean up Docker resources if requested
if [ "$CLEANUP" = true ]; then
    cleanup_docker
fi

# Show status
echo
print_info "Remaining ${CONTAINER_LABEL} services:"
$COMPOSE_CMD ps

echo
print_success "Shutdown completed!"
echo "=============================================="