# BVC Tracker

Seguimiento en tiempo real del mercado de renta variable de la Bolsa de Valores de Caracas.

## Estructura del proyecto

```
bvc_tracker/
├── main.py                  # Rutas FastAPI (solo enrutamiento)
├── requirements.txt
├── portafolio.json          # Creado automáticamente al agregar activos
├── config.json              # Creado automáticamente (tasa BCV)
│
├── services/
│   ├── bvc.py               # Comunicación con la API de la BVC + caché
│   └── portafolio.py        # Lógica de negocio: CRUD + cálculos
│
├── templates/               # Jinja2 templates
│   ├── base.html            # Layout base (header, ticker, nav)
│   ├── pizarra.html         # Tabla del mercado
│   ├── portafolio.html      # Portafolio personal con modales
│   └── detalle.html         # Detalle + gráfica de velas + profundidad
│
└── static/
    ├── css/main.css         # Sistema de diseño completo (dark theme)
    └── js/main.js           # Reloj en tiempo real
```

## Instalación

```bash
pip install -r requirements.txt
python main.py
```

Abrir en: http://localhost:8000

## Mejoras respecto a la versión anterior

- ✅ Funciones duplicadas eliminadas
- ✅ Caché de 60 segundos para datos de la BVC (evita saturar el servidor)
- ✅ Manejo de errores en todos los requests externos
- ✅ HTML generado con templates Jinja2 (no más `html += "..."`)
- ✅ Lógica de negocio separada del enrutamiento
- ✅ `limpiar_float()` unificado como `_to_float()` usado consistentemente
- ✅ Editar y eliminar activos del portafolio
- ✅ Tabla ordenable por cualquier columna (clic en encabezado)
- ✅ Dos gráficas: composición (dona) y ganancia por activo (barras)
- ✅ Diseño dark responsivo con sistema de variables CSS
- ✅ Ticker inferior con animación CSS pura
- ✅ Reloj en tiempo real

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `PORT` | `8000` | Puerto del servidor |
