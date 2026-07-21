$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $projectRoot "backend"

if (-not $env:OPENAI_API_KEY) {
    Write-Host "org.system needs an OpenAI API key for general GPT answers." -ForegroundColor Yellow
    Write-Host "The key is hidden while you type and is not written to this repository." -ForegroundColor DarkGray
    $secureKey = Read-Host "OpenAI API key" -AsSecureString
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
        Remove-Variable secureKey, keyPointer -ErrorAction SilentlyContinue
    }
}

$env:ORG_SYSTEM_LLM_MODE = "openai"
if (-not $env:OPENAI_MODEL) {
    $env:OPENAI_MODEL = "gpt-5.6-terra"
}

Set-Location $backendPath
Write-Host "Starting org.system with $env:OPENAI_MODEL at http://127.0.0.1:8000" -ForegroundColor Green
python -m uvicorn app.main:app --reload --port 8000
