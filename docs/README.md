# Documentación de referencia — Tabacalera

Esta carpeta es la referencia técnica global del proyecto:

- **[ARQUITECTURA.md](ARQUITECTURA.md)** — mapa del sistema: apps, modelos, relaciones, flujo de negocio, stack técnico, estado de la migración a Tailwind/Alpine y convenciones ya establecidas. Léelo primero si eres nuevo en el proyecto o si retomas trabajo después de un tiempo.
- **[PLAN_MEJORA.md](PLAN_MEJORA.md)** — roadmap de mejora por fases, con tareas concretas, archivos afectados y métricas medibles. Nace de una auditoría del código enfocada en la queja de que la UI/UX actual ralentiza el trabajo diario (registro de facturas, creación de cheques, entre otros).
- **[DECISIONES.md](DECISIONES.md)** — reglas de negocio y decisiones estables que el código debe respetar.
- **[RUNBOOK_PRODUCCION.md](RUNBOOK_PRODUCCION.md)** — despliegue, validaciones, respaldo y rollback del sistema local.
- **[INCIDENCIAS_DATOS.md](INCIDENCIAS_DATOS.md)** — casos históricos que requieren auditoría manual y que no deben inferirse automáticamente.

## Cómo mantener esto actualizado

Ambos documentos citan rutas de archivo y números de línea como evidencia. El código se sigue moviendo, así que:

- Cada documento lleva una fecha de "última auditoría" en su encabezado — si pasan varios meses o el archivo referenciado cambió de forma importante, vale la pena re-verificar antes de confiar ciegamente en la línea citada.
- Cuando se complete una fase de `PLAN_MEJORA.md`, márcala como hecha ahí mismo (no la borres — sirve de historial de qué se decidió y por qué) y actualiza `ARQUITECTURA.md` si el cambio alteró el mapa del sistema (nuevo modelo, nueva app, cambio de convención).
- Si se toma una decisión de producto/negocio relevante en conversación con el usuario (ej. cómo debe comportarse el cierre semanal, si `proveedor`/`articulo` necesitan UI propia), regístrala en `ARQUITECTURA.md` bajo la sección correspondiente para no tener que volver a preguntarla.
