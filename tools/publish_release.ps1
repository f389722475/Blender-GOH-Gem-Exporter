[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$Repo = "f389722475/Blender-GOH-Gem-Exporter",
    [string]$GitRoot = "D:\codex\GOH\Blender GOH Gem Exporter Git",
    [string]$DevRoot = "D:\codex\GOH\Blender GOH Gem Exporter",
    [string]$UnlockRoot = "D:\codex\GOH\Blender GOH Gem Exporter Unlock",
    [string]$BlenderExe = "D:\Steam\steamapps\common\Blender\blender.exe",
    [string]$CommitMessage = "",
    [string]$NotesPath = "",

    [switch]$SkipValidation,
    [switch]$SkipBackup,
    [switch]$SkipPackage,
    [switch]$SkipCommit,
    [switch]$NoPush,
    [switch]$ReplaceExistingRelease,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = $GitRoot
    )
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Invoke-External -FilePath "git" -Arguments $Arguments -WorkingDirectory $GitRoot
}

function Invoke-Gh {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Invoke-External -FilePath "gh" -Arguments $Arguments -WorkingDirectory $GitRoot
}

function Ensure-GhToken {
    if ($env:GH_TOKEN) {
        return
    }
    $remote = & git -C $GitRoot remote get-url origin
    if ($remote -notmatch "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)") {
        throw "Cannot infer GitHub credential path from origin: $remote"
    }
    $owner = $Matches.owner
    $repoName = $Matches.repo
    $credentialInput = "protocol=https`nhost=github.com`npath=$owner/$repoName.git`n`n"
    $credential = $credentialInput | git credential fill
    $tokenLine = $credential | Where-Object { $_ -like "password=*" } | Select-Object -First 1
    if (-not $tokenLine) {
        throw "No GitHub token found through git credential fill. Log in with Git for HTTPS first."
    }
    $env:GH_TOKEN = $tokenLine -replace "^password=", ""
}

function Assert-NoPythonPublishWorkflow {
    $workflowPath = Join-Path $GitRoot ".github\workflows\python-publish.yml"
    if (Test-Path -LiteralPath $workflowPath) {
        throw "Refusing to publish because python-publish.yml exists locally. The project intentionally does not restore this workflow."
    }
}

function Invoke-Validation {
    Invoke-External -FilePath "python" -Arguments @("-m", "compileall", "blender_goh_gem_exporter", "tests")
    Invoke-External -FilePath "python" -Arguments @("tests\smoke_test.py")
    if (Test-Path -LiteralPath $BlenderExe) {
        $blenderTests = @(
            "tests\regression_t26e4_import_display_space.py",
            "tests\regression_m60a1_import.py",
            "tests\regression_3blend_export.py"
        )
        foreach ($test in $blenderTests) {
            if (Test-Path -LiteralPath (Join-Path $GitRoot $test)) {
                Invoke-External -FilePath $BlenderExe -Arguments @("--background", "--factory-startup", "--python", $test)
            }
        }
        if (Test-Path -LiteralPath (Join-Path $GitRoot "tests\regression_random_vehicle_imports.py")) {
            $oldIterations = [Environment]::GetEnvironmentVariable("GOH_REGRESSION_ITERATIONS", "Process")
            try {
                $env:GOH_REGRESSION_ITERATIONS = "5"
                Invoke-External -FilePath $BlenderExe -Arguments @("--background", "--factory-startup", "--python", "tests\regression_random_vehicle_imports.py")
            }
            finally {
                if ($null -eq $oldIterations) {
                    Remove-Item Env:\GOH_REGRESSION_ITERATIONS -ErrorAction SilentlyContinue
                }
                else {
                    $env:GOH_REGRESSION_ITERATIONS = $oldIterations
                }
            }
        }
    }
    else {
        Write-Warning "Blender executable not found: $BlenderExe. Skipping Blender runtime regressions."
    }
}

function Invoke-UnencryptedBackup {
    if (-not (Test-Path -LiteralPath $DevRoot)) {
        Write-Warning "Dev root not found, skipping unencrypted backup: $DevRoot"
        return
    }
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupDir = Join-Path $UnlockRoot "v$Version`_unencrypted_source_$stamp"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    robocopy $DevRoot $backupDir /E /XD .tools dist runtime_test_output .pytest_cache __pycache__ /XF *.pyc *.pyo *.zip | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
    Write-Output "Unencrypted backup: $backupDir"
}

function Invoke-PackageBuild {
    $distDir = Join-Path $DevRoot "dist"
    $script = Join-Path $GitRoot "tools\make_release_zips.py"
    Invoke-External -FilePath "python" -Arguments @($script, "--repo", $GitRoot, "--dist", $distDir, "--version", $Version, "--clean")
}

function Test-GitHasChanges {
    Push-Location -LiteralPath $GitRoot
    try {
        $status = git status --porcelain
        return [bool]$status
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $GitRoot)) {
    throw "Git root does not exist: $GitRoot"
}
if (-not $CommitMessage) {
    $CommitMessage = "Release v$Version"
}
if (-not $NotesPath) {
    $NotesPath = Join-Path $GitRoot "docs\RELEASE_NOTES_v$Version.md"
}

Ensure-GhToken
Invoke-Gh @("repo", "view", $Repo, "--json", "nameWithOwner")
Invoke-Git @("fetch", "origin", "main", "--tags", "--prune")
Invoke-Git @("pull", "--ff-only")
Assert-NoPythonPublishWorkflow

if (-not $SkipValidation) {
    Invoke-Validation
}
if (-not $SkipBackup) {
    Invoke-UnencryptedBackup
}
if (-not $SkipPackage) {
    Invoke-PackageBuild
}

$tag = "v$Version"
$assetZip = Join-Path $DevRoot "dist\blender_goh_gem_exporter-$Version.zip"
$assetFullZip = Join-Path $DevRoot "dist\blender_goh_gem_exporter-$Version-full.zip"
foreach ($asset in @($assetZip, $assetFullZip)) {
    if (-not (Test-Path -LiteralPath $asset)) {
        throw "Release asset is missing: $asset"
    }
}
if (-not (Test-Path -LiteralPath $NotesPath)) {
    throw "Release notes file is missing: $NotesPath"
}

if ($DryRun) {
    Write-Output "Dry run passed. No commit, tag, push, or release upload was performed."
    exit 0
}

if (-not $SkipCommit -and (Test-GitHasChanges)) {
    Invoke-Git @("add", "-A")
    Assert-NoPythonPublishWorkflow
    Invoke-Git @("commit", "-m", $CommitMessage)
}

Push-Location -LiteralPath $GitRoot
try {
    git rev-parse --verify $tag *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "Local tag already exists: $tag"
    }
}
finally {
    Pop-Location
}
$remoteTag = git -C $GitRoot ls-remote --tags origin "refs/tags/$tag"
if ($remoteTag) {
    throw "Remote tag already exists: $tag"
}

Invoke-Git @("tag", "-a", $tag, "-m", "Release $tag")
if (-not $NoPush) {
    Invoke-Git @("push", "origin", "main")
    Invoke-Git @("push", "origin", $tag)
}

$existingRelease = $false
Push-Location -LiteralPath $GitRoot
try {
    gh release view $tag --repo $Repo *> $null
    $existingRelease = ($LASTEXITCODE -eq 0)
}
finally {
    Pop-Location
}

if ($existingRelease) {
    if (-not $ReplaceExistingRelease) {
        throw "Release already exists: $tag. Use -ReplaceExistingRelease to upload assets with --clobber."
    }
    Invoke-Gh @("release", "edit", $tag, "--repo", $Repo, "--title", "Blender GOH GEM Exporter $tag", "--notes-file", $NotesPath)
    Invoke-Gh @("release", "upload", $tag, $assetZip, $assetFullZip, "--repo", $Repo, "--clobber")
}
else {
    Invoke-Gh @("release", "create", $tag, $assetZip, $assetFullZip, "--repo", $Repo, "--title", "Blender GOH GEM Exporter $tag", "--notes-file", $NotesPath)
}

Invoke-Gh @("release", "view", $tag, "--repo", $Repo, "--json", "tagName,url,assets")
Invoke-Git @("fetch", "origin", "main", "--tags", "--prune")
Invoke-Git @("merge-base", "--is-ancestor", $tag, "origin/main")
Write-Output "Release publish completed: $tag"
