[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

$defaultArgs = @("--report-dir", "testdata/Regression-Growth-Tests-442", "--no-slack")
if (-not $Arguments -or $Arguments.Count -eq 0) {
    $Arguments = $defaultArgs
}

$venvPython = Join-Path "venv" "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Could not find $venvPython. Run scripts\windows\setup.ps1 first to create the virtual environment."
}

Write-Host "Using Python: $venvPython" -ForegroundColor Cyan
Write-Host "Running src/main.py $Arguments" -ForegroundColor Cyan

& $venvPython "src/main.py" $Arguments
exit $LASTEXITCODE

