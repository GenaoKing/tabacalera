# Incidencias de datos pendientes

> Revisión: 2026-08-11. Este documento registra casos detectados; no autoriza correcciones automáticas.

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

### Procedimiento de resolución disponible

1. Comparar cada avance con el documento bancario y el reporte firmado del cosechero.
2. Confirmar cosecha, sábado de cuenta y que no exista ya otro movimiento equivalente.
3. Abrir `/avances/?sin_cosecha=1`, revisar el avance y usar **Vincular a cosecha** con la cosecha, cosechero y fecha confirmados. El servicio crea o reutiliza la cuenta semanal exacta y genera un solo `DetalleAvance`.
4. Regenerar Dashboard, CSV y PDF y registrar aquí la evidencia de la corrección.

Hasta completar esos pasos, el dashboard, el CSV, el PDF y el comando de conciliación excluyen deliberadamente estas siete filas para evitar una asignación o duplicación incorrecta.

La implementación del CRUD no vinculó ni modificó automáticamente ninguno de estos siete casos.

## Correcciones manuales realizadas

### Entrega 60117 — 2026-08-09

- Solicitud: la última entrega creada había sido asignada por error a Luciano Andrés López (`Cosechero 50009`).
- Verificación: `EntregaTabaco 60117`, fecha operativa 2026-06-29, cosecha 2025-2026, variedad Criollo 98.
- Corrección: se cambió únicamente `cosechero_id` de `50009` a Víctor Paulino (`20017`) dentro de una transacción con bloqueo y comprobación del propietario anterior.
- Permanecieron sin cambios la fecha, cosecha, variedad y todas las cantidades.
- Verificación posterior: la fila `60117` pertenece a Víctor Paulino.
