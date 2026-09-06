<#
.SYNOPSIS
    Archives a specified worktree <RunId> to .loop/archived_worktrees and cleans up remaining worktrees.

.DESCRIPTION
    Automates Section 8.3 of coding_agent/README.md:
    1. Ensures target archive folder .loop/archived_worktrees exists.
    2. Archives the specified <RunId> worktree using `git worktree move` (with fallback for raw copies).
    3. Prunes git worktree metadata.
    4. Removes and cleans up all remaining worktree directories under .loop/worktrees.

.PARAMETER RunId
    The ID of the run/worktree to archive (e.g., "20260728T174316-4235987a" or "run-001").
    If omitted, the script performs a cleanup of remaining worktrees.

.PARAMETER BaseDir
    Root directory containing the .loop folder. Auto-detects in '.' or '..' by default.

.EXAMPLE
    .\archive_worktrees.ps1 -RunId "20260820T230927-4055b18d"

.EXAMPLE
    .\archive_worktrees.ps1 "run-001"
#>

[CmdletBinding()]
param (
    [Parameter(Position = 0, Mandatory = $false, HelpMessage = "The Run ID of the worktree to archive")]
    [string]$RunId,

    [Parameter(Mandatory = $false)]
    [string]$BaseDir = ""
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# Resolve BaseDir (auto-detect .loop in current dir or parent dir if not specified)
if ([string]::IsNullOrWhiteSpace($BaseDir)) {
    if (Test-Path ".\.loop") {
        $BaseDir = "."
    } elseif (Test-Path "..\.loop") {
        $BaseDir = ".."
    } else {
        $BaseDir = "."
    }
}

$worktreesDir = Join-Path $BaseDir ".loop\worktrees"
$archivedDir  = Join-Path $BaseDir ".loop\archived_worktrees"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Worktree Archival & Cleanup Automation        " -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Check if .loop/worktrees directory exists
if (-not (Test-Path $worktreesDir)) {
    Write-Host "[!] Worktree directory not found at '$worktreesDir'. Nothing to archive or clean." -ForegroundColor Yellow
    exit 0
}

# 2. Archive specified RunId if provided
if (-not [string]::IsNullOrWhiteSpace($RunId)) {
    $sourcePath = Join-Path $worktreesDir $RunId
    $destPath   = Join-Path $archivedDir $RunId

    if (Test-Path $sourcePath) {
        Write-Host ""
        Write-Host "[*] Ensuring archive folder exists: $archivedDir" -ForegroundColor Green
        New-Item -ItemType Directory -Path $archivedDir -Force | Out-Null

        Write-Host "[*] Archiving worktree '$RunId' -> '$destPath'..." -ForegroundColor Green
        
        # Try moving via git worktree move to preserve git registration metadata
        $gitMove = git worktree move "$sourcePath" "$destPath" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[+] Successfully moved worktree via Git." -ForegroundColor Green
        } else {
            Write-Host "[-] git worktree move fallback: moving directory directly..." -ForegroundColor Yellow
            Move-Item -Path $sourcePath -Destination $destPath -Force
            Write-Host "[+] Successfully moved directory to archive." -ForegroundColor Green
        }
    } else {
        Write-Host ""
        Write-Host "[!] Source worktree '$RunId' was not found at '$sourcePath'. Skipping archival." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "[*] No RunId specified. Proceeding to clean up all worktrees..." -ForegroundColor Cyan
}

# 3. Clean up remaining worktrees
Write-Host ""
Write-Host "[*] Pruning Git worktree registrations..." -ForegroundColor Cyan
git worktree prune

Write-Host "[*] Removing remaining worktree directories in '$worktreesDir'..." -ForegroundColor Cyan
$remaining = Get-ChildItem -Path $worktreesDir -Directory -ErrorAction SilentlyContinue | 
    Where-Object { $_.Name -ne "archived_worktrees" }

if ($null -eq $remaining -or $remaining.Count -eq 0) {
    Write-Host "[+] No remaining worktrees to clean." -ForegroundColor Green
} else {
    foreach ($item in $remaining) {
        Write-Host "    - Cleaning: $($item.Name)" -ForegroundColor Gray
        git worktree remove $item.FullName --force 2>$null
        if (Test-Path $item.FullName) {
            Remove-Item $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# Final Git worktree prune check
git worktree prune

Write-Host ""
Write-Host "[OK] Worktree archival and cleanup complete!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
