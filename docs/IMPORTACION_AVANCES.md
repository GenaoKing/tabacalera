# Importación de avances desde Excel

> Estado auditado: 2026-08-11. Esta guía describe el comportamiento real de `avance/services.py` y `/avances/importar/`.

## Formato recomendado para cheques y depósitos

Para preparar manualmente un archivo que mezcle ambos tipos, usar un solo libro `.xlsx`, una sola hoja y la primera fila como encabezado:

| Tipo | ID | Fecha | Numero | Monto | Descripcion |
|---|---:|---|---|---:|---|
| cheque | 50030 | 2026-04-17 | 10452 | 15000.00 | Avance para corte |
| deposito | 50031 | 2026-04-17 | DEP-20260417-01 | 8000.00 | Depósito a cuenta |

Reglas:

- `Tipo`: `cheque` o `deposito`. El importador también reconoce `ch`, `dep`, `depósito`, `cheques` y `depositos`.
- `ID`: ID interno del cosechero en el sistema; no es la cédula. Es la forma más segura de identificarlo.
- `Fecha`: fecha real del avance. Se recomienda una fecha real de Excel o texto ISO `AAAA-MM-DD`, por ejemplo `2026-04-17`.
- `Numero`: número del cheque o referencia del depósito. Aunque el parser permite dejarlo vacío, operativamente debe completarse para facilitar conciliación y detección manual de duplicados.
- `Monto`: número positivo. Preferir una celda numérica de Excel con dos decimales, sin escribir `RD$` dentro de la celda.
- `Descripcion`: opcional. Si falta, se usa `Avance a cosecha <nombre>`.

El encabezado `Tipo` hace que el archivo sea detectado como **unificado**. En este formato también se admite `No. Cuenta` como alternativa al `ID`, pero el `ID` tiene prioridad y evita problemas con cuentas vacías, digitadas como número o desactualizadas.

## Formato separado de cheques

Para un archivo que contenga solo cheques:

| No. Cheque | Monto | ID | Fecha | Cosechero | Descripcion |
|---|---:|---:|---|---|---|

Son necesarias para detectar el formato las columnas exactas `No. Cheque`, `Monto` e `ID`. `Fecha` también es necesaria para que una fila sea válida. `Cosechero` solo ayuda a leer el preview; la asociación automática se realiza por `ID`.

El nombre del archivo **no aporta la fecha a los cheques**.

## Formato de export bancario para depósitos

Para un export que contenga solo depósitos:

| No. de cuenta | Monto | Beneficiario | Fecha | Descripcion |
|---|---:|---|---|---|

Las columnas exactas `No. de cuenta`, `Monto` y `Beneficiario` activan el formato bancario. La asociación se hace comparando solamente los dígitos de `No. de cuenta` con `Cosechero.numero_cuenta_banco` de los cosecheros activos. `Beneficiario` no busca por nombre; solo se muestra para ayudar a asignar manualmente una fila no encontrada.

Conviene almacenar la cuenta como texto en Excel para no perder ceros iniciales.

### Fecha tomada del nombre del archivo

Este mecanismo existe, pero es limitado:

- Solo aplica al formato bancario de depósitos.
- Busca una fecha `MM-DD-AA` dentro del nombre. Ejemplo: `Depositos 04-17-26.xlsx` produce `2026-04-17`.
- No usa la fecha de creación, modificación ni carga del archivo.
- Si una fila tiene una celda `Fecha` no vacía, esa celda tiene prioridad.
- Si la columna no existe o la celda está vacía, usa la fecha del nombre.
- Un valor de fecha no vacío pero inválido no cae automáticamente al nombre; queda como error para corregir en el preview.
- Nombres `17-04-26` o `2026-04-17` no son reconocidos por este mecanismo.

La fecha global del preview permite completar todas las filas que sigan sin fecha antes de confirmar.

## Cosecha y ticket semanal

La cosecha se selecciona en la pantalla antes de analizar el archivo y se aplica a **todas** las filas. No se obtiene de una columna, de la fecha ni del nombre del archivo.

La fecha de cada fila es la fecha operativa del avance. Al confirmar, el sistema calcula el sábado correspondiente con `proximo_sabado()` y crea o reutiliza la cuenta exacta:

`cosechero + cosecha seleccionada + sábado`

El propio sábado pertenece a esa misma cuenta. Por ejemplo, viernes `2026-04-17` y sábado `2026-04-18` se vinculan al ticket del `2026-04-18`.

## Cómo preparar el libro

- Usar `.xlsx`; también se admite CSV. Evitar `.xls`: aparece en el selector histórico, pero el lector actual usa `openpyxl` y no ofrece soporte confiable para ese formato antiguo.
- Colocar la tabla en la primera hoja. Las demás hojas no se leen.
- Colocar los encabezados en la primera fila, sin títulos decorativos ni celdas combinadas encima.
- No incluir filas de total, subtotales, firmas o notas dentro de la tabla.
- Preferir fechas ISO o celdas de fecha. `04/05/2026` se interpreta primero como `4 de mayo`, no como `5 de abril`.
- Preferir montos numéricos. `15,000.00` se interpreta correctamente, pero actualmente textos como `1,500` se interpretan como `1.500` y `15.000,00` como `15.00000`; deben evitarse.
- Revisar en el preview cosechero, tipo, número, monto, fecha, total seleccionado y cosecha antes de confirmar.
- Las filas verdes se preseleccionan. Una fila amarilla sin cosechero exige selección manual. Una fila roja necesita corregir fecha, monto, tipo o cosechero.

## Efectos de confirmar

- Cada fila confirmada crea un `Avance` activo, en estado documental `realizado`, y un `DetalleAvance` dentro del ticket semanal.
- Un ticket existente se actualiza y queda pendiente de impresión; si no existe, se crea.
- Si hay varios tickets históricos activos para la misma cuenta semanal, esa fila se rechaza.
- La importación procesa cada fila en su propia transacción. Puede terminar con filas creadas y otras rechazadas; el resultado debe revisarse antes de corregir o reintentar.

## Limitaciones de seguridad actuales

El preview vale la pena porque permite confirmar identidad, fecha, importe, cosecha y total antes de escribir. Sin embargo, este importador es anterior al flujo de venta segura y todavía tiene estas limitaciones:

- No tiene clave de idempotencia ni detección automática de duplicados por referencia.
- Volver a confirmar o volver a subir el mismo archivo puede duplicar los avances.
- Los movimientos importados no crean una `OperacionVenta` con usuario y huella del archivo.
- La cuenta semanal no usa todavía el bloqueo transaccional MSSQL del alta individual.
- No existe rollback del lote completo cuando solo una fila falla.

Hasta reforzar el importador: cargar un archivo una sola vez, conservarlo como evidencia, revisar la pantalla final, comprobar los avances creados en `/avances/` por fecha/referencia/total y corregir filas fallidas individualmente sin volver a seleccionar las ya creadas.

## Mejoras pendientes recomendadas

1. Añadir idempotencia por lote y por fila, guardando hash del archivo y referencia normalizada.
2. Mostrar duplicados probables contra la base antes de permitir confirmar.
3. Registrar cada fila en `OperacionVenta` con usuario y fecha operativa.
4. Reutilizar el bloqueo semanal del servicio de ventas.
5. Definir si la confirmación será atómica para todo el archivo o continuará permitiendo éxito parcial.
6. Corregir el parser monetario para formatos `1,500` y `15.000,00` sin ambigüedad.
7. Retirar `.xls` de la interfaz o incorporar un lector compatible.
