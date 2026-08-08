# Plan de mejora — Tabacalera

> Última auditoría de código: 2026-08-08. Ver [ARQUITECTURA.md](ARQUITECTURA.md) para el mapa del sistema referenciado aquí.

## Ejecución del roadmap integral — 2026-08-08

| Fase | Estado | Evidencia principal |
|---|---|---|
| Seguridad, Git y backup | Completada | rama `feature/venta-segura`, checkpoint `ec5e74b`, BAK verificado en `RUNBOOK_PRODUCCION.md` |
| Venta decimal e idempotente | Completada | migración `ventas.0006`, `OperacionVenta`, bloqueo MSSQL y pruebas de replay/conflicto/FIFO |
| Captura AJAX y borrador | Completada | `ventas_form_v2.html`, `sessionStorage` 24 h, búsqueda normalizada y resumen semanal |
| Impresión desacoplada | Completada en código | POST separado y `503` sin rollback; falta prueba física final de la USB |
| Tickets escalables | Completada | filtros GET, paginación de 50 y POST de impresión |
| CRUD y altas rápidas | Completada | cosecheros, artículos y proveedores; soft-delete y validaciones |
| Dashboard financiero | Completada | resumen por cosecha, grupos de saldo, PDF y CSV desde cálculo común |
| Hardening | Completada en código | entorno, zona horaria, favicon, recursos visuales locales; pendiente smoke test manual con impresora |

Commits de fase y resultados de validación se completan al cierre de esta rama. Los puntos que exigen hardware real no se consideran verificados hasta probar la impresora conectada.

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

- [ ] **Reemplazar el selector de cosechero.** Hoy (`ventas_form.html:59-73`) se renderiza server-side un `<button>` por cada cosechero activo, y el filtro de búsqueda re-evalúa un `x-show` de tipo "string includes" contra **todos** los botones en cada tecla — sin AJAX, sin debounce, sin límite de resultados. El propio archivo ya tiene el patrón correcto para artículos: un array en memoria + `articulosFiltrados` como getter, capado a 6 resultados visibles. Aplicar el mismo patrón al selector de cosechero.
  **Métrica**: latencia de tecla-a-render objetivo <50ms independiente del número de cosecheros. Definir junto con el usuario un umbral (ej. >2000 cosecheros) a partir del cual convenga migrar a un endpoint de búsqueda con debounce en vez de array en memoria.

- [ ] **Desacoplar el guardado de la impresión.** `_imprimir_ticket()` (`ventas/views.py:36-141`) abre la impresora térmica USB (`escpos.printer.Usb`) de forma síncrona **dentro** del POST de "Registrar e Imprimir". Si la impresora está apagada/desconectada, esto puede agregar latencia real antes de que el `try/except` silencioso deje pasar. Guardar y responder primero; disparar la impresión como una llamada aparte (fetch async) con estado visible "Imprimiendo…" y manejo de error explícito (hoy falla en silencio).
  **Métrica**: respuesta de "Guardar" <500ms sin importar el estado de la impresora.

- [ ] **Preservar el carrito ante error de validación.** Si `procesar_venta` devuelve `success: False` (ej. inventario insuficiente), `registrar_venta` (`ventas/views.py:180-199`) re-renderiza la página desde un GET limpio — el estado del carrito vive solo en memoria de Alpine, así que se pierde todo y el usuario debe re-ingresar. Opciones: (a) convertir el submit a AJAX y mantener el componente Alpine vivo, mostrando el error sin recargar la página; o (b) persistir el carrito en `localStorage` como red de seguridad.
  **Métrica**: 0 pérdidas de datos ingresados ante error de validación.

- [ ] **Hacer visible el cierre semanal automático.** `proximo_sabado()` desplaza silenciosamente la fecha de venta al sábado más próximo (`ventas/services.py:31-39`), y una venta nueva del mismo cosechero en la misma semana **se fusiona** con la existente (`obtener_venta_existente`) en vez de crear una nueva — pero la fecha que el usuario ve en el formulario no es necesariamente la que se guarda. Mostrar en el formulario, antes de enviar, algo como "Esto se registrará en el ticket semanal que cierra el sábado [fecha], total acumulado hasta ahora: [monto]".
  **Métrica**: cualitativa — confirmar con el usuario/cajeros que dejan de reportar confusión sobre la fecha del ticket.

- [ ] **Alta rápida de cosechero/artículo faltante sin salir del ticket en progreso.** Hoy, si falta un cosechero o artículo, hay que abandonar la venta en curso, ir al módulo correspondiente, crearlo, y volver (perdiendo el carrito por el punto anterior). Agregar un modal de "alta rápida" reutilizable desde `ventas_form.html`. Depende de que exista una vista de creación real para `Cosechero` (ver Fase 2).
  **Métrica**: de ~5+ navegaciones de página a 1 modal para el caso de "cosechero nuevo a mitad de venta".

- [ ] **Paginar y filtrar `tickets.html`.** `get_tickets` (`ventas/views.py:206-226`) trae todas las ventas activas sin límite; el template las renderiza todas en el DOM y solo oculta con `x-show` para el buscador de texto. El único filtro server-side es por cosecha (recarga completa de página). Agregar `Paginator` + filtro por rango de fecha y por cosechero.
  **Métrica**: tamaño de página acotado (ej. 50 filas) sin importar cuánto crezca el histórico.

---

## Fase 2 — Completar la migración visual (Tailwind/Alpine)

**Objetivo**: completar la migración visual para que todo el sistema se sienta consistente. Las cuatro apps con pantallas operativas propias (`ventas`, `avance`, `cosecheros` y `compra`) ya usan Tailwind/Alpine; `dashboard` hereda directamente la base global y `proveedor`/`articulo` todavía no tienen UI propia.

- [x] **Migrar `cosecheros/templates/index.html`.** *(Hecho — 2026-08-08)* Se reemplazó Bootstrap por Tailwind/Alpine, se eliminó el modal repetido por cada cosechero y se agregó un único modal reutilizable. El listado ahora tiene búsqueda server-side por nombre/cédula/teléfono y paginación de 25 filas. En la verificación con datos locales, la respuesta bajó de ~440 KB a ~104 KB.
- [x] **Migrar `compra/templates/compras_form.html`.** *(Hecho — 2026-08-08)* Se reemplazó Bootstrap y el armado imperativo de filas por una pantalla Tailwind/Alpine responsive con estados de carga/error, totales de costo y venta sugerida, validación visible y guard contra doble envío. La carga de artículos conserva el contrato existente por proveedor y el guardado continúa generando los lotes FIFO.
- [ ] **Dar a `cosecheros` un CRUD real en UI.** Hoy la única forma de crear/editar un cosechero es Django Admin (`cosecheros/admin.py`, registro plano sin `search_fields`/`list_filter`). Esto es además **prerrequisito** de la alta rápida de la Fase 1, y de que el matching automático de cuenta bancaria en el import masivo de `avance` tenga datos confiables para trabajar.
- [ ] **Decidir con el usuario el destino de `proveedor` y `articulo`.** Hoy no tienen ni `urls.py` ni vistas reales — son solo modelos consumidos por `compra`. Confirmar si eso es intencional (gestión solo vía admin) o si necesitan una UI propia, y documentar la decisión en `ARQUITECTURA.md`.

**Métrica de fase**: 100% de las cuatro apps con pantallas operativas propias están en Tailwind (`ventas`, `avance`, `cosecheros`, `compra`). El grep de clases Bootstrap remanentes en esos templates da 0 coincidencias.

---

## Fase 3 — Correctness & hardening

**Objetivo**: cerrar bugs latentes encontrados durante la auditoría. No están directamente ligados a la lentitud reportada, pero son riesgos de integridad de datos que conviene resolver antes de que se manifiesten en producción. Puede correr en paralelo a la Fase 2.

- [ ] **`Cosechero.numero_cuenta_banco`** — `CharField(unique=True, blank=True)`. Si dos cosecheros quedan con este campo vacío, el segundo guardado revienta con `IntegrityError`. Cambiar a `null=True` y normalizar `''` → `None` al guardar, o agregar una validación explícita.
- [ ] **Validador de cédula** (`cosecheros/models.py`) — agregar un guard `isdigit()`/regex antes de indexar el string, para dar un error de validación claro en vez de un fallo interno con input no numérico.
- [ ] **Filtro invertido en `cosecheros/utils/reportes.py`** — el comentario dice "solo los que dan positivo" pero el código filtra `saldo < 0`. **No cambiar sin confirmar antes con el usuario** cuál es la regla de negocio correcta — podría ser el comentario el equivocado, no el código.
- [x] **Completar el flujo de login.** *(Hecho — 2026-08-08)* Se agregó `/accounts/login/` con una pantalla Tailwind local, redirecciones de login/logout y protección coherente de dashboard, cosecheros, reportes, precios, ventas, avances y compras. Ya no es necesario iniciar sesión indirectamente a través de `/admin/`.
- [ ] **De-duplicar `proximo_sabado()`** entre `avance/services.py` y `ventas/services.py` — moverla a un módulo compartido.
- [x] **De-duplicar la tabla `PRECIOS_VARIEDAD`.** *(Hecho — 2026-07-19, alcance ampliado: ver "Precios dinámicos por cosecha" más abajo)*
- [x] **Filtro invertido de saldo en `resumen_perdidas_cosecha`.** *(Resuelto — 2026-07-19: el comando ahora muestra ambos grupos, "nos deben" y "les debemos", en vez de filtrar por un signo — ver nota abajo)*
- [ ] **Higiene de producción (a futuro, antes de cualquier despliegue fuera de LAN)**: `DEBUG=True`, `SECRET_KEY` hardcodeada, `ALLOWED_HOSTS=['*', '192.168.43.90']` en `app/settings.py`.

### Precios dinámicos por cosecha (2026-07-19)

A pedido del usuario, se resolvió con más alcance del que originalmente preveía la Fase 3: los precios de tabaco ya no son un dict hardcodeado, sino el modelo `PrecioVariedadCosecha` (una fila por variedad, 7 columnas de precio, con historial por cosecha) — ver `docs/ARQUITECTURA.md` §4.1. Incluye página Tailwind de gestión (`/cosecheros/precios/`), copia automática de precios al abrir una cosecha nueva, y consolidación de toda la lógica de tara/producción/saldo (antes duplicada entre `cosecheros/views.py` y `cosecheros/utils/reportes.py`) en un único `cosecheros/services.py`.

Pendiente para el futuro (no incluido en este trabajo): un dashboard o generador de reportes dinámico para ver de un vistazo, sin PDF ni línea de comandos, cuánto se debe a cada cosechero y cuánto debe cada uno — el usuario lo mencionó como la necesidad real detrás del comando `resumen_perdidas_cosecha`.

---

## Métricas globales a trackear entre fases

| Métrica | Cómo medirla | Línea base | Objetivo |
|---|---|---|---|
| Queries en GET `/ventas/` | `django-debug-toolbar` o `assertNumQueries` | `2 + 2N` (N = artículos activos) | Constante, independiente de N |
| Queries en POST de un ticket de 5 artículos + 2 cheques | Igual que arriba | ~22 (estimado) | ~8 |
| Tiempo de respuesta de "Guardar" | Medición manual o logging de duración de request | Incluye I/O de impresora si aplica | <500ms, independiente del estado de la impresora |
| Recargas de página por sesión de captura múltiple (varios cosecheros seguidos) | Conteo manual / analítica de navegación | 1 recarga completa por ticket | Minimizar recargas necesarias para el flujo "siguiente cosechero" |
| % de templates migrados a Tailwind | Grep de clases Bootstrap remanentes | 4 de 4 apps con UI operativa (`ventas`, `avance`, `cosecheros`, `compra`) | Cumplido; decidir aparte si `proveedor`/`articulo` tendrán UI propia |
| Bugs de correctness abiertos (Fase 3) | Checklist de este documento | 7 identificados | 0 (3 resueltos al 2026-08-08, 4 abiertos) |

**Sugerencia de instrumentación**: instalar `django-debug-toolbar` en desarrollo antes de empezar la Fase 0, para tener una línea base real de queries por vista en vez de solo la estimación de la auditoría de código.
