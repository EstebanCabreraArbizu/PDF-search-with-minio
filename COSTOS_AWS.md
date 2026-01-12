# 💰 Reporte de Costos AWS - Despliegue en Producción

Este documento detalla una estimación mensual para desplegar el "Sistema de Búsqueda Inteligente" en AWS, optimizado para un volumen de ~10,000 PDFs con crecimiento mensual.

## 🏗️ Arquitectura de Referencia
- **Computo**: AWS App Runner (o EC2 t3.medium)
- **Base de Datos**: Amazon RDS for PostgreSQL (db.t4g.micro / small)
- **Almacenamiento**: Amazon S3 (en reemplazo de MinIO local)
- **Networking**: Application Load Balancer (ALB) + VPC

## 💵 Resumen de Costos Estimados (Mensual)

| Servicio | Configuración | Costo Est. (USD) | Notas |
| :--- | :--- | :--- | :--- |
| **AWS App Runner** | 1 vCPU / 2GB RAM | ~$35.00 | Escalado automático, gestionado. |
| **Amazon RDS (Postgres)** | db.t4g.small (Multi-AZ) | ~$45.00 | Alta disponibilidad y backups. |
| **Amazon S3** | 100 GB (Standard) | ~$2.30 | Almacenamiento de archivos. |
| **S3 Get/Put Requests** | 50,000 requests | ~$0.25 | Basado en volumen de uso. |
| **VPC / Data Transfer** | 10 GB Outbound | ~$0.90 | Transferencia de datos a internet. |
| **Application Load Balancer**| ALB Fijo | ~$18.00 | Si se usa App Runner, esto es opcional. |
| **TOTAL ESTIMADO** | | **~$101.45** | **Costo mensual aproximado** |

## 💡 Estrategias de Ahorro (Cost Optimization)

1. **Uso de Capa Gratuita (Free Tier)**:
   - Si la cuenta es nueva, el RDS t4g.micro y S3 (hasta 5GB) pueden salir a coste $0 el primer año.
   - App Runner tiene una capa gratuita para las primeras horas de computo.

2. **Reservas de Instancias (Reserved Instances)**:
   - Si el proyecto es a largo plazo (+1 año), reservar la instancia de RDS puede ahorrar hasta un **30-40%**.

3. **Ciclo de Vida de S3**:
   - Mover PDFs de años anteriores (ej. 2019-2022) a **S3 Intelligent-Tiering** o **Glacier** para reducir costos de almacenamiento en un **60%**.

4. **Instancias Spot (Opcional)**:
   - Para el motor de indexación (OCR), se podrían usar instancias Spot que son hasta **90% más baratas**, aunque no recomendadas para el API principal.

---
> [!NOTE]
> Estos costos son referenciales basándose en la calculadora de AWS (Enero 2026). Los precios pueden variar según la región (recomendado: us-east-1 o us-east-2).
