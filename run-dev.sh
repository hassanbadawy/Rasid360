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
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v node &> /dev/null; then
        print_warning "Node.js is not installed. Frontend development features will be limited."
    fi
    
    print_success "Requirements check passed"
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
    print_info "Checking Docker daemon..."
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        print_info "Please start Docker and try again"
        exit 1
    fi
    
    print_success "Docker daemon is running"
}

# Function to build the development container
build_dev_container() {
    print_info "Building development container..."
    
    # Use docker-compose build or docker compose build
    if docker-compose version &> /dev/null; then
        docker-compose build devcontainer
    else
        docker compose build devcontainer
    fi
    
    print_success "Development container built"
}

# Function to install frontend dependencies
install_frontend_deps() {
    if [ -d "web" ]; then
        print_info "Installing frontend dependencies inside container..."

        # Check if container is running
        if docker compose ps devcontainer | grep -q "Up"; then
            docker compose exec devcontainer bash -c "cd /workspace/frigate/web && npm install"
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
    docker compose up -d
    
    print_success "Docker Compose services started"
}

# Function to wait for services to be ready
wait_for_services() {
    print_info "Waiting for services to be ready..."

    # Wait for MQTT
    print_info "Waiting for MQTT service..."
    timeout=30
    while [ $timeout -gt 0 ]; do
        if docker compose exec -T mqtt mosquitto_pub -h localhost -p 1883 -t test/topic -m "test" 2>/dev/null; then
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

# Function to start Frigate backend service
start_frigate_backend() {
    print_info "Starting Frigate backend service..."

    # Check if container is running
    if docker compose ps devcontainer | grep -q "Up"; then
        # Check if Frigate main process is already running
        if docker compose exec devcontainer pgrep -f "python3.*-m frigate$" > /dev/null 2>&1; then
            print_info "Frigate main process already running (likely started by s6-supervise)"
        else
            # Start Frigate in the background
            docker compose exec -d devcontainer bash -c "cd /workspace/frigate && python3 -m frigate"
        fi

        # Check if frigate-extras is already running
        if docker compose exec devcontainer pgrep -f "frigate.extras.main" > /dev/null 2>&1; then
            print_info "Frigate-extras already running (likely started by s6-supervise)"
        else
            # Start frigate-extras in the background
            docker compose exec -d devcontainer bash -c "cd /workspace/frigate && python3 -m frigate.extras.main"
        fi

        # Wait for Frigate to start
        print_info "Waiting for Frigate to be ready..."
        sleep 10

        # Check if Frigate is running
        if docker compose exec devcontainer pgrep -f "python3.*frigate" > /dev/null 2>&1; then
            print_success "Frigate backend service started"
            print_info "API available at http://localhost:5001/api"
        else
            print_warning "Frigate may not have started correctly"
            print_info "Check logs with: docker compose exec devcontainer cat /dev/shm/logs/frigate/current"
        fi
    else
        print_error "Container is not running"
        return 1
    fi
}

# Function to start frontend development server
start_frontend_dev() {
    if [ -d "web" ]; then
        # Check if container is running
        if docker compose ps devcontainer | grep -q "Up"; then
            print_info "Starting frontend development server inside container..."
            print_info "Frontend will be available at http://localhost:5173"
            print_info "Use Ctrl+C to stop the frontend server"

            docker compose exec devcontainer bash -c "cd /workspace/frigate/web && npm run dev"
        else
            print_error "Container is not running. Please start it with: docker compose up -d"
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
    echo "• Frontend (Production):  http://localhost:5000"
    echo "• Backend API:           http://localhost:5001/api"
    echo "• MQTT Broker:           localhost:1883"
    echo
    echo "Docker Services:"
    docker compose ps
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
    echo "  docker compose down"
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
    echo "  -d, --docker-only   Start only Docker services (no frontend)"
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
    if [ "$BUILD_ONLY" = true ] || ! docker images | grep -q devcontainer; then
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
        docker compose exec -d devcontainer bash -c "cd /workspace/frigate/web && npm run dev" > /dev/null 2>&1

        # Wait a moment for the frontend to start
        sleep 5

        # Check if frontend is running
        if docker compose exec devcontainer pgrep -f "vite.*--host" > /dev/null 2>&1; then
            print_success "Frontend development server started inside container"
            print_info "Frontend available at http://localhost:5173"
            print_info "Backend API available at http://localhost:5001/api"

            # Keep the script running and show logs
            echo
            print_info "Press Ctrl+C to stop all services"
            echo

            # Wait for user interrupt
            trap 'print_info "Stopping services..."; docker compose exec devcontainer pkill -f "vite.*--host" 2>/dev/null; docker compose exec devcontainer pkill -f "python3.*frigate" 2>/dev/null; docker compose down 2>/dev/null; print_success "All services stopped"; exit 0' INT

            # Show logs or keep running
            if docker-compose version &> /dev/null; then
                docker-compose logs -f
            else
                docker compose logs -f
            fi
        else
            print_warning "Frontend development server may not have started correctly"
            print_info "You can start it manually with: docker compose exec devcontainer bash -c 'cd /workspace/frigate/web && npm run dev'"
            show_access_info

            # Keep running to show logs
            docker compose logs -f
        fi
    else
        # Docker-only mode
        print_success "Docker services started in background"
        print_info "Use 'docker compose logs -f' to view logs"
        print_info "Use 'docker compose down' to stop services"
    fi
fi