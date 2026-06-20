"""
Importador de portafolios desde Excel/CSV de brokers venezolanos.
Detecta automáticamente el formato y extrae símbolo, cantidad y precio.
"""
import io
from typing import Optional

def detectar_formato(nombre_archivo: str) -> str:
    ext = nombre_archivo.lower().split('.')[-1]
    if ext in ['xlsx', 'xls']:
        return 'excel'
    elif ext == 'csv':
        return 'csv'
    return 'desconocido'


def parsear_numero(valor) -> float:
    """Convierte número venezolano a float."""
    if valor is None or str(valor).strip() in ['', '-', 'N/A']:
        return 0.0
    try:
        s = str(valor).strip().replace(' ', '')
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0


def importar_excel(contenido: bytes, nombre: str) -> list[dict]:
    """Importa activos desde un archivo Excel de broker venezolano."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)
        ws = wb.active
        filas = list(ws.iter_rows(values_only=True))
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo Excel: {e}")

    activos = []
    # Buscar encabezados en las primeras 10 filas
    header_row = None
    col_simb = col_cant = col_precio = None

    keywords_simb   = ['simbolo', 'símbolo', 'simb', 'ticker', 'accion', 'acción', 'titulo', 'título']
    keywords_cant   = ['cantidad', 'cant', 'titulos', 'títulos', 'acciones', 'unidades']
    keywords_precio = ['precio', 'costo', 'valor', 'promedio', 'prom', 'compra']

    for i, fila in enumerate(filas[:10]):
        fila_lower = [str(c).lower().strip() if c else '' for c in fila]
        for kw in keywords_simb:
            if any(kw in cel for cel in fila_lower):
                header_row = i
                for j, cel in enumerate(fila_lower):
                    if any(kw in cel for kw in keywords_simb):
                        col_simb = j
                    elif any(kw in cel for kw in keywords_cant):
                        col_cant = j
                    elif any(kw in cel for kw in keywords_precio):
                        col_precio = j
                break
        if header_row is not None:
            break

    if header_row is None or col_simb is None:
        raise ValueError("No se encontraron columnas de símbolo en el archivo. Verifica que tenga columnas: Símbolo, Cantidad, Precio.")

    for fila in filas[header_row + 1:]:
        if not fila or not fila[col_simb]:
            continue
        simb = str(fila[col_simb]).strip().upper()
        if not simb or simb in ['NONE', 'SIMBOLO', 'SÍMBOLO', 'TOTAL']:
            continue
        cant   = parsear_numero(fila[col_cant])   if col_cant   is not None and col_cant   < len(fila) else 0
        precio = parsear_numero(fila[col_precio]) if col_precio is not None and col_precio < len(fila) else 0
        if simb and cant > 0:
            activos.append({
                'simbolo': simb,
                'cantidad': cant,
                'precio_promedio': precio,
                'comision': 0,
                'registro': 0,
                'iva': 16,
            })

    return activos


def importar_csv(contenido: bytes) -> list[dict]:
    """Importa activos desde CSV."""
    import csv
    texto = contenido.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(texto))
    activos = []

    for fila in reader:
        keys = {k.lower().strip(): v for k, v in fila.items()}
        simb = (keys.get('simbolo') or keys.get('símbolo') or
                keys.get('ticker') or keys.get('accion') or '').strip().upper()
        if not simb:
            continue
        cant   = parsear_numero(keys.get('cantidad') or keys.get('titulos') or keys.get('acciones') or 0)
        precio = parsear_numero(keys.get('precio') or keys.get('costo') or keys.get('promedio') or 0)
        if cant > 0:
            activos.append({
                'simbolo': simb,
                'cantidad': cant,
                'precio_promedio': precio,
                'comision': 0,
                'registro': 0,
                'iva': 16,
            })
    return activos


def importar_archivo(contenido: bytes, nombre: str) -> list[dict]:
    """Punto de entrada principal — detecta formato y parsea."""
    formato = detectar_formato(nombre)
    if formato == 'excel':
        return importar_excel(contenido, nombre)
    elif formato == 'csv':
        return importar_csv(contenido)
    else:
        raise ValueError(f"Formato no soportado: {nombre}. Usa .xlsx o .csv")
