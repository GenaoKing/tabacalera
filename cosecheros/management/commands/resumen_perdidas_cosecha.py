# app/management/commands/resumen_perdidas_cosecha.py
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
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
            self.stdout.write(f"{'Cosechero':35} {'Gastos':>15} {'Producción':>15} {'Saldo':>15}")
            self.stdout.write("-" * 82)
            for r in filas:
                c = r["cosechero"]
                nombre = f"{c.nombre} {c.apellido}".strip()
                self.stdout.write(f"{nombre:35} {r['gastos']:>15,.2f} {r['produccion']:>15,.2f} {r['saldo']:>15,.2f}")

        imprimir_grupo(f"Cosecha #{cosecha_id} — Nos deben (saldo > 0)", nos_deben)
        self.stdout.write(self.style.NOTICE(f"Subtotal nos deben: {total_nos_deben:,.2f}\n"))

        imprimir_grupo(f"Cosecha #{cosecha_id} — Les debemos (saldo < 0)", les_debemos)
        self.stdout.write(self.style.NOTICE(f"Subtotal les debemos: {total_les_debemos:,.2f}\n"))

        self.stdout.write(self.style.WARNING(f"NETO (nos deben - les debemos): {neto:,.2f}\n"))

        if csv_path:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["cosecha_id", "cosechero_id", "cosechero_nombre", "gastos", "produccion", "saldo", "grupo"])
                for r in resultados:
                    c = r["cosechero"]
                    grupo = "nos_deben" if r["saldo"] > 0 else ("les_debemos" if r["saldo"] < 0 else "saldado")
                    w.writerow([
                        cosecha_id,
                        c.id,
                        f"{c.nombre} {c.apellido}".strip(),
                        f"{r['gastos']:.2f}",
                        f"{r['produccion']:.2f}",
                        f"{r['saldo']:.2f}",
                        grupo,
                    ])
            self.stdout.write(self.style.SUCCESS(f"CSV escrito en: {csv_path}"))
