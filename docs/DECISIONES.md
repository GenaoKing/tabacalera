# Decisiones de negocio y diseño

## Cuenta semanal de cosechero

- Una `Venta` es la cuenta que agrupa movimientos por `cosechero + cosecha + sábado`.
- La fecha real de entrega o avance se audita en `OperacionVenta.fecha_movimiento`; `Venta.fecha_venta` conserva el sábado de la semana.
- El sábado es un corte informativo para revisión y firma. No bloquea movimientos posteriores.
- Un movimiento nuevo sobre un ticket ya impreso vuelve a marcarlo pendiente.
- `Guardar` registra y acumula sin imprimir.
- `Registrar e imprimir` registra primero y luego solicita la impresión del acumulado semanal completo.
- Una falla de impresora nunca revierte una venta confirmada.

## Integridad e historia

- Cada envío nuevo usa una UUID idempotente. Mismo UUID y mismo payload es replay; mismo UUID con otro payload es conflicto `409`.
- El consumo de inventario es FIFO y admite cantidades con dos decimales mayores que cero.
- Los detalles anteriores a la auditoría permanecen con `operacion=NULL`.
- Los cuatro tickets históricos duplicados identificados permanecen sin cambios. Una semana ambigua se muestra y se rechaza para movimientos nuevos; no se consolida automáticamente.
- No se migra esquema productivo sin backup SQL Server verificado.

## Experiencia operativa

- El borrador de Venta vive en `sessionStorage`, separado por usuario y pestaña, y expira a las 24 horas.
- El servidor es la autoridad final sobre inventario, precio y validaciones.
- Las altas rápidas de cosechero y artículo preservan el borrador. Un artículo nuevo requiere una compra antes de poder venderse.
- Cosecheros, proveedores y artículos se desactivan lógicamente; la operación solo muestra activos.
- Proveedores se crean en su pantalla dedicada, excepto que los artículos seleccionan únicamente proveedores existentes.

## Conciliación financiera

- El saldo no se persiste en otra tabla.
- La fuente única calcula `gastos - producción` desde artículos, avances y entregas valorizadas.
- Saldo positivo significa que el cosechero debe a Tabacalera; saldo negativo significa que Tabacalera debe al cosechero.
- Dashboard, CSV y PDF parten de las mismas fuentes de cálculo.
- El universo de una cosecha es la unión de cosecheros con entregas o ventas activas de esa cosecha. Un avance solo pertenece a la cosecha cuando está vinculado a una `Venta` mediante `DetalleAvance`.
- Las cuentas con gastos y ninguna entrega permanecen en “Nos deben” y muestran la etiqueta “Sin producción entregada”; no se duplican en una tercera tabla.
- La alerta de cuentas sin producción forma parte del total y cantidad general de “Nos deben”.
- La última actividad usa la fecha operativa: entrega, fecha real del avance u operación. Para artículos históricos sin `OperacionVenta`, usa el sábado de `Venta` y lo identifica como cierre semanal aproximado.
- Todos los cálculos de dominio usan `Decimal`; la conversión a texto de dos decimales ocurre únicamente en la presentación o exportación.
- Los indicadores por tarea son individuales por cosechero: sus gastos, su producción valorizada y sus quintales entregados se dividen entre su propio `terreno_sembrado`. No se presenta una razón global de toda la cosecha.
- Los quintales usan la misma cantidad ajustada por tara que sirve para valorizar las entregas. Una entrega sin precio suma quintales aunque no sume producción monetaria.
- Si un cosechero tiene cero tareas, su bloque muestra “Sin tareas registradas” en lugar de dividir entre cero o presentar un cero engañoso.
- Los avances sin `DetalleAvance` no se asignan por rango de fecha ni se contabilizan automáticamente. Sus casos conocidos están en `INCIDENCIAS_DATOS.md`.
- En la operación normal no se espera saldo exactamente cero; el servicio y CSV lo conservan defensivamente sin crear una tabla adicional.

### Decisiones financieras pendientes

- Definir si el redondeo monetario debe aplicarse por detalle, por agrupación o solo al total. Hasta entonces se conserva la precisión Decimal existente y se presentan dos decimales.
- Resolver manualmente los siete avances históricos sin cosecha antes de incorporarlos a cualquier conciliación.
- Evaluar un modelo de terreno por `cosechero + cosecha` si se necesita comparar promedios históricos cuando el área sembrada cambia entre temporadas.

## CRUD de avances

- La tabla abre en la cosecha más reciente y muestra avances activos; filtros explícitos permiten consultar otras cosechas, inactivos y huérfanos.
- Un alta individual siempre queda vinculada a la cuenta `cosechero + cosecha + sábado` y usa la idempotencia de `OperacionVenta`.
- Se permite corregir cosechero, cosecha, fecha, monto y datos documentales. La edición modifica el avance existente, sin tabla de versiones, y recalcula transaccionalmente las cuentas afectadas.
- `realizado`, `cambiado` y `nulo` son informativos. Solo `Avance.is_active` determina si el cargo participa en tickets, Dashboard, PDF y saldos.
- Desactivar es reversible; un avance inactivo es de solo lectura hasta restaurarlo.
- Los huérfanos se muestran, pero solo se vinculan después de confirmar manualmente cosecha, cosechero y fecha. No se asignan automáticamente por rango.
- El importador conserva su preview y queda disponible como acción secundaria desde la tabla.
- Para archivos manuales mixtos se recomienda el formato unificado con `Tipo`, `ID`, `Fecha`, `Numero`, `Monto` y `Descripcion`; la cosecha se selecciona una vez en la interfaz para todo el lote.
- La fecha del nombre es solo un fallback del export bancario de depósitos y usa `MM-DD-AA`; nunca se infiere desde los metadatos del archivo ni se aplica a cheques.
- Mientras el importador no tenga idempotencia, un archivo confirmado no debe reimportarse. El resultado puede ser parcial porque cada fila se confirma en su propia transacción.

## Seguridad local

- Todas las pantallas operativas requieren autenticación.
- Django Admin queda como soporte técnico; los CRUD Tailwind son la interfaz diaria.
- No se crean roles adicionales hasta que la operación real demuestre la necesidad de separar permisos.

## Identidad visual

- `static/img/tabacalera-genao-logo.png` es la única fuente canónica del logo corporativo.
- El logo se usa en sidebar, login, favicon, Django Admin, PDF individual y ticket térmico.
- Las salidas del servidor no deben abrir `logo.png` mediante una ruta relativa; deben usar `app.branding.get_brand_logo_path()`.
- El login y el resto del portal mantienen los recursos visuales locales, sin cargar fuentes ni imágenes externas.

## Presentación numérica

- Todo importe o cantidad decimal visible usa `10,000.00`, incluso cuando su parte decimal sea cero.
- El símbolo monetario se conserva según el contexto (`$` o `RD$`); la regla común afecta el número, no la semántica de la moneda.
- IDs, números de documentos y conteos de filas no reciben decimales ni separadores monetarios.
- El formato no entra en la lógica financiera: modelos, formularios, APIs y cálculos mantienen `Decimal` o cadenas numéricas canónicas sin comas.
- Los CSV operativos son documentos para lectura humana y presentan las columnas decimales con la misma convención; `csv.writer` entrecomilla los valores que contienen coma.
