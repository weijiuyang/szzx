param(
    [string]$Version = "",
    [string]$Notes = "",
    [string]$PublicBaseUrl = "",
    [string]$LatestPrefix = "windows/latest",
    [string]$VersionPrefix = "windows",
    [switch]$SkipGitPull
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Require-Env($Name) {
    $Value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Missing environment variable: $Name"
    }
    return $Value
}

if (-not $SkipGitPull) {
    Write-Host "Pulling latest code..."
    git pull --ff-only
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = python -c "from szzx_local.version import APP_VERSION; print(APP_VERSION)"
}

if ([string]::IsNullOrWhiteSpace($Notes)) {
    $Notes = "Windows build v$Version"
}

$Bucket = Require-Env "TENCENT_COS_BUCKET"
$Region = Require-Env "TENCENT_COS_REGION"
$SecretId = Require-Env "TENCENT_COS_SECRET_ID"
$SecretKey = Require-Env "TENCENT_COS_SECRET_KEY"

if ([string]::IsNullOrWhiteSpace($PublicBaseUrl)) {
    $PublicBaseUrl = [Environment]::GetEnvironmentVariable("TENCENT_COS_PUBLIC_BASE_URL")
}
if ([string]::IsNullOrWhiteSpace($PublicBaseUrl)) {
    $PublicBaseUrl = "https://$Bucket.cos.$Region.myqcloud.com"
}
$PublicBaseUrl = $PublicBaseUrl.TrimEnd("/")

Write-Host "Building Windows exe..."
$env:SKIP_SMOKE_TEST = "1"
& "$Root\scripts\build_windows.ps1"

$Python = "$Root\.venv\Scripts\python.exe"
& $Python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org cos-python-sdk-v5

$LatestExeKey = "$LatestPrefix/SZZXLocalDesk.exe"
$LatestManifestKey = "$LatestPrefix/update.json"
$VersionedExeKey = "$VersionPrefix/$Version/SZZXLocalDesk.exe"
$DownloadUrl = "$PublicBaseUrl/$LatestExeKey"

$Manifest = [ordered]@{
    version = $Version
    download_url = $DownloadUrl
    notes = $Notes
} | ConvertTo-Json -Depth 3
$ManifestPath = Join-Path $Root "dist\update.json"
$Manifest | Set-Content -Encoding UTF8 $ManifestPath

$UploadScript = Join-Path $Root "dist\upload_to_cos.py"
@"
import os
import time
from qcloud_cos import CosConfig, CosS3Client

config = CosConfig(
    Region=os.environ["TENCENT_COS_REGION"],
    SecretId=os.environ["TENCENT_COS_SECRET_ID"],
    SecretKey=os.environ["TENCENT_COS_SECRET_KEY"],
)
client = CosS3Client(config)

def upload_with_retry(local_path: str, key: str) -> None:
    last_error = None
    for attempt in range(1, 6):
        try:
            print(f"Uploading {local_path} -> {key} (attempt {attempt}/5)")
            with open(local_path, "rb") as file:
                client.put_object(
                    Bucket=os.environ["TENCENT_COS_BUCKET"],
                    Body=file,
                    Key=key,
                    ACL="public-read",
                    EnableMD5=False,
                )
            return
        except Exception as exc:
            last_error = exc
            wait_seconds = min(30, attempt * 6)
            print(f"Upload failed: {exc}. Retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)
    raise last_error

upload_with_retry(os.environ["LOCAL_EXE"], os.environ["LATEST_EXE_KEY"])
upload_with_retry(os.environ["LOCAL_EXE"], os.environ["VERSIONED_EXE_KEY"])
upload_with_retry(os.environ["LOCAL_MANIFEST"], os.environ["LATEST_MANIFEST_KEY"])
print("Upload complete.")
"@ | Set-Content -Encoding UTF8 $UploadScript

$env:LOCAL_EXE = Join-Path $Root "dist\SZZXLocalDesk.exe"
$env:LOCAL_MANIFEST = $ManifestPath
$env:LATEST_EXE_KEY = $LatestExeKey
$env:VERSIONED_EXE_KEY = $VersionedExeKey
$env:LATEST_MANIFEST_KEY = $LatestManifestKey

Write-Host "Uploading to Tencent COS..."
& $Python $UploadScript

Write-Host ""
Write-Host "Published v$Version"
Write-Host "Latest exe:       $DownloadUrl"
Write-Host "Update manifest:  $PublicBaseUrl/$LatestManifestKey"
Write-Host "Versioned exe:    $PublicBaseUrl/$VersionedExeKey"
