#requires -Version 5.1
<#
.SYNOPSIS
    Builds the Plexar Harness Windows installer (NSIS), signs it for the updater, and writes latest.json.

.DESCRIPTION
    INSTALLER.md. Run from anywhere; paths resolve from this script.
      1. pnpm run build                                   (repo lib/ output)
      2. pinned win-x64 Node from nodejs.org, SHA-256 checked against its SHASUMS256.txt
      3. scripts/plexar-release/stage-windows-bundle.mjs  (src-tauri/plexar-runtime/)
      4. tauri build                                      (NSIS installer)
      5. release copy PlexarHarness_<v>_x64-setup.exe, updater signature, latest.json, SHA-256

    The installer version is packages/bundle/plexar/package.json's version; tauri.conf.json is
    rewritten to match before building. The updater key and its password are read from
    <signing-dir> (never inside a repo) and given only to
    `tauri signer sign`. There is no Authenticode signing: SmartScreen warns on first run.

.NOTES
    ASCII only. $LASTEXITCODE is checked after every native call, because
    $ErrorActionPreference = 'Stop' does not catch a native exe's non-zero exit.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$DesktopDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $DesktopDir '..\..')).Path
$TauriDir = Join-Path $DesktopDir 'src-tauri'
$TauriConfPath = Join-Path $TauriDir 'tauri.conf.json'
$TauriCli = '@tauri-apps/cli@2.11.5'
$NodeVersion = 'v22.19.0'
$SigningDir = '<signing-dir>'

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "plexar-harness desktop build: '$Step' failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Version = (Get-Content -Raw -Path (Join-Path $RepoRoot 'packages\bundle\plexar\package.json') | ConvertFrom-Json).version
$Conf = [IO.File]::ReadAllText($TauriConfPath)
$Synced = [regex]::new('"version":\s*"[^"]*"').Replace($Conf, ('"version": "' + $Version + '"'), 1)
if ($Synced -ne $Conf) { [IO.File]::WriteAllText($TauriConfPath, $Synced, $Utf8NoBom) }
Write-Host "Plexar Harness $Version"

Write-Host "== 1/5: pnpm run build =="
Push-Location $RepoRoot
try {
    pnpm run build
    Assert-LastExitCode 'pnpm run build'
}
finally {
    Pop-Location
}

Write-Host "== 2/5: Node $NodeVersion (win-x64) =="
$NodeCache = Join-Path $env:TEMP "plexar-harness-node\$NodeVersion"
New-Item -ItemType Directory -Force -Path $NodeCache | Out-Null
$NodeZipName = "node-$NodeVersion-win-x64.zip"
$NodeZip = Join-Path $NodeCache $NodeZipName
$Sums = Join-Path $NodeCache 'SHASUMS256.txt'
Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/dist/$NodeVersion/SHASUMS256.txt" -OutFile $Sums
$Expected = (Get-Content $Sums | Where-Object { $_ -match ("\s" + [regex]::Escape($NodeZipName) + "$") } | ForEach-Object { ($_ -split '\s+')[0] })
if (-not $Expected) { Write-Error "no SHA-256 for $NodeZipName in SHASUMS256.txt"; exit 1 }
if (-not (Test-Path $NodeZip) -or (Get-FileHash -Algorithm SHA256 $NodeZip).Hash.ToLower() -ne $Expected) {
    Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/dist/$NodeVersion/$NodeZipName" -OutFile $NodeZip
}
$Actual = (Get-FileHash -Algorithm SHA256 $NodeZip).Hash.ToLower()
if ($Actual -ne $Expected) { Write-Error "Node archive SHA-256 $Actual does not match nodejs.org's $Expected"; exit 1 }
$NodeDir = Join-Path $NodeCache 'extract'
$NodeExe = Join-Path $NodeDir "node-$NodeVersion-win-x64\node.exe"
if (-not (Test-Path $NodeExe)) {
    if (Test-Path $NodeDir) { Remove-Item -Recurse -Force $NodeDir }
    Expand-Archive -Path $NodeZip -DestinationPath $NodeDir
}
Write-Host "verified $NodeZipName ($Actual)"

Write-Host "== 3/5: staging the runtime =="
Push-Location $RepoRoot
try {
    node scripts/plexar-release/stage-windows-bundle.mjs --node-exe $NodeExe
    Assert-LastExitCode 'stage-windows-bundle.mjs'
}
finally {
    Pop-Location
}

Write-Host "== 4/5: tauri build (NSIS) =="
# The build runs WITHOUT the signing key in its environment.
Push-Location $DesktopDir
try {
    npx --yes $TauriCli build
    Assert-LastExitCode 'tauri build'
}
finally {
    Pop-Location
}

Write-Host "== 5/5: release copy, updater signature, latest.json =="
$KeyFile = Join-Path $SigningDir 'updater.key'
$KeyPasswordFile = Join-Path $SigningDir 'updater.key.password'
foreach ($f in @($KeyFile, $KeyPasswordFile)) {
    if (-not (Test-Path $f)) { Write-Error "updater signing file missing: $f"; exit 1 }
}
$BundleDir = Join-Path $TauriDir 'target\release\bundle'
$Built = Join-Path $BundleDir ('nsis\Plexar Harness_' + $Version + '_x64-setup.exe')
if (-not (Test-Path $Built)) { Write-Error "installer not found: $Built"; exit 1 }
$ReleaseDir = Join-Path $BundleDir 'release'
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$Installer = Join-Path $ReleaseDir ('PlexarHarness_' + $Version + '_x64-setup.exe')
Copy-Item -Path $Built -Destination $Installer -Force
$SigFile = $Installer + '.sig'
if (Test-Path $SigFile) { Remove-Item -LiteralPath $SigFile }
Push-Location $DesktopDir
try {
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (Get-Content -Raw -Path $KeyPasswordFile).Trim()
    npx --yes $TauriCli signer sign -f $KeyFile $Installer | Out-Null
    Assert-LastExitCode 'tauri signer sign'
}
finally {
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = $null
    Pop-Location
}
if (-not (Test-Path $SigFile)) { Write-Error "updater signature missing: $SigFile"; exit 1 }
$ManifestPath = Join-Path $BundleDir 'latest.json'
Push-Location $RepoRoot
try {
    node --import tsx/esm scripts/plexar-release/updater-manifest.ts --version $Version --sig $SigFile --out $ManifestPath
    Assert-LastExitCode 'updater-manifest.ts'
}
finally {
    Pop-Location
}

$Hash = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower()
$SizeMb = [math]::Round((Get-Item $Installer).Length / 1MB, 1)
Write-Host "Installer: $Installer ($SizeMb MB)"
Write-Host "SHA-256:   $Hash"
Write-Host "Signature: $SigFile"
Write-Host "Manifest:  $ManifestPath"
Write-Host "Upload: release\PlexarHarness_${Version}_x64-setup.exe to https://downloads.plexar.tech/harness/windows/ and latest.json to https://downloads.plexar.tech/harness/latest.json"
