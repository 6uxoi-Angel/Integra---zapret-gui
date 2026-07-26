param(
    [switch]$InstallIfMissing
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Diagnostic([string]$Message) {
    [Console]::Error.WriteLine($Message)
}

function Test-PythonExecutable([string]$Executable) {
    if ([string]::IsNullOrWhiteSpace($Executable)) { return $null }
    try {
        $resolved = [System.IO.Path]::GetFullPath($Executable)
    } catch {
        $resolved = $Executable
    }
    if ($resolved -like "*\WindowsApps\python*.exe") { return $null }
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { return $null }

    try {
        $script = @"
import struct, sys
version = sys.version_info[:3]
ok = struct.calcsize('P') * 8 == 64 and (3, 10, 0) <= version < (3, 15, 0)
if not ok:
    raise SystemExit(1)
print(sys.executable)
"@
        $output = & $resolved -c $script 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) {
            return ([string](@($output)[-1])).Trim()
        }
    } catch {
        return $null
    }
    return $null
}

function Find-SupportedPython {
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $candidates = New-Object 'System.Collections.Generic.List[string]'

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($version in @("3.14", "3.13", "3.12", "3.11", "3.10")) {
            try {
                $path = & $py.Source "-$version" -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $path) {
                    [void]$candidates.Add(([string](@($path)[-1])).Trim())
                }
            } catch { }
        }
    }

    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            [void]$candidates.Add($command.Source)
        }
    }

    $roots = New-Object 'System.Collections.Generic.List[string]'
    if ($env:LOCALAPPDATA) { [void]$roots.Add((Join-Path $env:LOCALAPPDATA "Programs\Python")) }
    if ($env:ProgramFiles) { [void]$roots.Add((Join-Path $env:ProgramFiles "Python*")) }
    if (${env:ProgramFiles(x86)}) { [void]$roots.Add((Join-Path ${env:ProgramFiles(x86)} "Python*")) }
    foreach ($root in $roots) {
        if ([string]::IsNullOrWhiteSpace($root)) { continue }
        try {
            Get-ChildItem -Path $root -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue |
                ForEach-Object { [void]$candidates.Add($_.FullName) }
        } catch { }
    }

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate) -or -not $seen.Add($candidate)) { continue }
        $valid = Test-PythonExecutable $candidate
        if ($valid) { return $valid }
    }
    return $null
}

function Install-Python313 {
    Write-Diagnostic "Supported Python was not found. Installing 64-bit Python 3.13 for the current user..."

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            & $winget.Source install --id Python.Python.3.13 --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
            if ($LASTEXITCODE -eq 0) { return }
            Write-Diagnostic "winget installation failed; trying the official python.org installer."
        } catch {
            Write-Diagnostic "winget installation failed; trying the official python.org installer."
        }
    }

    $indexUrl = "https://www.python.org/ftp/python/"
    $response = Invoke-WebRequest -UseBasicParsing -Uri $indexUrl
    $matches = [regex]::Matches($response.Content, 'href="(3\.13\.\d+)/"')
    $versions = @($matches | ForEach-Object { [Version]$_.Groups[1].Value } | Sort-Object -Descending -Unique)
    if (-not $versions -or $versions.Count -eq 0) {
        throw "Could not determine the latest Python 3.13 release from python.org."
    }

    $version = $versions[0].ToString()
    $installerUrl = "$indexUrl$version/python-$version-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-$version-amd64.exe"
    Write-Diagnostic "Downloading Python $version from python.org..."
    Invoke-WebRequest -UseBasicParsing -Uri $installerUrl -OutFile $installerPath

    try {
        $arguments = @(
            "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1",
            "Include_test=0", "Include_doc=0", "Include_debug=0", "Shortcuts=0"
        )
        $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Python installer returned exit code $($process.ExitCode)."
        }
    } finally {
        Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    }
}

$python = Find-SupportedPython
if (-not $python -and $InstallIfMissing) {
    Install-Python313
    $python = Find-SupportedPython
}

if (-not $python) {
    Write-Diagnostic "No supported 64-bit Python 3.10-3.14 installation was found."
    exit 2
}

[Console]::Out.WriteLine($python)
exit 0
