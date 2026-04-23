# Configuración de entorno para npm

## Opción 1: Manual (Recomendada)

En PowerShell, ejecutar:

```powershell
$env:NPM_GITHUB_TOKEN = "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"
npm install
npm test
```

## Opción 2: Usar el archivo .env

```powershell
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        $name = $matches[1]
        $value = $matches[2]
        Set-Item -Path "env:$name" -Value $value
    }
}
npm install
```

## Nota
El archivo .npmrc ya está configurado para usar la variable ${NPM_GITHUB_TOKEN}.
No necesitas modificar .npmrc directamente.
