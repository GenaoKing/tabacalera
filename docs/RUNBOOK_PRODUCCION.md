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
