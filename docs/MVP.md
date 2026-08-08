# Roadmap integral — Tabacalera Genao

## Resumen

El trabajo continuará por fases pequeñas, verificables y documentadas. La prioridad inmediata será asegurar el registro de ventas; después se completarán Tickets, CRUD operativos, dashboard financiero y hardening.

Decisiones confirmadas:

- Una venta agrupa movimientos por `cosechero + cosecha + sábado`.
- El cierre semanal será informativo, no bloqueará movimientos.
- **Guardar** acumula sin imprimir.
- **Registrar e imprimir** acumula y luego imprime el ticket semanal completo.
- Los borradores vivirán en `sessionStorage`.
- Los artículos permiten cantidades decimales.
- Los duplicados históricos identificados no se modificarán.
- Proveedores y artículos tendrán CRUD visual.
- Toda modificación de esquema productivo exige backup verificado.

## Fases de implementación

### 0. Seguridad, Git y documentación

- Crear `feature/venta-segura` y realizar un commit de checkpoint con el estado visual actual.
- Detener temporalmente escrituras antes de migrar.
- Crear un backup `COPY_ONLY` con `CHECKSUM` y compresión en la carpeta oficial de SQL Server.
- Ejecutar `RESTORE VERIFYONLY WITH CHECKSUM`.
- Copiar el BAK a `C:\Tabacalera\backups` y comparar SHA-256.
- Registrar fecha, archivo, tamaño, hash, migraciones y procedimiento de rollback en `docs/RUNBOOK_PRODUCCION.md`.
- Mantener:
  - `PLAN_MEJORA.md`: tareas, estados, fechas, commits y evidencia.
  - `ARQUITECTURA.md`: estado técnico vigente.
  - `DECISIONES.md`: reglas de negocio estables y decisiones tomadas.

### 1. Venta segura e idempotente

- Migrar `DetalleArticulo.cantidad` de entero a `decimal(10,2)`; conservar datos históricos y rechazar nuevas cantidades menores o iguales a cero.
- Crear `OperacionVenta` para auditar cada envío:
  - UUID único de idempotencia.
  - Venta semanal asociada.
  - Usuario.
  - Fecha real del movimiento.
  - Fecha/hora de registro.
  - Hash del payload.
  - Total agregado.
  - Indicador de impresión solicitada.
- Asociar los nuevos detalles de artículos y avances con su operación; los detalles históricos quedarán sin operación.
- Si se repite una clave con el mismo payload, devolver el resultado existente sin consumir inventario ni duplicar avances.
- Si la misma clave llega con contenido diferente, responder `409`.
- Usar un bloqueo transaccional MSSQL por `cosechero + cosecha + sábado` para evitar dos cuentas semanales nuevas concurrentes.
- Buscar la venta semanal por cosechero, cosecha y sábado exacto. Si una semana histórica tiene varios tickets activos, rechazar nuevas modificaciones con un mensaje explícito; no consolidarla automáticamente.
- Marcar `impreso=False` cada vez que se agregue un movimiento después de una impresión.

### 2. Captura AJAX y experiencia de venta

- Enviar el formulario sin recargar la página y mostrar errores inline.
- Mantener cosechero, cosecha, fecha, artículos y avances ante errores de validación.
- Guardar el borrador en una clave de `sessionStorage` separada por usuario:
  - Restauración visible al recargar la pestaña.
  - Expiración a las 24 horas.
  - Botón para descartar.
  - Limpieza inmediata después de un guardado confirmado.
- Generar la UUID con `crypto.randomUUID()` y conservarla durante reintentos.
- Reconciliar al restaurar el borrador con inventario y precios actuales; el servidor seguirá siendo la autoridad final.
- Sustituir los 90 botones de cosechero por un arreglo JSON en memoria, búsqueda normalizada y máximo de ocho resultados.
- Mostrar una tarjeta semanal con sábado de cierre, existencia del ticket y total acumulado.
- Admitir cantidades con dos decimales en carrito, FIFO, totales, ticket térmico y PDF.
- Reemplazar `alert()` por mensajes visuales accesibles y estados claros de envío.

### 3. Impresión desacoplada

- El guardado responderá antes de acceder a la impresora.
- Cambiar la impresión a `POST /ventas/imprimir/<venta_id>/`; ningún `GET` producirá efectos.
- Flujo de **Registrar e imprimir**:
  1. Guardar operación.
  2. Limpiar el borrador tras confirmación.
  3. Solicitar impresión del acumulado semanal completo.
  4. Mostrar `Guardado`, `Imprimiendo`, `Impreso` o `Guardado; impresión fallida`.
- Una falla USB nunca revertirá la venta.
- Permitir reintentar desde la confirmación o desde Tickets.
- Solo una impresión exitosa marcará `Venta.impreso=True`.

### 4. Tickets escalables

- Paginar en servidor a 50 filas.
- Incorporar filtros GET por cosecha, cosechero, fecha inicial y fecha final.
- Conservar filtros al cambiar de página.
- Evitar renderizar los 3,633 tickets actuales en el DOM.
- Mantener detalle AJAX y cambiar la acción de impresión a POST.
- Mostrar claramente tickets pendientes de reimpresión después de nuevos movimientos.

### 5. CRUD y altas rápidas

- Crear CRUD Tailwind para cosecheros, proveedores y artículos.
- Mantener soft-delete y mostrar únicamente registros activos en operación.
- Normalizar cuentas bancarias vacías a `NULL`.
- Corregir el validador de cédula para rechazar caracteres no numéricos con mensajes claros.
- Agregar alta rápida de cosechero desde Ventas sin perder el borrador.
- Agregar alta rápida de artículo seleccionando un proveedor existente; la creación de proveedores permanecerá en su pantalla dedicada.
- Mantener Django Admin para soporte técnico, no como interfaz operativa principal.

### 6. Dashboard financiero por cosecha

- Convertir el dashboard principal en un resumen seleccionable por cosecha.
- Reutilizar la fuente única de cálculo existente:
  - Total que los cosecheros deben a Tabacalera.
  - Total que Tabacalera debe a los cosecheros.
  - Balance neto.
  - Cantidad de cosecheros en cada grupo.
- Incluir dos tablas: “Nos deben” y “Les debemos”, con búsqueda, orden y acceso al PDF individual.
- Agregar exportación CSV.
- No persistir un saldo duplicado: se calculará desde artículos, avances y producción.

### 7. Hardening y cierre del roadmap

- Centralizar `proximo_sabado()` en un módulo compartido.
- Marcar como resueltos los pendientes obsoletos del plan.
- Mover `SECRET_KEY`, `DEBUG`, hosts y rutas sensibles a configuración de entorno.
- Añadir favicon local y eliminar dependencias visuales externas cuando sea práctico.
- Ejecutar una revisión final de permisos y separar roles solo si la operación real lo requiere.

## Interfaces

- `GET /ventas/resumen-semanal/?cosechero=&cosecha=&fecha=` devolverá sábado, ticket, total y existencia.
- `POST /ventas/` aceptará `Idempotency-Key` y devolverá JSON con venta, operación, total semanal, estado de replay y URL de impresión.
- Errores de validación devolverán `400`; reutilización conflictiva de clave, `409`.
- `POST /ventas/imprimir/<id>/` devolverá JSON y `503` si falla el hardware, sin revertir la venta.
- Tickets usarán `?cosecha=&q=&desde=&hasta=&page=`.
- Los endpoints de alta rápida devolverán el nuevo objeto para insertarlo inmediatamente en los selectores.

## Pruebas y aceptación

- Dos solicitudes iguales con la misma UUID producen una sola operación, un solo descuento FIFO y un solo avance.
- Dos usuarios registrando simultáneamente en la misma semana reutilizan una sola venta.
- Una cantidad `0.5` se conserva exactamente en inventario, venta, PDF y ticket térmico.
- Errores de inventario o validación mantienen intacto el borrador y no modifican la base.
- Una falla o desconexión de impresora deja la venta guardada y pendiente de impresión.
- Un movimiento nuevo sobre un ticket impreso vuelve a marcarlo pendiente.
- Los cuatro tickets históricos duplicados permanecen sin cambios.
- Tickets pagina y filtra correctamente con el volumen productivo actual.
- CRUD respeta validadores, unicidad y soft-delete.
- Dashboard y PDF producen los mismos saldos.
- Antes del despliegue: `manage.py check`, migraciones en dry-run, suite completa, smoke test autenticado, prueba real de impresora y verificación del backup.

## Rollback y seguimiento

- No ejecutar migraciones sin backup verificado y confirmación explícita.
- Si falla la migración o la validación productiva, detener el servicio, restaurar el BAK y volver al commit de checkpoint.
- Cada fase termina con tests, actualización documental y un commit independiente antes de iniciar la siguiente.
- Las migraciones de decimal e idempotencia no se considerarán reversibles mediante código una vez que existan cantidades fraccionarias; el rollback confiable será restaurar el backup.
