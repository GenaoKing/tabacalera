# app/management/commands/resumen_perdidas_cosecha.py
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from cosecheros.utils.reportes import calcular_saldos_cosecha
import csv

class Command(BaseCommand):
    help = "Lista (y opcionalmente exporta) la pérdida acumulada (saldo > 0) por cosechero para una cosecha dada."

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

        total_perdida = sum((r["saldo"] for r in resultados), Decimal('0'))

        self.stdout.write(self.style.NOTICE(
            f"\nCosecha #{cosecha_id} — Pérdida acumulada (sólo saldos > 0): {total_perdida:,.2f}\n"
        ))
        self.stdout.write(self.style.SUCCESS(f"{'Cosechero':35} {'Gastos':>15} {'Producción':>15} {'Saldo(+nos debe)':>20}"))
        self.stdout.write("-" * 90)
        for r in resultados:
            c = r["cosechero"]
            nombre = f"{c.nombre} {c.apellido}".strip()
            self.stdout.write(f"{nombre:35} {r['gastos']:>15,.2f} {r['produccion']:>15,.2f} {r['saldo']:>20,.2f}")

        self.stdout.write("-" * 90)
        self.stdout.write(self.style.NOTICE(f"TOTAL PÉRDIDA ACUMULADA: {total_perdida:,.2f}\n"))

        if csv_path:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["cosecha_id", "cosechero_id", "cosechero_nombre", "gastos", "produccion", "saldo"])
                for r in resultados:
                    c = r["cosechero"]
                    w.writerow([
                        cosecha_id,
                        c.id,
                        f"{c.nombre} {c.apellido}".strip(),
                        f"{r['gastos']:.2f}",
                        f"{r['produccion']:.2f}",
                        f"{r['saldo']:.2f}",
                    ])
            self.stdout.write(self.style.SUCCESS(f"CSV escrito en: {csv_path}"))
