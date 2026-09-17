# Windows lifecycle smoke test. Execution is ONLY for a disposable VM/user.
[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$Confirmation = '',
    [string]$Setup = '',
    [string]$UpgradeSetup = '',
    [string]$ExpectedVersion = '',
    [ValidateSet('disabled', 'owned', 'foreign')]
    [string]$AutostartCase = 'owned',
    [string]$EvidenceDirectory = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$stages = @('fresh-install', 'seed-settings-autostart', 'upgrade', 'uninstall')
if (-not $Execute) {
    [ordered]@{status = 'not_run'; mode = 'plan-only'; stages = $stages;
        requirement = 'Disposable Windows VM, standard user, two built installers; see docs/installer-smoke.md'} |
        ConvertTo-Json -Depth 5
    exit 0
}
# These are consent gates, not VM detection. NEVER set them on a workstation.
if ($Confirmation -cne 'I_ACCEPT_DISPOSABLE_VM' -or $env:PC_REMOTE_DISPOSABLE_VM -cne '1') {
    throw 'Execution denied: explicit disposable-VM confirmation and environment gate required.'
}
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Use a non-elevated standard-user account; elevation invalidates the user-scope test.'
}
if (-not $Setup -or -not $UpgradeSetup -or -not $ExpectedVersion -or -not $EvidenceDirectory) {
    throw 'Setup, UpgradeSetup, ExpectedVersion and a new EvidenceDirectory are required.'
}
$Setup = (Resolve-Path -LiteralPath $Setup).Path
$UpgradeSetup = (Resolve-Path -LiteralPath $UpgradeSetup).Path
foreach ($binary in @($Setup, $UpgradeSetup)) {
    if ([IO.Path]::GetExtension($binary) -ne '.exe') { throw 'Installer must be an EXE.' }
}
if (Test-Path -LiteralPath $EvidenceDirectory) { throw 'EvidenceDirectory must not already exist.' }
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\PC Remote'
$exe = Join-Path $installDir 'PC Remote.exe'
$settingsDir = Join-Path $env:APPDATA 'PC Remote'
$legacyDir = Join-Path $env:APPDATA 'PC-Android'
$startupDir = [Environment]::GetFolderPath('Startup')
$startup = Join-Path $startupDir 'PC Remote.cmd'
$legacyStartup = Join-Path $startupDir 'PC-Android.cmd'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$arpSuffix = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8A5675B9-1F20-4E2B-8BB4-D0C42973F9E4}_is1'
$arpKey = "HKCU:\$arpSuffix"
$machineArp = "HKLM:\$arpSuffix"
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PC Remote\PC Remote.lnk'
$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PC Remote.lnk'
function Read-RunValue {
    if (Test-Path $runKey) {
        return (Get-Item $runKey).GetValue('PC Remote', $null)
    }
    return $null
}
foreach ($path in @($installDir, $settingsDir, $legacyDir, $startup, $legacyStartup, $arpKey, $machineArp, $startMenu, $desktop)) {
    if (Test-Path -LiteralPath $path) { throw "Dirty test user: existing $path. Revert VM; do not delete user data." }
}
if ($null -ne (Read-RunValue)) { throw 'Dirty test user: PC Remote Run value exists.' }
if (Get-Process -Name 'PC Remote' -ErrorAction SilentlyContinue) { throw 'PC Remote is already running.' }

function Get-MachineState {
    # Read-only. An access error is a BLOCKER, not an empty/clean inventory.
    $services = @(Get-CimInstance Win32_Service -ErrorAction Stop |
        Sort-Object Name | Select-Object Name, PathName, StartMode)
    $rules = @(Get-NetFirewallRule -ErrorAction Stop | Sort-Object Name |
        Select-Object Name, DisplayName, Enabled, Direction, Action, Profile)
    $programs = @(Get-NetFirewallApplicationFilter -ErrorAction Stop | Sort-Object InstanceID |
        Select-Object InstanceID, Program)
    return (@{services = $services; rules = $rules; programs = $programs} | ConvertTo-Json -Depth 6 -Compress)
}
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -Wait -PassThru
    $script:events.Add(@{command = [IO.Path]::GetFileName($File); exitCode = $process.ExitCode})
    Assert-True ($process.ExitCode -eq 0) "Process failed: $File exit=$($process.ExitCode)"
}
function Assert-Installed([string]$Version = '') {
    Assert-True (Test-Path -LiteralPath $exe) 'Installed EXE missing.'
    Assert-True (Test-Path -LiteralPath $startMenu) 'Start Menu shortcut missing.'
    Assert-True (-not (Test-Path -LiteralPath $desktop)) 'Unrequested desktop shortcut was created.'
    Assert-True (-not (Test-Path -LiteralPath $machineArp)) 'Machine ARP registration was created.'
    $arp = Get-ItemProperty -LiteralPath $arpKey
    Assert-True ($arp.Publisher -eq 'mimaxon1') 'ARP publisher mismatch.'
    if ($Version) {
        Assert-True ($arp.DisplayVersion -eq $Version) 'ARP version mismatch.'
        Assert-True ($arp.DisplayName -eq "PC Remote $Version") 'ARP display name mismatch.'
    }
    Assert-True (-not (Get-Process -Name 'PC Remote' -ErrorAction SilentlyContinue)) 'Silent installer launched app.'
}
function Assert-MachineUnchanged {
    Assert-True ((Get-MachineState) -ceq $script:baseline) 'Service/firewall inventory changed; inspect evidence and revert VM.'
}

New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
$events = New-Object 'System.Collections.Generic.List[object]'
$report = [ordered]@{status = 'running'; autostartCase = $AutostartCase;
    os = [Environment]::OSVersion.VersionString;
    setupSha256 = (Get-FileHash $Setup -Algorithm SHA256).Hash;
    upgradeSha256 = (Get-FileHash $UpgradeSetup -Algorithm SHA256).Hash;
    completed = @(); events = $events; error = $null}
$failed = $false
try {
    $baseline = Get-MachineState
    $baseline | Set-Content (Join-Path $EvidenceDirectory 'machine-before.json') -Encoding UTF8
    $silent = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
    Invoke-Checked $Setup ($silent + @('/TASKS=""', ('/LOG="{0}"' -f (Join-Path $EvidenceDirectory 'install.log'))))
    Assert-Installed
    Assert-True (-not (Test-Path $startup)) 'Fresh install enabled Startup autostart.'
    Assert-True ($null -eq (Read-RunValue)) 'Fresh install enabled Run-key autostart.'
    Assert-MachineUnchanged
    $report.completed += 'fresh-install'

    if ($AutostartCase -eq 'owned') {
        # This is the only application CLI invocation; it must exit, not run servers.
        Invoke-Checked $exe @('--install-autostart')
        Assert-True (Test-Path $startup) 'Autostart CLI did not create Startup file.'
        $generated = [IO.File]::ReadAllText($startup)
        Assert-True ($generated.Contains(('start "" /b "{0}"' -f $exe))) 'Autostart does not target installed executable.'
        # Exercise supported compatibility artifacts without running them.
        Copy-Item -LiteralPath $startup -Destination $legacyStartup
        if (-not (Test-Path $runKey)) { New-Item -Path $runKey | Out-Null }
        New-ItemProperty -Path $runKey -Name 'PC Remote' -Value ('"{0}"' -f $exe) -PropertyType String -Force | Out-Null
    } elseif ($AutostartCase -eq 'foreign') {
        [IO.File]::WriteAllText($startup, "@echo off`r`nrem unrelated portable installation`r`n")
        Copy-Item -LiteralPath $startup -Destination $legacyStartup
        if (-not (Test-Path $runKey)) { New-Item -Path $runKey | Out-Null }
        New-ItemProperty -Path $runKey -Name 'PC Remote' -Value '"C:\Other Portable\PC Remote.exe"' -PropertyType String -Force | Out-Null
    }
    # Opaque sentinels test installer byte preservation, NOT application schema/migration.
    New-Item -ItemType Directory -Path $settingsDir, $legacyDir -Force | Out-Null
    $fixtures = @((Join-Path $settingsDir 'settings.json'),
        (Join-Path $settingsDir 'network_settings.json'), (Join-Path $legacyDir 'settings.json'))
    foreach ($file in $fixtures) { [IO.File]::WriteAllText($file, '{"installer_smoke_sentinel":"preserve-me"}') }
    $hashes = @{}
    foreach ($file in $fixtures) { $hashes[$file] = (Get-FileHash $file).Hash }
    $startupHash = if (Test-Path $startup) { (Get-FileHash $startup).Hash } else { $null }
    $runValue = Read-RunValue
    $report.completed += 'seed-settings-autostart'

    Invoke-Checked $UpgradeSetup ($silent + @('/TASKS=""', ('/LOG="{0}"' -f (Join-Path $EvidenceDirectory 'upgrade.log'))))
    Assert-Installed $ExpectedVersion
    foreach ($file in $fixtures) { Assert-True ((Get-FileHash $file).Hash -eq $hashes[$file]) 'Upgrade modified persisted settings.' }
    if ($null -eq $startupHash) { Assert-True (-not (Test-Path $startup)) 'Upgrade enabled autostart.' }
    else {
        Assert-True ((Get-FileHash $startup).Hash -eq $startupHash) 'Upgrade modified autostart choice.'
        Assert-True ((Get-FileHash $legacyStartup).Hash -eq $startupHash) 'Upgrade modified legacy autostart choice.'
    }
    Assert-True ((Read-RunValue) -ceq $runValue) 'Upgrade modified Run value.'
    Assert-MachineUnchanged
    $report.completed += 'upgrade'

    Invoke-Checked (Join-Path $installDir 'unins000.exe') ($silent + @('/LOG="{0}"' -f (Join-Path $EvidenceDirectory 'uninstall.log')))
    Assert-True (-not (Get-Process -Name 'PC Remote' -ErrorAction SilentlyContinue)) 'Uninstall left running application.'
    Assert-True (-not (Test-Path $exe)) 'Uninstall left application executable.'
    Assert-True (-not (Test-Path $arpKey)) 'Uninstall left ARP registration.'
    Assert-True (-not (Test-Path $startMenu)) 'Uninstall left Start Menu shortcut.'
    foreach ($file in $fixtures) { Assert-True ((Get-FileHash $file).Hash -eq $hashes[$file]) 'Uninstall removed or modified settings.' }
    if ($AutostartCase -eq 'foreign') {
        foreach ($file in @($startup, $legacyStartup)) { Assert-True ((Get-FileHash $file).Hash -eq $startupHash) 'Uninstall removed unrelated Startup file.' }
        Assert-True ((Read-RunValue) -ceq $runValue) 'Uninstall removed unrelated Run value.'
    } else {
        Assert-True (-not (Test-Path $startup)) 'Uninstall left owned Startup file.'
        Assert-True (-not (Test-Path $legacyStartup)) 'Uninstall left owned legacy Startup file.'
        Assert-True ($null -eq (Read-RunValue)) 'Uninstall left owned Run value.'
    }
    Assert-MachineUnchanged
    (Get-MachineState) | Set-Content (Join-Path $EvidenceDirectory 'machine-after.json') -Encoding UTF8
    $report.completed += 'uninstall'
    $report.status = 'passed'
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    $failed = $true
} finally {
    # Do not auto-delete fixtures or retry uninstall on failure. Preserve evidence;
    # discard/revert the VM after review, including foreign/sentinel leftovers.
    $report | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'result.json') -Encoding UTF8
    $report | ConvertTo-Json -Depth 8
}
if ($failed) { exit 1 }
