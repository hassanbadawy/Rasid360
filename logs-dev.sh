#!/bin/bash

# Frigate Development Environment Logs Script
# This script shows logs from all development services

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

# Function to show help
show_help() {
    echo "Frigate Development Environment Logs Script"
    echo
    echo "Usage: $0 [OPTIONS] [SERVICE]"
    echo
    echo "Options:"
    echo "  -h, --help          Show this help message"
    echo "  -f, --follow        Follow log output (tail -f)"
    echo "  -n, --lines N       Show last N lines (default: 50)"
    echo "  --since TIME        Show logs since timestamp (e.g., '1h', '10m')"
    echo
    echo "Services:"
    echo "  devcontainer        Main Frigate development container"
    echo "  mqtt               MQTT broker"
    echo "  all                All services (default)"
    echo
    echo "Examples:"
    echo "  $0                  Show last 50 lines from all services"
    echo "  $0 -f               Follow logs from all services"
    echo "  $0 devcontainer     Show logs from devcontainer only"
    echo "  $0 -n 100 -f        Show last 100 lines and follow"
    echo "  $0 --since 1h       Show logs from the last hour"
}

# Parse command line arguments
FOLLOW=false
LINES=50
SINCE=""
SERVICE="all"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        --since)
            SINCE="--since=$2"
            shift 2
            ;;
        devcontainer|mqtt|all)
            SERVICE="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check if Docker Compose is available
COMPOSE_CMD="docker-compose"
if ! docker-compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
fi

# Function to show service status
show_status() {
    print_info "Service Status:"
    $COMPOSE_CMD ps
    echo
}

# Function to show logs for all services
show_all_logs() {
    if [ "$FOLLOW" = true ]; then
        if [ -n "$SINCE" ]; then
            $COMPOSE_CMD logs $SINCE -f
        else
            $COMPOSE_CMD logs -f
        fi
    else
        if [ -n "$SINCE" ]; then
            $COMPOSE_CMD logs --tail=$LINES $SINCE
        else
            $COMPOSE_CMD logs --tail=$LINES
        fi
    fi
}

# Function to show logs for specific service
show_service_logs() {
    local service=$1
    
    if [ "$FOLLOW" = true ]; then
        if [ -n "$SINCE" ]; then
            $COMPOSE_CMD logs $SINCE -f $service
        else
            $COMPOSE_CMD logs -f $service
        fi
    else
        if [ -n "$SINCE" ]; then
            $COMPOSE_CMD logs --tail=$LINES $SINCE $service
        else
            $COMPOSE_CMD logs --tail=$LINES $service
        fi
    fi
}

# Function to show container logs directly
show_container_logs() {
    local container=$1
    
    if [ "$FOLLOW" = true ]; then
        if [ -n "$SINCE" ]; then
            docker logs $SINCE -f $container
        else
            docker logs -f $container
        fi
    else
        if [ -n "$SINCE" ]; then
            docker logs --tail=$LINES $SINCE $container
        else
            docker logs --tail=$LINES $container
        fi
    fi
}

# Main execution
echo "=============================================="
print_info "Frigate Development Environment Logs"
echo "=============================================="

# Show current status
show_status

# Show logs based on service selection
case $SERVICE in
    devcontainer)
        print_info "Showing logs for devcontainer..."
        show_container_logs frigate-devcontainer
        ;;
    mqtt)
        print_info "Showing logs for MQTT..."
        show_container_logs mqtt
        ;;
    all)
        print_info "Showing logs for all services..."
        show_all_logs
        ;;
    *)
        print_error "Unknown service: $SERVICE"
        show_help
        exit 1
        ;;
esac