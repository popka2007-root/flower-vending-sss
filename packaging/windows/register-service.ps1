# Register Flower Vending as a Windows service using NSSM
# Run this script as Administrator.

$serviceName = "FlowerVending"
$appPath = "C:\Program Files\FlowerVending\FlowerVending.exe"

# Check if NSSM is available
$nssm = Get-Command "nssm.exe" -ErrorAction SilentlyContinue
if (-not $nssm) {
    Write-Host "NSSM not found. Download from https://nssm.cc/download"
    Write-Host "Extract nssm.exe to a PATH directory or same folder as this script."
    exit 1
}

# Check if service already exists
if (Get-Service $serviceName -ErrorAction SilentlyContinue) {
    Write-Host "Service '$serviceName' already exists. Restarting..."
    & $nssm.Path restart $serviceName
    exit 0
}

# Install service
& $nssm.Path install $serviceName $appPath

# Configure service
& $nssm.Path set $serviceName AppDirectory "C:\Program Files\FlowerVending"
& $nssm.Path set $serviceName AppParameters "--config config\machine.production.yaml --no-ui"
& $nssm.Path set $serviceName DisplayName "Flower Vending System"
& $nssm.Path set $serviceName Description "Production runtime for the flower vending machine"
& $nssm.Path set $serviceName Start SERVICE_AUTO_START
& $nssm.Path set $serviceName AppStdout "C:\Program Files\FlowerVending\var\log\service.log"
& $nssm.Path set $serviceName AppStderr "C:\Program Files\FlowerVending\var\log\service.err"
& $nssm.Path set $serviceName AppStopMethodSkip 6
& $nssm.Path set $serviceName AppThrottle 0

# Start service
& $nssm.Path start $serviceName

Write-Host "Service '$serviceName' installed and started."
Write-Host "Manage with: nssm (stop|start|restart|status) $serviceName"
