import unittest
from pathlib import Path

from app.routers.portfolio import _fee_total, _normalizar_simbolo


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "app" / "routers" / "portfolio.py"
TEMPLATE = ROOT / "templates" / "portafolio.html"


class PortfolioPositionManagementTests(unittest.TestCase):
    def test_fee_total_includes_commission_registry_and_vat_on_commission(self):
        self.assertAlmostEqual(_fee_total(100, 10, 16), 126.0)
        self.assertEqual(_fee_total(-1, -2, -3), 0.0)

    def test_symbols_are_normalized(self):
        self.assertEqual(_normalizar_simbolo(" rst.b "), "RST.B")

    def test_router_registers_buy_reduce_correct_delete_and_ledger(self):
        source = ROUTER.read_text(encoding="utf-8")
        for marker in (
            'app.add_api_route("/agregar", agregar',
            'app.add_api_route("/reducir", reducir',
            'app.add_api_route("/editar", editar',
            'app.add_api_route("/eliminar", eliminar',
            'tipo="compra"',
            'tipo="venta"',
            'TransaccionHistorial',
            'cant > _to_float(activo.cantidad)',
        ):
            self.assertIn(marker, source)

    def test_buy_uses_weighted_average_and_reduce_preserves_average_price(self):
        source = ROUTER.read_text(encoding="utf-8")
        self.assertIn("(costo_anterior + costo_nuevo) / cantidad_total", source)
        self.assertIn("El costo promedio por título no cambia", source)
        self.assertNotIn("activo.precio_promedio = precio\n", source.split("async def reducir", 1)[1].split("async def editar", 1)[0])

    def test_delete_is_administrative_and_removes_symbol_history(self):
        source = ROUTER.read_text(encoding="utf-8")
        delete_block = source.split("async def eliminar", 1)[1]
        self.assertIn("TransaccionHistorial.simbolo == simbolo", delete_block)
        self.assertIn("delete(synchronize_session=False)", delete_block)

    def test_template_exposes_clear_position_management_on_desktop_and_mobile(self):
        html = TEMPLATE.read_text(encoding="utf-8")
        for marker in (
            "Mi portafolio",
            "Costo promedio",
            "Precio actual",
            "Valor actual",
            "Ganancia / pérdida",
            "Comprar / sumar",
            "Vender / reducir",
            "Corregir posición",
            "Eliminar posición e historial",
            'action="/reducir"',
            'class="mobile-positions"',
            "Historial de operaciones",
        ):
            self.assertIn(marker, html)

    def test_existing_usd_benchmark_contract_remains_available(self):
        html = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("/api/v5/portfolio-benchmark", html)
        self.assertIn("Benchmark V5 deshabilitado", html)
        self.assertIn('data-prof="pnl-usd"', html)
        self.assertIn('data-prof="cost-usd"', html)


if __name__ == "__main__":
    unittest.main()
