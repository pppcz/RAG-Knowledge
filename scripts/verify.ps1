# Environment / stage acceptance checks (ASCII-only on purpose: PowerShell 5.1
# reads BOM-less scripts as ANSI, so non-ASCII text would be mangled).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\verify.ps1 [-Full]
param(
    [switch]$Full
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$script:failed = 0

function Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host ''
    Write-Host "===== $Name =====" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    $code = 0
    try {
        & $Action
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        $code = 1
    }
    if ($code -ne 0) {
        Write-Host "[FAIL] $Name (exit $code)" -ForegroundColor Red
        $script:failed++
    } else {
        Write-Host "[OK] $Name" -ForegroundColor Green
    }
}

Step 'docker info' {
    docker info --format 'Server {{.ServerVersion}} / {{.OSType}} / {{.Architecture}}'
}

Step 'uv --version' { uv --version }

Step 'python (uv) version' { uv run python --version }

Step 'ports 5433/6379/9000/9001' {
    foreach ($p in 5433, 6379, 9000, 9001) {
        $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        if ($c) { Write-Host ("  {0} LISTEN" -f $p) } else { Write-Host ("  {0} FREE" -f $p) }
    }
}

Step 'docker compose ps' { docker compose ps }

Step 'ruff check' { uv run ruff check . }

Step 'pytest' { uv run pytest }

if ($Full) {
    Step 'alembic upgrade head' { uv run alembic upgrade head }

    Step 'seed default tenant / admin' { uv run python -m scripts.seed }

    $listening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($listening) {
        Step 'GET /health' {
            $body = curl.exe -s -f http://localhost:8000/health
            if ($LASTEXITCODE -eq 0) { Write-Host $body }
        }

        Step 'POST /api/auth/login + GET /api/auth/me' {
            # JSON goes through a temp file: PowerShell 5.1 strips quotes from native args
            $payloadFile = Join-Path $env:TEMP 'rag-login.json'
            Set-Content -Path $payloadFile -Value '{"username":"admin","password":"123456"}' -Encoding ascii
            try {
                $login = curl.exe -s -f -X POST http://localhost:8000/api/auth/login `
                    -H "Content-Type: application/json" -d "@$payloadFile"
                if ($LASTEXITCODE -ne 0) { throw 'login failed' }
                $token = ($login | ConvertFrom-Json).access_token
                if (-not $token) { throw 'no access_token in response' }
                $script:token = $token
                Write-Host "access_token length=$($token.Length)"
                $me = curl.exe -s -f http://localhost:8000/api/auth/me -H "Authorization: Bearer $token"
                if ($LASTEXITCODE -ne 0) { throw 'GET /api/auth/me failed' }
                Write-Host $me
            } finally {
                Remove-Item -Path $payloadFile -ErrorAction SilentlyContinue
            }
        }

        Step 'GET /api/kb + GET /api/docs' {
            if (-not $script:token) { throw 'no token from login step' }
            $headers = "Authorization: Bearer $($script:token)"
            $kbs = curl.exe -s -f "http://localhost:8000/api/kb?page=1&page_size=5" -H $headers
            if ($LASTEXITCODE -ne 0) { throw 'GET /api/kb failed' }
            $parsedKbs = $kbs | ConvertFrom-Json
            Write-Host "knowledge_bases total=$($parsedKbs.total)"
            $script:kbId = 0
            if ($parsedKbs.total -gt 0) { $script:kbId = $parsedKbs.items[0].id }
            $docs = curl.exe -s -f "http://localhost:8000/api/docs?page=1&page_size=5" -H $headers
            if ($LASTEXITCODE -ne 0) { throw 'GET /api/docs failed' }
            Write-Host "documents total=$(($docs | ConvertFrom-Json).total)"
        }

        Step 'GET /api/kb/search (vector search)' {
            if (-not $script:token) { throw 'no token from login step' }
            if (-not $script:kbId) {
                Write-Host 'no knowledge base yet, skipping search check' -ForegroundColor Yellow
                return
            }
            $headers = "Authorization: Bearer $($script:token)"
            # Query text is percent-encoded ASCII on purpose (this file stays ASCII-only):
            # %E6%8A%A5%E9%94%80%E6%B5%81%E7%A8%8B = Reimbursement process (bai xiao liu cheng)
            $url = "http://localhost:8000/api/kb/search?kb_id=$($script:kbId)&q=%E6%8A%A5%E9%94%80%E6%B5%81%E7%A8%8B&top_k=3"
            $result = curl.exe -s -f $url -H $headers
            if ($LASTEXITCODE -ne 0) { throw 'GET /api/kb/search failed' }
            $parsed = $result | ConvertFrom-Json
            Write-Host "search kb_id=$($parsed.kb_id) total=$($parsed.total)"
            if ($parsed.total -gt 0) {
                $topScore = $parsed.items[0].score
                Write-Host "top score=$topScore file=$($parsed.items[0].filename)"
                if ($topScore -le 0) { throw 'top hit score is not positive' }
            } else {
                Write-Host 'no chunks indexed yet, search returned 0 hits' -ForegroundColor Yellow
            }
        }
        Step 'POST /api/chat/ask (SSE stream)' {
            if (-not $script:token) { throw 'no token from login step' }
            if (-not $script:kbId) {
                Write-Host 'no knowledge base yet, skipping chat check' -ForegroundColor Yellow
                return
            }
            $headers = "Authorization: Bearer $($script:token)"
            # JSON \u escapes keep this file ASCII-only:
            # question = "reimbursement process?" (bao xiao liu cheng shi shen me)
            $payloadPath = Join-Path $env:TEMP 'rag-chat.json'
            $payload = '{"kb_id":' + $script:kbId + ',"question":"\u62a5\u9500\u6d41\u7a0b\u662f\u4ec0\u4e48\uff1f"}'
            Set-Content -Path $payloadPath -Value $payload -Encoding ascii
            try {
                $stream = curl.exe -N -s -X POST "http://localhost:8000/api/chat/ask" `
                    -H "Content-Type: application/json" -H $headers -d "@$payloadPath"
                if ($LASTEXITCODE -ne 0) { throw 'POST /api/chat/ask failed' }
                $messageEvents = ($stream | Select-String -Pattern '^event: message').Count
                $doneEvents = ($stream | Select-String -Pattern '^event: done').Count
                Write-Host "sse message events=$messageEvents done events=$doneEvents"
                if ($messageEvents -lt 1) { throw 'no SSE message events' }
                if ($doneEvents -ne 1) { throw 'no SSE done event' }
            } finally {
                Remove-Item -Path $payloadPath -ErrorAction SilentlyContinue
            }
        }
    } else {
        Write-Host ''
        Write-Host 'Backend is not listening on :8000, skipping online API checks' -ForegroundColor Yellow
    }
}

Write-Host ''
if ($script:failed -gt 0) {
    Write-Host "Failed steps: $($script:failed)" -ForegroundColor Red
    exit 1
}
Write-Host 'All acceptance checks passed' -ForegroundColor Green
exit 0
