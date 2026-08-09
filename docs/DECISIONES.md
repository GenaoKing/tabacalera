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
- Los avances sin `DetalleAvance` no se asignan por rango de fecha ni se contabilizan automáticamente. Sus casos conocidos están en `INCIDENCIAS_DATOS.md`.
- En la operación normal no se espera saldo exactamente cero; el servicio y CSV lo conservan defensivamente sin crear una tabla adicional.

### Decisiones financieras pendientes

- Definir formalmente el efecto contable futuro de `Avance.estado = nulo` y `cambiado`. La fase actual conserva la regla histórica porque todos los avances productivos existentes están activos y realizados.
- Definir si el redondeo monetario debe aplicarse por detalle, por agrupación o solo al total. Hasta entonces se conserva la precisión Decimal existente y se presentan dos decimales.
- Resolver manualmente los siete avances históricos sin cosecha antes de incorporarlos a cualquier conciliación.

## Seguridad local

- Todas las pantallas operativas requieren autenticación.
- Django Admin queda como soporte técnico; los CRUD Tailwind son la interfaz diaria.
- No se crean roles adicionales hasta que la operación real demuestre la necesidad de separar permisos.
