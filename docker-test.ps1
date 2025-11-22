# PowerShell script to run tests in Docker (Windows)

param(
    [Parameter(Position=0)]
    [ValidateSet("all", "semantic", "demo", "demo-semantic", "shell", "build", "clean")]
    [string]$Command = "all"
)

Write-Host "=== Running Scrappy Tests in Docker ===" -ForegroundColor Cyan
Write-Host ""

function Run-Service {
    param(
        [string]$Service,
        [string]$Description
    )

    Write-Host ">>> $Description" -ForegroundColor Yellow
    docker-compose run --rm $Service
    Write-Host ""
}

switch ($Command) {
    "all" {
        Write-Host "Running all tests..." -ForegroundColor Green
        Run-Service "test" "Running full test suite"
    }

    "semantic" {
        Write-Host "Running semantic search tests..." -ForegroundColor Green
        Run-Service "test-semantic" "Running semantic search fixture tests"
    }

    "demo" {
        Write-Host "Running integration demo..." -ForegroundColor Green
        Run-Service "demo" "Running integration demo"
    }

    "demo-semantic" {
        Write-Host "Running semantic search POC..." -ForegroundColor Green
        Run-Service "demo-semantic" "Running semantic search POC"
    }

    "shell" {
        Write-Host "Opening interactive shell..." -ForegroundColor Green
        docker-compose run --rm scrappy bash
    }

    "build" {
        Write-Host "Building Docker image..." -ForegroundColor Green
        docker-compose build
    }

    "clean" {
        Write-Host "Cleaning up Docker resources..." -ForegroundColor Green
        docker-compose down -v
        Write-Host "Removed containers and volumes" -ForegroundColor Green
    }
}

Write-Host "=== Done ===" -ForegroundColor Cyan
