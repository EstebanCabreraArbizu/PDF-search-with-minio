# 📖 Manual de Usuario - Sistema de Búsqueda Inteligente

Bienvenido al sistema de gestión y búsqueda de planillas. Este documento le guiará a través de las funciones principales del sistema.

## 🔐 1. Acceso al Sistema
1. Abra su navegador y acceda a la URL proporcionada.
2. Ingrese su **Usuario** y **Contraseña**.
3. Haga clic en **"Iniciar Sesión"**.

> [!IMPORTANT]
> Los permisos varían según su rol:
> - **Usuario**: Puede buscar y descargar documentos.
> - **Administrador**: Puede además subir archivos, gestionar carpetas y sincronizar el índice.

---

## 🔍 2. Búsqueda de Documentos

### 🧪 Búsqueda Simple
Ideal para encontrar documentos específicos de un solo empleado.
1. Ingrese el **DNI o Código de Empleado**.
2. **Filtros**: Seleccione Año, Mes o Razón Social para refinar los resultados.
3. **Tipo de Documento**: Empiece a escribir (ej: "VACACIONS") y el sistema le sugerirá opciones.
4. Presione **"Buscar"**.

### 📋 Búsqueda Masiva
Para procesos de auditoría o descargas de grupos grandes.
1. Vaya a la pestaña **"Búsqueda Masiva"**.
2. Pegue los códigos (separados por comas o saltos de línea).
3. Aplique los filtros de año/mes/banco.
4. El sistema le mostrará un resumen de quiénes tienen documentos y quiénes no.

---

## 📥 3. Descarga y Fusión (Merge)
- **Descarga Individual**: Haga clic en el botón de descarga al lado del archivo.
- **Fusión (Merge)**: Si tiene múltiples resultados, haga clic en **"Fusionar en un solo PDF"**. El sistema combinará todos los documentos en un solo archivo para facilitar su impresión o envío.

---

## ⚙️ 4. Gestión de Archivos (Solo Administradores)

### 📤 Subir Archivos
1. Diríjase a **"Gestión de Archivos"**.
2. Use el explorador para situarse en la carpeta correcta.
3. Arrastre sus archivos PDF al área sombreada.
4. Haga clic en **"Subir e Indexar"**. El sistema leerá automáticamente el contenido (OCR) y lo hará buscable de inmediato.

### 🔄 Sincronización
Si subió archivos directamente al storage (MinIO/S3), use el botón **"Sincronizar Índice"** para que el buscador los reconozca.

---

## 🛠️ 5. Solución de Problemas Comunes

- **"No se encuentran resultados"**: Asegúrese de que el código sea correcto y que el año/mes coincidan.
- **"Error al fusionar"**: El sistema permite hasta 100 archivos por fusión. Si necesita más, realice búsquedas parciales.
- **"Sesión expirada"**: Por seguridad, la sesión dura un tiempo determinado. Si ve este mensaje, vuelva a iniciar sesión.

---
**Desarrollado por**: Esteban Cabrera Arbizu  
**Versión**: 1.0.0
