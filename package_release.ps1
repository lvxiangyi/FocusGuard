$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$ElectronDir = Join-Path $Root "electron"
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$ReleaseDir = Join-Path $ElectronDir "release"

$PackageJson = Get-Content -Raw -Encoding UTF8 (Join-Path $ElectronDir "package.json") | ConvertFrom-Json
$Version = $PackageJson.version
$Date = Get-Date -Format "yyyy-MM-dd"
$ArtifactName = "FocusGuard-Agent-$Version-$Date-win-unpacked"
$InstallerName = "FocusGuard-Agent-$Version-$Date-x64-setup.exe"
$SourceDir = Join-Path $ReleaseDir "win-unpacked"
$TargetDir = Join-Path $ReleaseDir $ArtifactName
$ZipPath = Join-Path $ReleaseDir "$ArtifactName.zip"
$InstallerPath = Join-Path $ReleaseDir $InstallerName
$NsisSucceeded = $false

function Assert-UnderDirectory {
    param(
        [string]$Path,
        [string]$Parent
    )
    $FullPath = [System.IO.Path]::GetFullPath($Path)
    $FullParent = [System.IO.Path]::GetFullPath($Parent)
    if (-not $FullPath.StartsWith($FullParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside release directory: $FullPath"
    }
}

function Invoke-Checked {
    param(
        [string]$Step,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "==> $Step"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Release version: $Version"
Write-Host "Release date:    $Date"
$env:RELEASE_DATE = $Date

Push-Location $BackendDir
try {
    Invoke-Checked "Run backend tests" { & ".\.venv\Scripts\python.exe" -m unittest discover -s tests }
    Invoke-Checked "Build backend executable" { & ".\.venv\Scripts\pyinstaller.exe" "aimonitor-backend.spec" --noconfirm }
}
finally {
    Pop-Location
}

Push-Location $FrontendDir
try {
    Invoke-Checked "Build frontend" { npm run build }
}
finally {
    Pop-Location
}

Push-Location $ElectronDir
try {
    Invoke-Checked "Build Electron win-unpacked" { npx electron-builder --dir }
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Force $ReleaseDir | Out-Null

if (Test-Path $TargetDir) {
    Assert-UnderDirectory -Path $TargetDir -Parent $ReleaseDir
    Remove-Item -LiteralPath $TargetDir -Recurse -Force
}

if (Test-Path $ZipPath) {
    Assert-UnderDirectory -Path $ZipPath -Parent $ReleaseDir
    Remove-Item -LiteralPath $ZipPath -Force
}

Copy-Item -LiteralPath $SourceDir -Destination $TargetDir -Recurse
foreach ($secretName in @(".env", "debug.log")) {
    $secretPath = Join-Path $TargetDir $secretName
    if (Test-Path -LiteralPath $secretPath) {
        Remove-Item -LiteralPath $secretPath -Force
    }
}
Set-Content -LiteralPath (Join-Path $TargetDir ".env.example") -Value "OPENROUTER_API_KEY=your_api_key_here`n" -Encoding ascii
Compress-Archive -Path $TargetDir -DestinationPath $ZipPath -Force

Push-Location $ElectronDir
try {
    if ($env:FOCUSGUARD_SKIP_NSIS -eq "1") {
        Write-Host ""
        Write-Host "==> Skipping NSIS installer (FOCUSGUARD_SKIP_NSIS=1)"
    }
    else {
        Write-Host ""
        Write-Host "==> Build Windows x64 NSIS installer"
        npx electron-builder --win nsis --x64
        if ($LASTEXITCODE -eq 0 -and (Test-Path $InstallerPath)) {
            $NsisSucceeded = $true
        }
        else {
            Write-Host "NSIS installer build failed or did not create the expected file."
        }
    }
}
finally {
    Pop-Location
}

Write-Host "Created:"
Write-Host "  $TargetDir"
Write-Host "  $ZipPath"
if ($NsisSucceeded) {
    Write-Host "  $InstallerPath"
}
else {
    Write-Host ""
    Write-Host "NSIS installer was not created."
    Write-Host "  $InstallerPath"
    Write-Host ""
    Write-Host "Directory zip is the recommended MVP package."
    Write-Host "To retry NSIS later, fix network/proxy or cache:"
    Write-Host "  $env:LOCALAPPDATA\electron-builder\Cache\nsis"
}
