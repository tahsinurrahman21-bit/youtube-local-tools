# YouTube Local Tools - Windows setup bootstrap
#
# 1. Picks an install folder and writes the ownership marker install.py expects.
# 2. Copies the installer files (and builds apps.zip from apps\ when run from a Git clone).
# 3. Downloads uv (checksum-verified, from bootstrap\assets.json).
# 4. Uses uv to create a private Python 3.11 environment inside the install folder.
# 5. Runs bootstrap\install.py, which installs the apps, libraries, FFmpeg, Deno and GPU support.
# 6. Creates app shortcuts in the install folder.
#
# Nothing is installed system-wide, no administrator rights are needed, and nothing
# is written to the registry. Keep this file ASCII-only (Windows PowerShell 5.1).

[CmdletBinding()]
param(
    [string]$InstallDir,
    [ValidateSet('auto', 'cpu')][string]$Gpu = 'auto'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
# install.py and uv print UTF-8; decode and display it as UTF-8 so text is not garbled.
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding } catch {}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path      # ...\bootstrap
$Source = Split-Path -Parent $Here                            # repo or extracted release
$MarkerName = '.youtube-local-tools-install'
$MarkerText = 'YouTubeLocalTools-Installer-v1'
$script:Log = $null

function Say([string]$Text) {
    Write-Host $Text
    if ($script:Log) { Add-Content -LiteralPath $script:Log -Value $Text -Encoding UTF8 }
}

function Invoke-Logged([string]$Exe, [string[]]$Arguments) {
    # Native tools write progress to stderr; do not let PowerShell treat that as an error.
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object { Say ("$_") }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    return $code
}

function New-AppsZip([string]$From, [string]$ZipPath) {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    $base = (Resolve-Path -LiteralPath $From).Path.TrimEnd('\') + '\'
    $zip = [IO.Compression.ZipFile]::Open($ZipPath, 'Create')
    try {
        Get-ChildItem -LiteralPath $From -Recurse -File -Force |
            Where-Object { $_.FullName -notmatch '\\(__pycache__|\.venv|\.pytest_cache|build|dist|tools)\\' -and $_.Extension -ne '.pyc' } |
            ForEach-Object {
                $rel = $_.FullName.Substring($base.Length).Replace('\', '/')
                [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $rel)
            }
    } finally {
        $zip.Dispose()
    }
}

try {
    Write-Host ''
    Write-Host 'YouTube Local Tools 1.1 setup'
    Write-Host '-----------------------------'

    # ---- 1. Choose the install folder --------------------------------------
    if (-not $InstallDir) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Choose where to install YouTube Local Tools. A "YouTubeLocalTools" folder is created inside it. Needs 3 GB free (8 GB with an NVIDIA GPU).'
        $dialog.ShowNewFolderButton = $true
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            Write-Host 'Setup cancelled.'
            exit 1
        }
        $InstallDir = $dialog.SelectedPath
    }
    $InstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    if ($InstallDir.Length -le 3) { $InstallDir = Join-Path $InstallDir 'YouTubeLocalTools' }  # a bare drive like D:\

    # A non-empty folder that is not an existing install gets a subfolder, so we never mix with other files.
    if (Test-Path -LiteralPath $InstallDir) {
        $hasMarker = Test-Path -LiteralPath (Join-Path $InstallDir $MarkerName)
        $isEmpty = @(Get-ChildItem -LiteralPath $InstallDir -Force).Count -eq 0
        if (-not $hasMarker -and -not $isEmpty) { $InstallDir = Join-Path $InstallDir 'YouTubeLocalTools' }
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $markerPath = Join-Path $InstallDir $MarkerName
    if (-not (Test-Path -LiteralPath $markerPath)) {
        if (@(Get-ChildItem -LiteralPath $InstallDir -Force).Count -gt 0) {
            throw "The folder $InstallDir is not empty and is not a YouTube Local Tools installation. Choose another folder."
        }
        Set-Content -LiteralPath $markerPath -Value $MarkerText -Encoding ASCII -NoNewline
    }

    $script:Log = Join-Path $InstallDir 'setup.log'
    Say 'YouTube Local Tools 1.1 setup'
    Say "Install folder: $InstallDir"

    $Temp = Join-Path $InstallDir 'setup-temp'
    $Cache = Join-Path $InstallDir 'setup-cache'
    New-Item -ItemType Directory -Force -Path $Temp, $Cache | Out-Null

    # ---- 2. Copy installer files ---------------------------------------------
    $Boot = Join-Path $InstallDir 'bootstrap'
    New-Item -ItemType Directory -Force -Path $Boot | Out-Null
    $sameBoot = ((Resolve-Path -LiteralPath $Here).Path.TrimEnd('\') -ieq (Resolve-Path -LiteralPath $Boot).Path.TrimEnd('\'))
    if (-not $sameBoot) {
        foreach ($name in 'install.py', 'launch.py', 'assets.json', 'THIRD-PARTY-NOTICES.txt', 'setup.ps1') {
            Copy-Item -LiteralPath (Join-Path $Here $name) -Destination $Boot -Force
        }
    }
    $appsSource = Join-Path $Source 'apps'
    if (Test-Path -LiteralPath (Join-Path $appsSource 'local_transcriber\main.py')) {
        Say 'Packaging the application source...'
        $tmpZip = Join-Path $Temp 'apps.zip'
        New-AppsZip $appsSource $tmpZip
        Copy-Item -LiteralPath $tmpZip -Destination (Join-Path $Boot 'apps.zip') -Force
    } elseif (Test-Path -LiteralPath (Join-Path $Here 'apps.zip')) {
        if (-not $sameBoot) { Copy-Item -LiteralPath (Join-Path $Here 'apps.zip') -Destination $Boot -Force }
    } else {
        throw 'Neither apps\ nor bootstrap\apps.zip was found. Download the complete release zip.'
    }

    # ---- 3. Download uv (private Python installer) ------------------------
    $uvExe = Join-Path $Boot 'uv.exe'
    if (-not (Test-Path -LiteralPath $uvExe)) {
        Say 'Downloading the private Python installer (uv)...'
        $manifest = Get-Content -LiteralPath (Join-Path $Boot 'assets.json') -Raw | ConvertFrom-Json
        $asset = $manifest.uv.'uv-x86_64-pc-windows-msvc.zip'
        if (-not $asset -or -not $asset.sha256 -or $asset.sha256.Length -ne 64) { throw 'Missing download checksum for uv.' }
        $uvZip = Join-Path $Temp 'uv.zip'
        Invoke-WebRequest -Uri $asset.url -OutFile $uvZip -UseBasicParsing -Headers @{ 'User-Agent' = 'YouTubeLocalTools-Setup/1.1' }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $uvZip).Hash.ToLowerInvariant()
        if ($hash -ne $asset.sha256.ToLowerInvariant()) {
            Remove-Item -LiteralPath $uvZip -Force
            throw 'Download checksum did not match: uv.zip'
        }
        $uvDir = Join-Path $Temp 'uv'
        Expand-Archive -LiteralPath $uvZip -DestinationPath $uvDir -Force
        foreach ($name in 'uv.exe', 'uvw.exe', 'uvx.exe') {
            $found = Get-ChildItem -LiteralPath $uvDir -Recurse -Filter $name | Select-Object -First 1
            if ($found) { Copy-Item -LiteralPath $found.FullName -Destination $Boot -Force }
        }
        if (-not (Test-Path -LiteralPath $uvExe)) { throw 'uv.exe was not found in the downloaded archive.' }
    }

    # ---- 4. Private Python environment ------------------------------------
    Get-ChildItem env: | Where-Object { $_.Name -match '^(UV_|PIP_|PYTHON)' -or $_.Name -in 'VIRTUAL_ENV', 'CONDA_PREFIX' } |
        ForEach-Object { Remove-Item -LiteralPath ('env:' + $_.Name) -ErrorAction SilentlyContinue }
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $InstallDir 'runtime\python'
    $env:UV_CACHE_DIR = $Cache
    $env:UV_PYTHON_INSTALL_BIN = 'false'
    $env:UV_PYTHON_INSTALL_REGISTRY = 'false'
    $env:UV_NO_CONFIG = 'true'
    $env:UV_NO_PROGRESS = 'true'
    $env:UV_LINK_MODE = 'copy'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONNOUSERSITE = '1'
    $env:TMP = $Temp
    $env:TEMP = $Temp

    Say 'Installing a private copy of Python into the selected folder...'
    $py = Join-Path $InstallDir 'runtime\env\Scripts\python.exe'
    Push-Location -LiteralPath $InstallDir
    try {
        if (-not (Test-Path -LiteralPath $py)) {
            $code = Invoke-Logged $uvExe @('venv', 'runtime\env', '--python', '3.11', '--managed-python')
            if ($code -ne 0) { throw 'Could not create the private Python environment.' }
        } else {
            Say 'Existing private Python environment found; reusing it.'
        }

        # ---- 5. Install apps, libraries, FFmpeg, Deno, GPU support --------
        $code = Invoke-Logged $py @((Join-Path $Boot 'install.py'), '--root', $InstallDir, '--assets', $Boot, '--gpu', $Gpu)
        if ($code -ne 0) { throw 'A setup component failed. See setup.log in the selected folder.' }
    } finally {
        Pop-Location
    }

    # ---- 6. Shortcuts --------------------------------------------------------
    Say 'Creating app shortcuts...'
    $pyw = Join-Path $InstallDir 'runtime\env\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $pyw)) { $pyw = $py }
    $launcher = Join-Path $InstallDir 'launch.py'
    $shell = New-Object -ComObject WScript.Shell
    $made = @()
    foreach ($app in @(@('screenshot_pdf', 'YouTube Screenshots to PDF'), @('local_transcriber', 'YouTube Local Transcriber'))) {
        $lnk = Join-Path $InstallDir ($app[1] + '.lnk')
        $shortcut = $shell.CreateShortcut($lnk)
        $shortcut.TargetPath = $pyw
        $shortcut.Arguments = '"' + $launcher + '" ' + $app[0]
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = $app[1]
        $shortcut.Save()
        $made += $lnk
    }
    Set-Content -LiteralPath (Join-Path $InstallDir 'shortcuts.json') -Value (ConvertTo-Json @($made) -Compress) -Encoding UTF8

    foreach ($dir in $Temp, $Cache) {
        try { Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction Stop } catch { Say "Some temporary files are still in use and can be deleted later: $dir" }
    }

    Say 'Setup finished. Open either app from the selected folder.'
    try { Start-Process explorer.exe -ArgumentList ('"' + $InstallDir + '"') } catch {}
    exit 0
} catch {
    Say ('SETUP FAILED: ' + $_.Exception.Message)
    exit 1
}
