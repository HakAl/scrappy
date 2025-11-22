#!/bin/bash
# Helper script to run tests in Docker

set -e

echo "=== Running Scrappy Tests in Docker ==="
echo ""

# Function to run a specific service
run_service() {
    local service=$1
    local description=$2

    echo ">>> $description"
    docker-compose run --rm "$service"
    echo ""
}

# Parse command line arguments
case "${1:-all}" in
    all)
        echo "Running all tests..."
        run_service test "Running full test suite"
        ;;

    semantic)
        echo "Running semantic search tests..."
        run_service test-semantic "Running semantic search fixture tests"
        ;;

    demo)
        echo "Running integration demo..."
        run_service demo "Running integration demo"
        ;;

    demo-semantic)
        echo "Running semantic search POC..."
        run_service demo-semantic "Running semantic search POC"
        ;;

    shell)
        echo "Opening interactive shell..."
        docker-compose run --rm scrappy bash
        ;;

    build)
        echo "Building Docker image..."
        docker-compose build
        ;;

    clean)
        echo "Cleaning up Docker resources..."
        docker-compose down -v
        echo "Removed containers and volumes"
        ;;

    *)
        echo "Usage: $0 [all|semantic|demo|demo-semantic|shell|build|clean]"
        echo ""
        echo "Commands:"
        echo "  all           - Run full test suite (default)"
        echo "  semantic      - Run semantic search tests only"
        echo "  demo          - Run integration demo"
        echo "  demo-semantic - Run semantic search POC"
        echo "  shell         - Open interactive bash shell in container"
        echo "  build         - Build Docker image"
        echo "  clean         - Remove containers and volumes"
        exit 1
        ;;
esac

echo "=== Done ==="
