# Plan de mejora — Tabacalera

> Última auditoría de código: 2026-08-09. Ver [ARQUITECTURA.md](ARQUITECTURA.md) para el mapa del sistema referenciado aquí.

## Ejecución del roadmap integral — 2026-08-08

| Fase | Estado | Evidencia principal |
|---|---|---|
| Seguridad, Git y backup | Completada | rama `feature/venta-segura`, checkpoint `ec5e74b`, BAK verificado en `RUNBOOK_PRODUCCION.md` |
| Venta decimal e idempotente | Completada | `b067583`, migración `ventas.0006`, `OperacionVenta`, bloqueo MSSQL y pruebas de replay/conflicto/FIFO |
| Captura AJAX y borrador | Completada | `9e5ffce`, `ventas_form_v2.html`, `sessionStorage` 24 h, búsqueda normalizada y resumen semanal |
| Impresión desacoplada | Completada en código | POST separado y `503` sin rollback; falta prueba física final de la USB |
| Tickets escalables | Completada | filtros GET, paginación de 50 y POST de impresión |
| CRUD y altas rápidas | Completada | `9e5ffce`, cosecheros, artículos y proveedores; soft-delete y validaciones |
| Dashboard financiero | Completada | `7207a7c`, resumen por cosecha, grupos de saldo, PDF y CSV desde cálculo común |
| Hardening | Completada en código | `fc2e197`, entorno, zona horaria, favicon, recursos locales; smoke autenticado correcto, pendiente impresora física |
| Universo financiero completo | Completada | `e22cb74`, unión de entregas y ventas, actividad operativa, flujo `Decimal`, incidencias y consultas constantes |
| Indicadores promedio por tarea | Completada | `dbfe259`, cards ponderados de gasto y producción, protección sin terreno y pruebas de presentación |

## Fase 9 — Indicadores promedio por tarea

- [x] Calcular gasto total y producción valorizada total desde el universo financiero completo.
- [x] Dividir ambos totales entre la suma `Decimal` de tareas registradas en las fichas de los cosecheros del universo.
- [x] Mantener los indicadores independientes de la búsqueda y del filtro “Sin producción”.
- [x] Mostrar dos cards responsive con el denominador utilizado.
- [x] Evitar división por cero y mostrar un estado explícito sin datos.
- [x] Documentar que el terreno actual no conserva historial por cosecha.
- [x] Probar cifras, renderizado y caso sin tareas.

No hay migración ni cambio de datos. Como paso futuro, se evaluará guardar el terreno por `cosechero + cosecha` si la empresa necesita comparaciones históricas exactas entre temporadas.

**Validación**: commit `dbfe259`; 21 pruebas aprobadas, `manage.py check` limpio, ninguna migración pendiente y Tailwind recompilado.

## Fase 8 — Universo financiero completo por cosecha

**Objetivo**: que la conciliación incluya a todo cosechero con actividad, aunque aún no haya entregado tabaco, sin duplicar saldos ni asignar avances ambiguos.

- [x] Construir la unión de entregas y ventas activas por cosecha en una fuente financiera única.
- [x] Separar artículos, avances, gastos, producción y saldo usando `Decimal` de extremo a extremo.
- [x] Incorporar fecha, tipo y precisión de la última actividad.
- [x] Alertar y etiquetar cuentas con gastos pero sin producción entregada.
- [x] Añadir filtro `sin_produccion=1` y ampliar el CSV.
- [x] Hacer que Dashboard, PDF, CSV y comando consuman la misma conciliación.
- [x] Corregir el importador para buscar por `cosechero + cosecha + sábado`.
- [x] Documentar siete avances huérfanos sin inferir ni modificar su cosecha.
- [x] Añadir pruebas de universo, Decimal, actividad, paridad y consultas constantes.

**Evidencia productiva antes → después**:

| Cosecha | Universo anterior | Universo completo | Sin entregas |
|---|---:|---:|---:|
| 2023-2024 | 43 | 49 | 6 |
| 2024-2025 | 60 | 74 | 14 |
| 2025-2026 | 0 | 71 | 71 |

Esta fase no agrega modelos ni migraciones y no modifica datos históricos. Su rollback consiste en volver al commit anterior del código.

**Commit de implementación**: `e22cb74` (`feat: completar universo financiero por cosecha`).

Validación final: `manage.py check` sin hallazgos, migraciones sin pendientes, Tailwind compilado, `collectstatic` correcto, 20 pruebas aprobadas y smoke autenticado `200` en Dashboard, filtro, CSV y PDF. Los puntos que exigen hardware real no se consideran verificados hasta probar la impresora conectada.

## Por qué existe este documento

El reporte del usuario fue que la UI/UX actual **ralentiza el trabajo diario**, mencionando puntualmente el registro de facturas (tickets de venta) y la creación de cheques (avances). Una auditoría del código confirmó que esto no es solo percepción de "UI vieja" — hay causas técnicas concretas y medibles: queries N+1 en cada carga del formulario de venta, una tormenta de señales que recalcula el total de la venta varias veces de más por cada línea agregada, impresión térmica síncrona bloqueando la respuesta HTTP, pérdida del carrito completo ante un error de validación, y un selector de cosechero que escala mal con el DOM.

El roadmap está ordenado por **impacto en la queja reportada vs. esfuerzo**, no por orden alfabético de apps. Cada fase es ejecutable de forma independiente y deja el sistema en un estado consistente.

## Cómo usar este documento

Cada tarea cita `archivo:línea` como estaba en la auditoría — verificar que sigue vigente antes de tocar, el código se mueve. Marcar con `[x]` cuando una tarea se complete y anotar la fecha; no borrar tareas completadas, sirven de historial.

---

## Fase 0 — Quick wins en el flujo actual

**Objetivo**: sin rediseñar nada visualmente, eliminar las causas técnicas ya identificadas de la lentitud al guardar un ticket. Bajo esfuerzo, alto impacto — se puede completar en un sprint corto.

- [x] **Eliminar el N+1 doble en la carga del formulario de venta.** *(Hecho — 2026-07-18)* `registrar_venta` (`ventas/views.py:193`) llama a dos funciones casi equivalentes — `obtener_articulos_con_inventario()` (`ventas/services.py:69`) y `obtener_articulos_con_inventario_obj()` (`ventas/services.py:100`) — cada una iterando artículo por artículo y consultando `DetalleCompra` por separado (sin `annotate`/`Sum`). La segunda función **ni siquiera se usa** en el template (`articulos_json` es lo único referenciado). Colapsar en una sola función con una consulta agregada.
  **Métrica**: queries en el GET de `/ventas/` de `2+2N` (N = artículos activos) a un número constante, verificable con `django-debug-toolbar` o `assertNumQueries` en un test.

- [x] **Cortar la tormenta de señales de recálculo de total.** *(Hecho — 2026-07-18: `bulk_create` para detalles + `update_total()` con `aggregate`)* `ventas/signals.py:5-10` dispara `Venta.update_total()` (2 SELECT + 1 UPDATE) en cada `post_save`/`post_delete` de `DetalleArticulo` y `DetalleAvance`. Como un solo ítem del carrito puede generar varias filas de `DetalleArticulo` (una por lote FIFO consumido, `consumir_lotes_fifo`), y `procesar_venta()` (`ventas/services.py:324`) además llama `update_total()` explícitamente al final, un ticket de 5 artículos + 2 cheques dispara ~7 recálculos completos de más.
  **Solución sugerida**: crear los detalles sin disparar la señal (o desconectarla temporalmente) durante `procesar_venta`, y calcular el total una sola vez al final con una agregación directa en vez de reconsultar y guardar repetidamente.
  **Métrica**: de ~3N+1 queries de bookkeeping a 1 sola. Medir antes/después con un ticket de prueba de 5 artículos + 2 cheques (objetivo: bajar de ~22 a ~8 queries totales en el POST).

- [x] **Guard de doble-submit.** *(Hecho — 2026-07-18)* `ventas_form.html:348-363` — los botones "Guardar"/"Registrar e Imprimir" solo se deshabilitan si el carrito está vacío, no mientras la request está en vuelo. Agregar estado de "enviando" (deshabilitar botón + spinner) en el submit de Alpine.
  **Métrica**: 0 tickets duplicados detectables por doble clic (verificable buscando `Venta` con mismos cosechero+cosecha+total creadas en el mismo segundo).

- [x] **No descartar en silencio avances incompletos.** *(Hecho — 2026-07-18: validación antes de tocar la BD)* `crear_avances_desde_post` (`ventas/services.py:207-208`) hace `continue` sin avisar cuando falta `tipo_avance`/`numero`/`monto` en una fila. Cambiar a error de validación visible al usuario antes de enviar.
  **Métrica**: 0 cheques perdidos silenciosamente (hoy no hay forma de saber si esto ya pasó en producción — vale la pena revisar logs históricos si existen).

- [x] **Validar `Avance.fecha` en cliente antes de enviar.** *(Hecho — 2026-07-18)* El campo es `DateField` no-nullable en el modelo, pero el modal permite dejarlo vacío. Si eso ocurre, el `IntegrityError` revienta dentro del `@transaction.atomic` de `procesar_venta`, revirtiendo **todo el ticket** (artículos y otros cheques ya cargados), no solo el cheque problemático. Agregar `required` + validación inline en el modal.
  **Métrica**: 0 rollbacks completos de ticket por este motivo.

- [x] **Limpieza de código muerto/duplicado.** *(Hecho — 2026-07-18)*
  - Borrado `ventas/forms.py` (no lo importaba nadie).
  - Unificadas las dos definiciones de `procesar_detalles_articulos` en `ventas/services.py`.
  - Borrado `static/css/output.css` (build viejo, no referenciado por ningún template).
  - Arreglado `cosecheros/signals.py` para usar el modelo `Avance` unificado en vez de los `Avance.Cheque/Deposito/PagoEfectivo` ya eliminados.

---

## Fase 1 — Rediseño del flujo de registro (facturas + cheques)

**Objetivo**: atacar directamente la queja explícita del usuario sobre lentitud al registrar facturas y cheques. Requiere tocar `ventas_form.html` y su JS de forma más profunda que la Fase 0.

- [x] **Reemplazar el selector de cosechero.** *(Resuelto — 2026-08-08: búsqueda normalizada en memoria, máximo de ocho resultados.)* Antes se renderizaba server-side un botón por cada cosechero activo.
  **Métrica**: latencia de tecla-a-render objetivo <50ms independiente del número de cosecheros. Definir junto con el usuario un umbral (ej. >2000 cosecheros) a partir del cual convenga migrar a un endpoint de búsqueda con debounce en vez de array en memoria.

- [x] **Desacoplar el guardado de la impresión.** *(Resuelto — 2026-08-08: el guardado responde primero y la impresión se solicita mediante un POST separado.)*
  **Métrica**: respuesta de "Guardar" <500ms sin importar el estado de la impresora.

- [x] **Preservar el carrito ante error de validación.** *(Resuelto — 2026-08-08: captura AJAX, errores inline y borrador en `sessionStorage` por 24 horas.)*
  **Métrica**: 0 pérdidas de datos ingresados ante error de validación.

- [x] **Hacer visible el cierre semanal automático.** *(Resuelto — 2026-08-08: tarjeta de resumen con sábado, ticket y total acumulado.)*
  **Métrica**: cualitativa — confirmar con el usuario/cajeros que dejan de reportar confusión sobre la fecha del ticket.

- [x] **Alta rápida de cosechero/artículo faltante sin salir del ticket en progreso.** *(Resuelto — 2026-08-08: modales operativos que conservan el borrador.)*
  **Métrica**: de ~5+ navegaciones de página a 1 modal para el caso de "cosechero nuevo a mitad de venta".

- [x] **Paginar y filtrar `tickets.html`.** *(Resuelto — 2026-08-08: paginación de 50 y filtros server-side por cosecha, cosechero y fechas.)*
  **Métrica**: tamaño de página acotado (ej. 50 filas) sin importar cuánto crezca el histórico.

---

## Fase 2 — Completar la migración visual (Tailwind/Alpine)

**Objetivo**: completar la migración visual para que todo el sistema se sienta consistente. Las cuatro apps con pantallas operativas propias (`ventas`, `avance`, `cosecheros` y `compra`) ya usan Tailwind/Alpine; `dashboard` hereda directamente la base global y `proveedor`/`articulo` todavía no tienen UI propia.

- [x] **Migrar `cosecheros/templates/index.html`.** *(Hecho — 2026-08-08)* Se reemplazó Bootstrap por Tailwind/Alpine, se eliminó el modal repetido por cada cosechero y se agregó un único modal reutilizable. El listado ahora tiene búsqueda server-side por nombre/cédula/teléfono y paginación de 25 filas. En la verificación con datos locales, la respuesta bajó de ~440 KB a ~104 KB.
- [x] **Migrar `compra/templates/compras_form.html`.** *(Hecho — 2026-08-08)* Se reemplazó Bootstrap y el armado imperativo de filas por una pantalla Tailwind/Alpine responsive con estados de carga/error, totales de costo y venta sugerida, validación visible y guard contra doble envío. La carga de artículos conserva el contrato existente por proveedor y el guardado continúa generando los lotes FIFO.
- [x] **Dar a `cosecheros` un CRUD real en UI.** *(Resuelto — 2026-08-08: CRUD Tailwind con soft-delete y alta rápida.)*
- [x] **Decidir con el usuario el destino de `proveedor` y `articulo`.** *(Resuelto — 2026-08-08: ambos tienen CRUD visual; proveedores se crean en su pantalla dedicada.)*

**Métrica de fase**: 100% de las cuatro apps con pantallas operativas propias están en Tailwind (`ventas`, `avance`, `cosecheros`, `compra`). El grep de clases Bootstrap remanentes en esos templates da 0 coincidencias.

---

## Fase 3 — Correctness & hardening

**Objetivo**: cerrar bugs latentes encontrados durante la auditoría. No están directamente ligados a la lentitud reportada, pero son riesgos de integridad de datos que conviene resolver antes de que se manifiesten en producción. Puede correr en paralelo a la Fase 2.

- [x] **`Cosechero.numero_cuenta_banco`.** *(Resuelto — 2026-08-08: los valores vacíos se normalizan a `NULL`.)*
- [x] **Validador de cédula.** *(Resuelto — 2026-08-08: rechaza caracteres no numéricos con validación clara.)*
- [x] **Filtro de saldos en reportes.** *(Resuelto — 2026-07-19: la conciliación expone ambos grupos y evita depender de un signo ambiguo.)*
- [x] **Completar el flujo de login.** *(Hecho — 2026-08-08)* Se agregó `/accounts/login/` con una pantalla Tailwind local, redirecciones de login/logout y protección coherente de dashboard, cosecheros, reportes, precios, ventas, avances y compras. Ya no es necesario iniciar sesión indirectamente a través de `/admin/`.
- [x] **De-duplicar `proximo_sabado()`.** *(Resuelto — 2026-08-08: centralizado en `app/fechas.py`.)*
- [x] **De-duplicar la tabla `PRECIOS_VARIEDAD`.** *(Hecho — 2026-07-19, alcance ampliado: ver "Precios dinámicos por cosecha" más abajo)*
- [x] **Filtro invertido de saldo en `resumen_perdidas_cosecha`.** *(Resuelto — 2026-07-19: el comando ahora muestra ambos grupos, "nos deben" y "les debemos", en vez de filtrar por un signo — ver nota abajo)*
- [x] **Higiene de producción.** *(Resuelto en código — 2026-08-08: secretos, `DEBUG`, hosts y rutas sensibles se leen desde entorno; al salir de la LAN deberán definirse los valores del despliegue.)*

### Precios dinámicos por cosecha (2026-07-19)

A pedido del usuario, se resolvió con más alcance del que originalmente preveía la Fase 3: los precios de tabaco ya no son un dict hardcodeado, sino el modelo `PrecioVariedadCosecha` (una fila por variedad, 7 columnas de precio, con historial por cosecha) — ver `docs/ARQUITECTURA.md` §4.1. Incluye página Tailwind de gestión (`/cosecheros/precios/`), copia automática de precios al abrir una cosecha nueva, y consolidación de toda la lógica de tara/producción/saldo (antes duplicada entre `cosecheros/views.py` y `cosecheros/utils/reportes.py`) en un único `cosecheros/services.py`.

Este pendiente quedó resuelto por las fases de Dashboard financiero y universo completo: la pantalla principal muestra ambos grupos por cosecha y comparte la conciliación con PDF, CSV y línea de comandos.

---

## Métricas globales a trackear entre fases

| Métrica | Cómo medirla | Línea base | Objetivo |
|---|---|---|---|
| Queries en GET `/ventas/` | `django-debug-toolbar` o `assertNumQueries` | `2 + 2N` (N = artículos activos) | Constante, independiente de N |
| Queries en POST de un ticket de 5 artículos + 2 cheques | Igual que arriba | ~22 (estimado) | ~8 |
| Tiempo de respuesta de "Guardar" | Medición manual o logging de duración de request | Incluye I/O de impresora si aplica | <500ms, independiente del estado de la impresora |
| Recargas de página por sesión de captura múltiple (varios cosecheros seguidos) | Conteo manual / analítica de navegación | 1 recarga completa por ticket | Minimizar recargas necesarias para el flujo "siguiente cosechero" |
| % de templates migrados a Tailwind | Grep de clases Bootstrap remanentes | 4 de 4 apps operativas originales | Cumplido; `proveedor` y `articulo` también tienen CRUD visual |
| Bugs de correctness abiertos (Fase 3) | Checklist de este documento | 7 identificados | 0; las decisiones contables futuras se mantienen separadas de los bugs |

**Instrumentación vigente**: mantener pruebas `assertNumQueries` para los servicios críticos; el universo financiero se valida con seis consultas constantes.
