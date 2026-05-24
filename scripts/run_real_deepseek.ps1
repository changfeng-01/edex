param(
    [string]$EnvFile = ".env",
    [string]$OutputMd = "examples/demo_run/llm_parameter_analysis_real.md",
    [string]$OutputJson = "examples/demo_run/llm_parameter_analysis_real.json"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $RepoRoot $EnvFile

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw "Missing $EnvFile. Copy .env.example to .env and set DEEPSEEK_API_KEY locally."
}

$Key = $null
foreach ($Line in Get-Content -LiteralPath $EnvPath -Encoding UTF8) {
    $Trimmed = $Line.Trim()
    if ($Trimmed.Length -eq 0 -or $Trimmed.StartsWith("#")) {
        continue
    }
    $Parts = $Trimmed -split "=", 2
    if ($Parts.Count -eq 2 -and $Parts[0].Trim() -eq "DEEPSEEK_API_KEY") {
        $Key = $Parts[1].Trim().Trim('"').Trim("'")
        break
    }
}

if ([string]::IsNullOrWhiteSpace($Key) -or $Key -eq "your_deepseek_api_key_here") {
    throw "DEEPSEEK_API_KEY is missing in $EnvFile."
}

$env:DEEPSEEK_API_KEY = $Key

Push-Location $RepoRoot
try {
    python -m goa_eval.cli analyze-params `
        --summary examples/demo_run/real_summary.json `
        --score examples/demo_run/score_summary.json `
        --metrics examples/demo_run/real_metrics.csv `
        --candidates examples/demo_run/next_candidates.csv `
        --params examples/sample_params.yaml `
        --model deepseek-v4-pro `
        --output-md $OutputMd `
        --output-json $OutputJson
}
finally {
    Remove-Item Env:\DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host "Real DeepSeek analysis written to $OutputMd and $OutputJson"
