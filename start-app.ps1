# Travel Guide Application Startup Script
# This script starts both the Python backend and Node.js frontend

Write-Host "🌍 AI-Powered Travel Guide Application" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Check if dependencies are installed
Write-Host "📦 Checking dependencies..." -ForegroundColor Yellow

# Check Node.js
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found. Please install Node.js v18+" -ForegroundColor Red
    exit 1
}

# Check Python
try {
    $pythonVersion = python --version
    Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Check if .env file exists
if (Test-Path ".env") {
    Write-Host "✅ Environment variables file found" -ForegroundColor Green
} else {
    Write-Host "⚠️  .env file not found. Please copy .env.example to .env" -ForegroundColor Yellow
    Write-Host "   and fill in your API keys and database connection" -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "📝 Created .env from template. Please edit with your values." -ForegroundColor Yellow
    }
    exit 1
}

Write-Host ""

# Stop any existing processes
Write-Host "🔄 Stopping existing servers..." -ForegroundColor Yellow
Get-Process | Where-Object {$_.ProcessName -like "*python*" -or $_.ProcessName -like "*uvicorn*" -or $_.ProcessName -like "*node*"} | Stop-Process -Force -ErrorAction SilentlyContinue

# Install dependencies if needed
if (!(Test-Path "node_modules")) {
    Write-Host "📦 Installing Node.js dependencies..." -ForegroundColor Yellow
    npm install --silent
}

Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet

Write-Host ""

# Start Python backend
Write-Host "🐍 Starting Python Backend (Port 8001)..." -ForegroundColor Green
Start-Process -WindowStyle Hidden -FilePath "uvicorn" -ArgumentList "app:app", "--reload", "--port", "8001", "--host", "0.0.0.0" -WorkingDirectory ".\python"

# Wait a bit for Python server to start
Start-Sleep -Seconds 3

# Start Node.js frontend  
Write-Host "⚡ Starting Node.js Frontend (Port 3000)..." -ForegroundColor Green
Start-Process -WindowStyle Hidden -FilePath "node" -ArgumentList "server.js"

# Wait for servers to fully start
Write-Host "⏳ Waiting for servers to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

Write-Host ""
Write-Host "🔍 Checking server status..." -ForegroundColor Yellow

# Check Python backend
try {
    $pythonHealth = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get -TimeoutSec 5
    Write-Host "✅ Python Backend: RUNNING" -ForegroundColor Green
    Write-Host "   📊 Status: $($pythonHealth.status)" -ForegroundColor White
    Write-Host "   🗺️ Places API: $($pythonHealth.osm_api)" -ForegroundColor White
    Write-Host "   🌤️ Weather API: $(if($pythonHealth.ow_key){'Available'}else{'Not Available'})" -ForegroundColor White
    Write-Host "   🤖 AI Guide: $(if($pythonHealth.groq_key){'Available'}else{'Not Available'})" -ForegroundColor White
} catch {
    Write-Host "❌ Python Backend: FAILED" -ForegroundColor Red
    Write-Host "   Check if port 8001 is available" -ForegroundColor Red
}

# Check Node.js frontend
try {
    $frontendResponse = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5
    if ($frontendResponse.StatusCode -eq 200) {
        Write-Host "✅ Node.js Frontend: RUNNING" -ForegroundColor Green
        Write-Host "   🌐 Web Interface: Available" -ForegroundColor White
    }
} catch {
    Write-Host "❌ Node.js Frontend: FAILED" -ForegroundColor Red
    Write-Host "   Check if port 3000 is available" -ForegroundColor Red
}

Write-Host ""
Write-Host "🎉 TRAVEL GUIDE APPLICATION IS READY!" -ForegroundColor Green
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Access your application at:" -ForegroundColor Cyan
Write-Host "   👉 http://localhost:3000" -ForegroundColor Yellow
Write-Host ""
Write-Host "✨ Features Available:" -ForegroundColor Cyan
Write-Host "   📅 Smart date-based travel planning" -ForegroundColor White
Write-Host "   🌤️ Weather-optimized recommendations" -ForegroundColor White
Write-Host "   🤖 AI-powered travel guides" -ForegroundColor White
Write-Host "   🗺️ Interactive maps with place markers" -ForegroundColor White
Write-Host "   🔗 Clickable places for Google reviews" -ForegroundColor White
Write-Host ""
Write-Host "💡 Tips:" -ForegroundColor Green
Write-Host "   • Try destinations like: Ooty, Paris, Tokyo, London" -ForegroundColor White
Write-Host "   • Enable 'AI travel guide & tips' for best experience" -ForegroundColor White
Write-Host "   • Click on place names to view Google reviews" -ForegroundColor White
Write-Host "   • Test different traveler types for varied recommendations" -ForegroundColor White
Write-Host ""
Write-Host "🛑 To stop the application, press Ctrl+C" -ForegroundColor Red
Write-Host ""

# Open browser automatically
try {
    Start-Process "http://localhost:3000"
    Write-Host "🌐 Opening your default browser..." -ForegroundColor Green
} catch {
    Write-Host "ℹ️  Please manually open http://localhost:3000 in your browser" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🚀 Ready to plan amazing trips! Enjoy your travel guide!" -ForegroundColor Magenta
Write-Host ""

# Keep the script running to show logs
Write-Host "📊 Application is running. Press Ctrl+C to stop." -ForegroundColor Yellow
try {
    # Keep script alive
    while ($true) {
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Host ""
    Write-Host "🛑 Shutting down servers..." -ForegroundColor Red
    Get-Process | Where-Object {$_.ProcessName -like "*python*" -or $_.ProcessName -like "*uvicorn*" -or $_.ProcessName -like "*node*"} | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "✅ Servers stopped. Goodbye!" -ForegroundColor Green
}