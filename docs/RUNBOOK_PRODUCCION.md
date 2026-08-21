# Runbook de producción local

## Estado del cambio 2026-08-08

- Rama: `feature/venta-segura`.
- Commit de checkpoint previo: `ec5e74b` (`checkpoint: estabilizar interfaz y documentacion`).
- El servidor Django se detuvo antes del backup y de la migración.
- Migración aplicada: `ventas.0006_alter_detallearticulo_cantidad_operacionventa_and_more`.
- La migración conserva los detalles históricos, cambia `cantidad` a `decimal(10,2)`, crea `OperacionVenta` y deja las operaciones históricas en `NULL`.
- Los tickets históricos duplicados no se tocaron.

## Backup verificado

| Dato | Valor |
|---|---|
| Fecha local | 2026-08-08 19:24:29 (America/Santo_Domingo) |
| Base | `Tabacalera` |
| Servidor | `DESKTOP-VGQEGRL` |
| Backup SQL Server | `C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Backup\Tabacalera_pre_venta_segura_20260808_192429.bak` |
| Copia operativa | `C:\Tabacalera\backups\Tabacalera_pre_venta_segura_20260808_192429.bak` |
| Tamaño | 1,318,912 bytes |
| SHA-256 | `B10448D890AE1704EBCE4105973AD9DBFB83DFBD0F134258C5779C3FFA3EB717` |
| Opciones | `COPY_ONLY`, `CHECKSUM`, `COMPRESSION` |
| Verificación | `RESTORE VERIFYONLY WITH CHECKSUM` correcta; hashes de ambas copias idénticos |

## Checklist de despliegue

1. Confirmar que no haya usuarios registrando movimientos.
2. Detener `runserver` y cualquier proceso que escriba en la base.
3. Crear un nuevo backup `COPY_ONLY WITH CHECKSUM, COMPRESSION` si existen movimientos posteriores al backup de arriba.
4. Ejecutar `RESTORE VERIFYONLY WITH CHECKSUM` y copiar el BAK fuera de la carpeta de SQL Server.
5. Comparar tamaño y SHA-256 de ambas copias.
6. Ejecutar:

   ```powershell
   C:\Users\Santiago\anaconda3\envs\tabacalera\python.exe manage.py check
   C:\Users\Santiago\anaconda3\envs\tabacalera\python.exe manage.py migrate --plan
   C:\Users\Santiago\anaconda3\envs\tabacalera\python.exe manage.py migrate
   C:\Users\Santiago\anaconda3\envs\tabacalera\python.exe manage.py test --noinput
   npm run build
   C:\Users\Santiago\anaconda3\envs\tabacalera\python.exe manage.py collectstatic --noinput
   ```

7. Iniciar el portal y hacer smoke test autenticado de Dashboard, Ventas, Tickets, Cosecheros, Artículos y Proveedores.
   Confirmar además que `/static/img/tabacalera-genao-logo.png` responde y aparece en login, sidebar y Admin; generar un PDF para validar el uso server-side.
8. Registrar una operación controlada con cantidad decimal y comprobar inventario, ticket semanal y PDF.
9. Probar la impresora térmica USB real. Una falla debe devolver `503` y dejar la venta guardada y pendiente.

## Rollback confiable

Las cantidades fraccionarias hacen que el rollback de esquema mediante código no sea confiable. Si falla la migración o la validación productiva:

1. Detener Django y bloquear nuevas escrituras.
2. Conservar logs y el estado fallido para diagnóstico.
3. Restaurar el BAK verificado en SQL Server sobre `Tabacalera`, usando acceso exclusivo.
4. Volver al commit de checkpoint `ec5e74b` o al commit de fase aprobado.
5. Ejecutar `manage.py check`, iniciar el portal y comprobar el último movimiento anterior al backup.

La restauración elimina todos los movimientos posteriores a la fecha del BAK; por eso debe coordinarse con la operación y nunca ejecutarse con usuarios trabajando.

## Configuración local

La configuración sensible vive en `.env`, ignorado por Git. `.env.example` documenta todas las variables. Cambiar `DJANGO_SECRET_KEY` invalida las sesiones existentes y requiere volver a iniciar sesión. El portal usa la zona horaria `America/Santo_Domingo`.

## Despliegue del universo financiero completo

- No contiene migraciones ni modifica filas productivas.
- Antes de reiniciar, ejecutar `manage.py check`, `makemigrations --check --dry-run`, la suite completa y `npm run build`.
- Verificar los conteos esperados 49, 74 y 71 para las cosechas 2023-2024, 2024-2025 y 2025-2026.
- Confirmar que los siete avances de `INCIDENCIAS_DATOS.md` permanezcan sin `DetalleAvance` y fuera de los totales.
- Rollback: detener Django, volver al commit inmediatamente anterior de esta fase y reiniciar. No se restaura base porque no hay cambio de esquema ni datos.

## Incidente local de base temporal — 2026-08-09

Una ejecución de `manage.py test` agotó el tiempo del terminal mientras SQL Server creaba `test_Tabacalera`. El proceso Python hijo continuó activo y la base temporal quedó iniciando recuperación; las siguientes conexiones locales comenzaron a responder de forma intermitente.

Evidencia y resolución:

- `Tabacalera` permaneció `ONLINE`, `MULTI_USER` y `READ_WRITE`, sin sesiones de usuario ni transacciones abiertas.
- Se detuvieron únicamente los procesos de prueba bloqueados y se eliminó `test_Tabacalera` después de confirmar que no tenía conexiones.
- La suite volvió a crear y destruir correctamente la base temporal.
- Ante la latencia residual de conexiones, se puso solamente `Tabacalera` offline/online con `ROLLBACK IMMEDIATE` cuando Django estaba detenido y no había sesiones activas.
- `DBCC CHECKDB (N'Tabacalera') WITH PHYSICAL_ONLY, NO_INFOMSGS` terminó sin reportar errores.
- No hubo migraciones, restauraciones, cambios de filas ni reinicio efectivo del servicio SQL Server.

Si reaparece, no interrumpir repetidamente la creación de la base de pruebas. Identificar primero el PID exacto de `manage.py test`, comprobar conexiones a `test_Tabacalera` y actuar solo sobre esa base temporal. Nunca eliminar ni restaurar `Tabacalera` para resolver un bloqueo de pruebas.

## Despliegue del CRUD de avances — 2026-08-11

- No contiene migraciones de esquema ni corrige automáticamente filas históricas.
- Requiere `npm run build` porque incorpora nuevas plantillas Tailwind.
- Antes de habilitar edición/desactivación, detener escrituras y crear un backup nuevo `COPY_ONLY WITH CHECKSUM, COMPRESSION`, verificarlo y copiarlo a `C:\Tabacalera\backups` con hash coincidente.
- Ejecutar `manage.py check`, `makemigrations --check --dry-run` y la suite MSSQL cuando el servidor acepte conexiones nuevas.
- Smoke autenticado mínimo: tabla por defecto, filtro Sin cosecha, alta idempotente, corrección dentro de la misma semana, movimiento entre semanas, desactivación y restauración.
- Confirmar al centavo la misma cifra en detalle de avance, ticket, Dashboard y PDF.
- La reversión de código consiste en volver al commit anterior. Como no existe historial de edición, una corrección productiva ya confirmada debe repararse manualmente o recuperarse desde backup coordinando la pérdida de movimientos posteriores.

Durante la implementación, 29 pruebas relevantes pasaron en SQLite aislado. Los intentos de crear/conectar la base de pruebas MSSQL agotaron el tiempo de login; se detuvo únicamente el proceso de pruebas y se dejó intacto el `runserver` productivo. No reiniciar SQL Server ni eliminar bases para completar esta verificación mientras haya usuarios trabajando.

### Backup previo a habilitar el CRUD de avances

| Dato | Valor |
|---|---|
| Fecha local | 2026-08-11 18:59:16 (America/Santo_Domingo) |
| Base | `Tabacalera` |
| Servidor | `DESKTOP-VGQEGRL` mediante Shared Memory (`lpc`) |
| Commit respaldado | `9858e25` (`feat: agregar CRUD operativo de avances`) |
| Backup SQL Server | `C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Backup\Tabacalera_pre_crud_avances_20260811_185916.bak` |
| Copia operativa | `C:\Tabacalera\backups\Tabacalera_pre_crud_avances_20260811_185916.bak` |
| Tamaño | 1,396,736 bytes |
| SHA-256 | `BF80B284D940CB9767D8C2E2100C0F3A284CA36709F8EA19DA0771A330BBCEE1` |
| Opciones | `COPY_ONLY`, `CHECKSUM`, `COMPRESSION` |
| Verificación | `RESTORE VERIFYONLY WITH CHECKSUM` correcta; tamaño y SHA-256 idénticos en ambas copias |

Después de verificar las dos copias se detuvo exclusivamente el proceso Django PID `49680`, que ejecutaba `manage.py runserver 127.0.0.1:8000 --noreload`. El puerto 8000 quedó libre y el servicio `MSSQLSERVER` permaneció en ejecución. El reinicio del portal queda a cargo del operador desde la terminal de VS Code.

## Despliegue del formato numérico uniforme — 2026-08-13

- Es un cambio exclusivo de presentación; no contiene migraciones ni escrituras de datos y no exige backup de base.
- Ejecutar `manage.py check`, `makemigrations --check --dry-run` y la suite completa.
- No requiere recompilar Tailwind porque no incorpora clases nuevas.
- En un despliegue con `DEBUG=False`, ejecutar `collectstatic --noinput` para publicar `static/js/number-format.js` antes de reiniciar Django.
- Smoke visual: comprobar Dashboard, lista/detalle de Avances, Tickets, Ventas, Compras, Cosecheros y un PDF. Un valor de diez mil debe aparecer como `10,000.00`.
- Verificar que los inputs y payloads continúen enviando `10000.00` sin coma.
- Rollback: volver al commit anterior y repetir `collectstatic`; no restaurar SQL Server.

## Corrección puntual del ticket de Demetrio Martínez — 2026-08-16

Se corrigió exclusivamente el ticket `365067`, de Demetrio Martínez (`cosechero_id=20016`) en la cosecha `10002`. Se eliminaron las líneas `DetalleArticulo 334006` (35.00 tareas de Arada Corte) y `334007` (35.00 tareas de Arada Cruce), ambas a `270.00` por tarea. La rebaja fue `18,900.00` y el ticket pasó de `73,390.00` a `54,490.00`.

La operación se ejecutó dentro de una transacción con bloqueo y precondiciones exactas. Se restituyeron 35.00 unidades a los lotes `170194` y `170195`, que quedaron en `8,422.00` y `6,717.00`, respectivamente. El ticket quedó con Arada Corte `45.00`, Arada Cruce `102.00`, Arada Sulcos `50.00`, un avance activo de `6,300.00` y `impreso=False`. Los detalles eliminados se verificaron ausentes y `manage.py check` terminó sin hallazgos.

| Dato | Valor |
|---|---|
| Fecha local | 2026-08-16 13:50:41 (America/Santo_Domingo) |
| Backup SQL Server | `C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Backup\Tabacalera_pre_ajuste_demetrio_20260816_135040.bak` |
| Copia operativa | `C:\Tabacalera\backups\Tabacalera_pre_ajuste_demetrio_20260816_135040.bak` |
| Tamaño de cada copia | 1,486,848 bytes |
| SHA-256 | `3145CC764C39D40D9920CB33F5FDF8C2A49915C03EE512F48EBC511572FEFB25` |
| Opciones | `COPY_ONLY`, `CHECKSUM`, `COMPRESSION` |
| Verificación | `RESTORE VERIFYONLY WITH CHECKSUM` correcta; tamaño y SHA-256 idénticos |

Rollback de datos: restaurar este BAK exige detener el portal y descarta todos los movimientos posteriores al backup. Si existen movimientos posteriores, se debe preferir una corrección manual inversa y conservar evidencia.
