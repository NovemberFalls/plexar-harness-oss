# Creates or refreshes every Plexar profile under $env:USERPROFILE\.dsh\profiles.
# Idempotent: existing profiles keep their sessions and bundles are re-linked. Shipped patches are
# re-copied on every run, except plexar-web's after its first install: the Web UI saves settings there.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..\..\..").Path
$bundle = ("$root\packages\bundle\plexar").Replace('\', '/')
$brand = ("$root\packages\client\ui-brand-plexar").Replace('\', '/')
$voice = ("$root\packages\experimental\voice-input-bundle").Replace('\', '/')
$env:TSX_TSCONFIG_PATH = "$root\tsconfig.json"
$loader = ([Uri]"$root\node_modules\tsx\dist\esm\index.mjs").AbsoluteUri
function Invoke-Dsh { & node --import $loader "$root\apps\cli\src\bin.ts" @args }
$profiles = [ordered]@{ 'plexar' = 'headless'; 'plexar-web' = 'web'; 'plexar-sdk' = 'sdk'; 'plexar-acp' = 'acp' }
foreach ($p in $profiles.Keys) {
  $dir = "$env:USERPROFILE\.dsh\profiles\$p"
  $fresh = -not (Test-Path $dir)
  if ($fresh) { Invoke-Dsh --profile $p --from-default-profile $profiles[$p] --dump-default-config | Out-Null }
  Invoke-Dsh plugin --profile $p add "link:$bundle" | Out-Null
  if ($p -eq 'plexar-web') {
    Invoke-Dsh plugin --profile $p add "link:$brand" | Out-Null
    Invoke-Dsh plugin --profile $p add "link:$root/packages/client/ui-settings-plexar" | Out-Null
    # Speech to text: local SenseVoice recognizer + composer microphone button.
    Invoke-Dsh plugin --profile $p add "link:$voice" | Out-Null
  }
  # plexar-web's patch is copied only when this run created the profile: creating it already writes
  # a default cordis.patch.yml, so the file's presence cannot mark a first install. Afterwards the
  # Web UI owns that file (Features `off`, permission default), and re-running must not wipe it.
  # No app writes the other profiles' patches, so they are refreshed and pick up shipped changes
  # such as the default model.
  $patch = "$PSScriptRoot\$p.patch.yml"
  $installedPatch = "$dir\cordis.patch.yml"
  $appOwned = $p -eq 'plexar-web'
  if (($fresh -or -not $appOwned) -and (Test-Path $patch)) { Copy-Item $patch $installedPatch -Force }
  Write-Host "profile $p ready"
}
# Put the `plexar-harness` terminal client on the user PATH (idempotent); new terminals pick it up.
$cli = "$root\packages\bundle\plexar\cli"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (($userPath -split ';') -contains $cli)) {
  [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ";$cli"), 'User')
  Write-Host "added $cli to the user PATH; open a new terminal to run plexar-harness"
} else { Write-Host "plexar already on the user PATH" }
