# app/management/commands/resumen_perdidas_cosecha.py
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from app.number_format import format_number
from cosecheros.services import calcular_saldos_cosecha
import csv

class Command(BaseCommand):
    help = (
        "Concilia, para una cosecha dada, cuánto le debemos a cada cosechero "
        "(producción > gastos) y cuánto nos debe cada uno (gastos > producción)."
    )

    def add_arguments(self, parser):
        parser.add_argument('--cosecha', type=int, required=True, help='ID de la cosecha (ej. 2)')
        parser.add_argument('--csv', type=str, help='Ruta de salida CSV opcional')

    def handle(self, *args, **options):
        cosecha_id = options['cosecha']
        csv_path = options.get('csv')

        try:
            resultados = calcular_saldos_cosecha(cosecha_id)
        except Exception as e:
            raise CommandError(str(e))

        # saldo > 0  => el cosechero nos debe (gastó más de lo que produjo)
        # saldo < 0  => se le debe a él (produjo más de lo que gastó)
        nos_deben = [r for r in resultados if r["saldo"] > 0]
        les_debemos = [r for r in resultados if r["saldo"] < 0]

        total_nos_deben = sum((r["saldo"] for r in nos_deben), Decimal('0'))
        total_les_debemos = sum((-r["saldo"] for r in les_debemos), Decimal('0'))
        neto = total_nos_deben - total_les_debemos

        def imprimir_grupo(titulo, filas):
            self.stdout.write(self.style.SUCCESS(f"\n{titulo}"))
            self.stdout.write(
                f"{'Cosechero':35} {'Gastos':>15} {'Producción':>15} "
                f"{'Saldo':>15} {'Última actividad':>18}"
            )
            self.stdout.write("-" * 102)
            for r in filas:
                c = r["cosechero"]
                nombre = f"{c.nombre} {c.apellido}".strip()
                marca = ' [SIN ENTREGA]' if r['sin_produccion_entregada'] else ''
                ultima = r['ultima_actividad_fecha'].isoformat() if r['ultima_actividad_fecha'] else 'N/A'
                self.stdout.write(
                    f"{(nombre + marca):35} {r['gastos']:>15,.2f} "
                    f"{r['produccion']:>15,.2f} {r['saldo']:>15,.2f} {ultima:>18}"
                )

        imprimir_grupo(f"Cosecha #{cosecha_id} — Nos deben (saldo > 0)", nos_deben)
        self.stdout.write(self.style.NOTICE(f"Subtotal nos deben: {format_number(total_nos_deben)}\n"))

        imprimir_grupo(f"Cosecha #{cosecha_id} — Les debemos (saldo < 0)", les_debemos)
        self.stdout.write(self.style.NOTICE(f"Subtotal les debemos: {format_number(total_les_debemos)}\n"))

        self.stdout.write(self.style.WARNING(f"NETO (nos deben - les debemos): {format_number(neto)}\n"))

        if csv_path:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow([
                    "cosecha_id", "cosechero_id", "cosechero_nombre",
                    "articulos", "avances", "gastos", "produccion", "saldo", "grupo",
                    "cantidad_entregas", "sin_produccion_entregada", "entregas_sin_precio",
                    "tareas", "gasto_por_tarea", "produccion_por_tarea",
                    "quintales_producidos", "quintales_por_tarea",
                    "ultima_actividad", "tipos_ultima_actividad", "precision_fecha",
                ])
                for r in resultados:
                    c = r["cosechero"]
                    grupo = "nos_deben" if r["saldo"] > 0 else ("les_debemos" if r["saldo"] < 0 else "saldado")
                    w.writerow([
                        cosecha_id,
                        c.id,
                        f"{c.nombre} {c.apellido}".strip(),
                        format_number(r['gastos_articulos']),
                        format_number(r['gastos_avances']),
                        format_number(r['gastos']),
                        format_number(r['produccion']),
                        format_number(r['saldo']),
                        grupo,
                        r['cantidad_entregas'],
                        'si' if r['sin_produccion_entregada'] else 'no',
                        r['entregas_sin_precio'],
                        format_number(r['tareas_sembradas']),
                        format_number(r['gasto_promedio_tarea']) if r['gasto_promedio_tarea'] is not None else '',
                        format_number(r['produccion_promedio_tarea']) if r['produccion_promedio_tarea'] is not None else '',
                        format_number(r['quintales_producidos']),
                        format_number(r['quintales_promedio_tarea']) if r['quintales_promedio_tarea'] is not None else '',
                        r['ultima_actividad_fecha'].isoformat() if r['ultima_actividad_fecha'] else '',
                        '|'.join(r['ultima_actividad_tipos']),
                        r['ultima_actividad_precision'] or '',
                    ])
            self.stdout.write(self.style.SUCCESS(f"CSV escrito en: {csv_path}"))
