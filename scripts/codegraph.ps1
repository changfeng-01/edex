# CodeGraph convenience wrapper
# Usage: .\scripts\codegraph.ps1 <command> [args...]
#   or:  npm run codegraph -- <command> [args...]

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$CodegraphBin = Join-Path $ProjectRoot "node_modules\@colbymchenry\codegraph-win32-x64\bin\codegraph.cmd"

if (-not (Test-Path $CodegraphBin)) {
    Write-Host "CodeGraph not installed. Run: npm install" -ForegroundColor Red
    exit 1
}

& $CodegraphBin @args
