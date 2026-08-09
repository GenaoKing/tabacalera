# Incidencias de datos pendientes

> Revisión: 2026-08-08. Este documento registra casos detectados; no autoriza correcciones automáticas.

## Avances sin venta ni cosecha

Existen siete filas activas de `Avance` que no tienen un `DetalleAvance`. Como `Avance` no posee una clave foránea directa a `Cosecha`, estos movimientos no pertenecen contablemente a una temporada hasta que sean revisados y vinculados manualmente a la cuenta semanal correcta.

| Avance ID | Cosechero ID | Fecha | Monto | Cosecha posible por rango | Estado de revisión |
|---:|---:|---|---:|---|---|
| 141641 | 20034 | 2023-09-30 | 50,000.00 | Cosecha 2023-2024 | Pendiente |
| 141642 | 20034 | 2023-09-30 | 50,000.00 | Cosecha 2023-2024 | Pendiente |
| 141643 | 20034 | 2023-09-30 | 50,000.00 | Cosecha 2023-2024 | Pendiente |
| 141644 | 20034 | 2023-09-30 | 50,000.00 | Cosecha 2023-2024 | Pendiente |
| 191660 | 20035 | 2024-05-24 | 24,750.00 | Cosecha 2023-2024 | Pendiente |
| 293364 | 20033 | 2024-11-11 | 1,500.00 | Cosecha 2024-2025 | Pendiente |
| 293365 | 20033 | 2024-11-11 | 8,000.00 | Cosecha 2024-2025 | Pendiente |

**Total pendiente de clasificación: 234,250.00.** La cosecha indicada es solo una referencia basada en el rango de fechas; no se usa para calcular saldos ni debe considerarse confirmada.

### Procedimiento futuro de resolución

1. Comparar cada avance con el documento bancario y el reporte firmado del cosechero.
2. Confirmar cosecha, sábado de cuenta y que no exista ya otro movimiento equivalente.
3. Vincularlo manualmente mediante una `Venta` de la cosecha confirmada y un `DetalleAvance` por el monto correcto.
4. Regenerar Dashboard, CSV y PDF y registrar aquí la evidencia de la corrección.

Hasta completar esos pasos, el dashboard, el CSV, el PDF y el comando de conciliación excluyen deliberadamente estas siete filas para evitar una asignación o duplicación incorrecta.
