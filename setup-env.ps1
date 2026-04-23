# Script para configurar variables de entorno de npm en PowerShell
# Ejecutar: .\setup-env.ps1

Write-Host "Configurando entorno para npm..." -ForegroundColor Cyan

# Leer token del .env (si existe)
$envFile = ".\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $name = $matches[1]
            $value = $matches[2]
            Set-Item -Path "env:$name" -Value $value
            Write-Host "  Set $name" -ForegroundColor Green
        }
    }
} else {
    Write-Host "WARNING: .env file not found" -ForegroundColor Yellow
}

# Configurar .npmrc con el token directamente
$npmrcFile = ".\.npmrc"
if (Test-Path $npmrcFile) {
    $content = Get-Content $npmrcFile -Raw
    if ($env:NPM_GITHUB_TOKEN) {
        $content = $content -replace '\${NPM_GITHUB_TOKEN}', $env:NPM_GITHUB_TOKEN
        Set-Content -Path $npmrcFile -Value $content -NoNewline
        Write-Host "OK .npmrc configured with token" -ForegroundColor Green
    } else {
        Write-Host "WARNING: NPM_GITHUB_TOKEN not found in env" -ForegroundColor Yellow
    }
} else {
    Write-Host "WARNING: .npmrc file not found" -ForegroundColor Yellow
}

Write-Host "`nReady! Now run: npm install" -ForegroundColor Cyan
