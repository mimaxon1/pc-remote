param(
  [Parameter(Mandatory = $true)][string]$IdentityName,
  [Parameter(Mandatory = $true)][string]$Publisher,
  [Parameter(Mandatory = $true)][string]$PublisherDisplayName,
  [Parameter(Mandatory = $true)][string]$Version,
  [string]$SourceDir = "dist\PC Remote",
  [string]$OutputDir = "release\store"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Convert-ToMsixVersion([string]$Value) {
  $clean = $Value.Trim().TrimStart('v')
  $parts = $clean.Split('.')
  if ($parts.Count -gt 4 -or $parts.Count -lt 1) {
    throw "MSIX version must contain one to four numeric components: $Value"
  }
  foreach ($part in $parts) {
    if ($part -notmatch '^\d+$') {
      throw "MSIX Store builds require a numeric four-part version; got: $Value"
    }
    $n = [int]$part
    if ($n -lt 0 -or $n -gt 65535) {
      throw "MSIX version component out of range 0..65535: $part"
    }
  }
  while ($parts.Count -lt 4) {
    $parts += '0'
  }
  return ($parts -join '.')
}

function Resize-Png([string]$Source, [string]$Destination, [int]$Width, [int]$Height) {
  Add-Type -AssemblyName System.Drawing
  $sourceImage = [System.Drawing.Image]::FromFile((Resolve-Path $Source))
  try {
    $bitmap = New-Object System.Drawing.Bitmap($Width, $Height)
    try {
      $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
      try {
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.DrawImage($sourceImage, 0, 0, $Width, $Height)
      }
      finally {
        $graphics.Dispose()
      }
      $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
      $bitmap.Dispose()
    }
  }
  finally {
    $sourceImage.Dispose()
  }
}

if (-not (Test-Path $SourceDir)) {
  throw "Portable build directory not found: $SourceDir. Run python build_release.py first."
}

$template = Join-Path $PSScriptRoot 'Package.appxmanifest.template'
if (-not (Test-Path $template)) {
  throw "Manifest template not found: $template"
}

$msixVersion = Convert-ToMsixVersion $Version
$staging = Join-Path $OutputDir 'staging'
$assets = Join-Path $staging 'Assets'
New-Item -ItemType Directory -Force -Path $assets | Out-Null

Copy-Item -Path (Join-Path $SourceDir '*') -Destination $staging -Recurse -Force

$icon = Join-Path (Split-Path $PSScriptRoot -Parent | Split-Path -Parent) 'web\icons\icon-192.png'
if (-not (Test-Path $icon)) {
  throw "Source icon not found: $icon"
}

Resize-Png $icon (Join-Path $assets 'StoreLogo.png') 50 50
Resize-Png $icon (Join-Path $assets 'Square44x44Logo.png') 44 44
Resize-Png $icon (Join-Path $assets 'Square150x150Logo.png') 150 150
Resize-Png $icon (Join-Path $assets 'Square310x310Logo.png') 310 310

# The source icon is square. For the optional wide tile we center it on a transparent canvas.
Add-Type -AssemblyName System.Drawing
$wide = New-Object System.Drawing.Bitmap(310, 150)
try {
  $g = [System.Drawing.Graphics]::FromImage($wide)
  try {
    $g.Clear([System.Drawing.Color]::Transparent)
    $src = [System.Drawing.Image]::FromFile((Resolve-Path $icon))
    try {
      $g.DrawImage($src, 80, 0, 150, 150)
    }
    finally {
      $src.Dispose()
    }
  }
  finally {
    $g.Dispose()
  }
  $wide.Save((Join-Path $assets 'Wide310x150Logo.png'), [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
  $wide.Dispose()
}

$manifest = Get-Content $template -Raw
$manifest = $manifest.Replace('__IDENTITY_NAME__', $IdentityName)
$manifest = $manifest.Replace('__PUBLISHER__', $Publisher)
$manifest = $manifest.Replace('__PUBLISHER_DISPLAY_NAME__', $PublisherDisplayName)
$manifest = $manifest.Replace('__VERSION__', $msixVersion)
$manifest | Set-Content -Path (Join-Path $staging 'AppxManifest.xml') -Encoding utf8

$kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$makeAppx = Get-ChildItem -Path $kits -Filter MakeAppx.exe -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -match '\\x64\\MakeAppx\.exe$' } |
  Sort-Object FullName -Descending |
  Select-Object -First 1
if (-not $makeAppx) {
  throw 'MakeAppx.exe was not found. Install a recent Windows SDK.'
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$outFile = Join-Path $OutputDir "PC-Remote-$($Version.TrimStart('v'))-store-x64.msix"
if (Test-Path $outFile) {
  Remove-Item $outFile -Force
}

& $makeAppx.FullName pack /d $staging /p $outFile /o
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "Created unsigned Store MSIX: $outFile"
Write-Host 'For Microsoft Store submission, do not self-sign with an untrusted certificate.'
Write-Host 'Partner Center will re-sign the MSIX after certification.'
