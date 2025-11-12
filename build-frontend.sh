#!/bin/bash

# Frigate Frontend Production Build Script
# This script builds the frontend for production deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Function to check if Node.js is available
check_nodejs() {
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed or not in PATH"
        exit 1
    fi
    
    print_success "Node.js and npm are available"
}

# Function to check if web directory exists
check_web_directory() {
    if [ ! -d "web" ]; then
        print_error "web directory not found"
        exit 1
    fi
    
    if [ ! -f "web/package.json" ]; then
        print_error "web/package.json not found"
        exit 1
    fi
    
    print_success "Web directory structure found"
}

# Function to install dependencies
install_dependencies() {
    print_info "Installing frontend dependencies..."
    
    cd web
    
    if [ -f "package-lock.json" ]; then
        npm install
    elif [ -f "yarn.lock" ]; then
        yarn install
    elif [ -f "pnpm-lock.yaml" ]; then
        pnpm install
    else
        print_warning "No lock file found. Using npm install"
        npm install
    fi
    
    cd ..
    print_success "Dependencies installed"
}

# Function to build for production
build_production() {
    print_info "Building frontend for production..."
    
    cd web
    
    # Check if BASE_PATH environment variable is set, otherwise use default
    BASE_PATH=${BASE_PATH:-"/"}
    
    # Run the build command
    npm run build
    
    cd ..
    
    # Copy built files to the expected location
    if [ -d "web/dist" ]; then
        print_info "Copying built files to web/dist..."
        print_success "Frontend built successfully"
        
        # Check if the docker-compose.yml expects web/dist to be mounted
        if docker-compose config 2>/dev/null | grep -q "web:dist"; then
            print_info "Found web/dist mount in docker-compose.yml"
        fi
    else
        print_error "Build failed - dist directory not found"
        exit 1
    fi
}

# Function to show help
show_help() {
    echo "Frigate Frontend Production Build Script"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help          Show this help message"
    echo "  -i, --install       Install dependencies before building"
    echo "  --base-path PATH    Set base path for build (default: /)"
    echo "  --clean             Clean build directory before building"
    echo
    echo "This script builds the frontend for production deployment."
    echo "The built files will be available in web/dist/"
    echo
    echo "Examples:"
    echo "  $0                  Build with existing dependencies"
    echo "  $0 -i               Install dependencies and build"
    echo "  $0 --base-path /frigate/  Build with custom base path"
    echo "  $0 --clean -i       Clean, install, and build"
}

# Parse command line arguments
INSTALL_DEPS=false
CLEAN_BUILD=false
BASE_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -i|--install)
            INSTALL_DEPS=true
            shift
            ;;
        --base-path)
            BASE_PATH="$2"
            shift 2
            ;;
        --clean)
            CLEAN_BUILD=true
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
print_info "Frigate Frontend Production Build"
echo "=============================================="

# Check requirements
check_nodejs
check_web_directory

# Clean build directory if requested
if [ "$CLEAN_BUILD" = true ]; then
    print_info "Cleaning build directory..."
    rm -rf web/dist
    print_success "Build directory cleaned"
fi

# Install dependencies if requested
if [ "$INSTALL_DEPS" = true ]; then
    install_dependencies
fi

# Set base path if specified
if [ -n "$BASE_PATH" ]; then
    export BASE_PATH="$BASE_PATH"
    print_info "Using base path: $BASE_PATH"
fi

# Build for production
build_production

# Show final information
echo
print_success "Frontend production build completed!"
echo "Built files location: web/dist/"
echo
echo "To serve the built frontend:"
echo "• Update docker-compose.yml to mount web/dist"
echo "• Or serve with a web server (e.g., nginx, apache)"
echo "• Or use: cd web && npm run preview"
echo
echo "Access URLs after deployment:"
echo "• Frigate UI: http://localhost:5000"
echo "• API: http://localhost:5000/api"
echo "=============================================="