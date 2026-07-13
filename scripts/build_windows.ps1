$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Root ".pyinstaller-cache"

$PythonLauncher = $null
foreach ($Version in @("3.12", "3.11", "3.10")) {
    try {
        py "-$Version" --version | Out-Null
        $PythonLauncher = "-$Version"
        break
    } catch {
    }
}

if ($null -eq $PythonLauncher) {
    throw "Python 3.12/3.11/3.10 is required for packaging. Install Python from https://www.python.org/downloads/windows/ and rerun this script."
}

if (Test-Path ".venv\Scripts\python.exe") {
    $VenvVersion = .\.venv\Scripts\python.exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($VenvVersion -eq "3.13") {
        Write-Host "Recreating .venv because Python 3.13 is not recommended for packaging."
        Remove-Item -Recurse -Force .venv
    }
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py $PythonLauncher -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pyinstaller

Remove-Item -Recurse -Force build, dist, .packaging-assets -ErrorAction SilentlyContinue
$WindowsIcon = Join-Path $Root "szzx_local\assets\icon\unframed_logo.ico"
if (-not (Test-Path $WindowsIcon)) {
    throw "Windows icon not found: $WindowsIcon"
}
.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --windowed `
    --onefile `
    --name "数智中心" `
    --icon $WindowsIcon `
    --add-data "szzx_local/assets;szzx_local/assets" `
    --clean `
    run.py
Remove-Item -Recurse -Force .packaging-assets -ErrorAction SilentlyContinue
$OutputExe = Join-Path $Root "dist\数智中心.exe"
if (-not (Test-Path $OutputExe)) {
    throw "Windows executable was not created: $OutputExe"
}

if ($env:SKIP_SMOKE_TEST -ne "1") {
    $env:SZZX_LOCAL_DATA_DIR = Join-Path $Root ".smoke-data"
    & $OutputExe --smoke-test
} else {
    Write-Host "Skipping packaged smoke test."
}

Write-Host "Built dist\数智中心.exe"
