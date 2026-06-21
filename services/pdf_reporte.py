"""
Generador de reportes PDF mensuales para Caracas Bull.
Usa reportlab para crear PDFs profesionales con el diseño de la app.
"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# ── Paleta de colores Caracas Bull ────────────────────────────────────────────
VERDE    = colors.HexColor("#00c896")
OSCURO   = colors.HexColor("#080f0f")
GRIS     = colors.HexColor("#6b9090")
ROJO     = colors.HexColor("#ff4d6a")
DORADO   = colors.HexColor("#f0c040")
BLANCO   = colors.white
BG_CARD  = colors.HexColor("#0f1a1a")
BG_TABLE = colors.HexColor("#162020")


def fmt_bs(valor: float) -> str:
    """Formatea número en formato venezolano."""
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} Bs"


def fmt_pct(valor: float) -> str:
    signo = "+" if valor > 0 else ""
    return f"{signo}{valor:.2f}%"


def generar_reporte(
    usuario_nombre: str,
    usuario_email: str,
    plan: str,
    filas: list,
    resumen: dict,
    tasa: float,
    mes: str = None,
) -> bytes:
    """
    Genera el reporte PDF mensual y devuelve los bytes.
    
    filas: lista de dicts con simb, cantidad, precio_prom, precio_actual,
           val_mkt, ganancia, rend_pct, peso_pct
    resumen: dict con total_inv, total_mkt, gan_bs, gan_usd, rend
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        title=f"Reporte Mensual — Caracas Bull",
        author="Caracas Bull",
    )

    styles = getSampleStyleSheet()
    mes_str = mes or datetime.now().strftime("%B %Y").capitalize()

    # ── Estilos personalizados ─────────────────────────────────────────────────
    titulo_style = ParagraphStyle(
        'Titulo', parent=styles['Normal'],
        fontSize=22, textColor=VERDE, fontName='Helvetica-Bold',
        spaceAfter=4, alignment=TA_LEFT,
    )
    subtitulo_style = ParagraphStyle(
        'Subtitulo', parent=styles['Normal'],
        fontSize=11, textColor=GRIS, fontName='Helvetica',
        spaceAfter=2,
    )
    seccion_style = ParagraphStyle(
        'Seccion', parent=styles['Normal'],
        fontSize=13, textColor=VERDE, fontName='Helvetica-Bold',
        spaceBefore=16, spaceAfter=8,
    )
    normal_style = ParagraphStyle(
        'Normal2', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor("#e8f0f0"),
        fontName='Helvetica',
    )
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=8, textColor=GRIS, alignment=TA_CENTER,
    )

    story = []

    # ── HEADER ────────────────────────────────────────────────────────────────
    # Logo + nombre
    header_data = [[
        Paragraph("<b>CaracasBull</b>", ParagraphStyle(
            'Logo', fontSize=18, textColor=VERDE, fontName='Helvetica-Bold'
        )),
        Paragraph(
            f"<b>Reporte Mensual</b><br/>{mes_str}",
            ParagraphStyle('FechaTitulo', fontSize=11, textColor=GRIS,
                          fontName='Helvetica', alignment=TA_RIGHT)
        )
    ]]
    header_table = Table(header_data, colWidths=[9*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=VERDE, spaceAfter=12))

    # Info del usuario
    story.append(Paragraph(f"<b>{usuario_nombre}</b> &nbsp;·&nbsp; {usuario_email} &nbsp;·&nbsp; Plan {plan.capitalize()}", normal_style))
    story.append(Spacer(1, 16))

    # ── RESUMEN EJECUTIVO ──────────────────────────────────────────────────────
    story.append(Paragraph("Resumen del portafolio", seccion_style))

    color_gan = VERDE if resumen.get('gan_bs', 0) >= 0 else ROJO
    color_rend = VERDE if resumen.get('rend', 0) >= 0 else ROJO

    resumen_data = [
        ["Métrica", "Valor"],
        ["Valor de mercado", fmt_bs(resumen.get('total_mkt', 0))],
        ["Costo total invertido", fmt_bs(resumen.get('total_inv', 0))],
        ["Ganancia / Pérdida (Bs)", fmt_bs(resumen.get('gan_bs', 0))],
        ["Ganancia / Pérdida (USD)", f"${resumen.get('gan_usd', 0):,.2f}"],
        ["Rendimiento total", fmt_pct(resumen.get('rend', 0))],
        ["Tasa BCV usada", fmt_bs(tasa) if tasa > 0 else "No configurada"],
        ["Número de posiciones", str(len(filas))],
    ]

    resumen_table = Table(resumen_data, colWidths=[9*cm, 8*cm])
    resumen_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), VERDE),
        ('TEXTCOLOR', (0,0), (-1,0), OSCURO),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BACKGROUND', (0,1), (-1,-1), BG_TABLE),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor("#e8f0f0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [BG_TABLE, BG_CARD]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#1e3030")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('FONTNAME', (0,3), (0,3), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1,3), (1,3), color_gan),
        ('TEXTCOLOR', (1,5), (1,5), color_rend),
        ('FONTNAME', (1,3), (1,3), 'Helvetica-Bold'),
        ('FONTNAME', (1,5), (1,5), 'Helvetica-Bold'),
    ]))
    story.append(resumen_table)
    story.append(Spacer(1, 20))

    # ── DETALLE DE POSICIONES ──────────────────────────────────────────────────
    if filas:
        story.append(Paragraph("Detalle de posiciones", seccion_style))

        cols = ["Símbolo", "Cant.", "P. Costo", "P. Mercado", "Val. Mkt", "Ganancia", "Rend.", "Peso"]
        detalle_data = [cols]

        for f in filas:
            gan = f.get('ganancia', 0)
            rend = f.get('rend_pct', 0)
            detalle_data.append([
                f.get('simb', ''),
                str(int(f.get('cantidad', 0))),
                fmt_bs(f.get('precio_prom', 0)),
                fmt_bs(f.get('precio_actual', 0)),
                fmt_bs(f.get('val_mkt', 0)),
                fmt_bs(gan),
                fmt_pct(rend),
                f"{f.get('peso_pct', 0):.1f}%",
            ])

        col_widths = [2*cm, 1.2*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 1.8*cm, 1.5*cm]
        detalle_table = Table(detalle_data, colWidths=col_widths, repeatRows=1)

        # Colores dinámicos por ganancia
        table_styles = [
            ('BACKGROUND', (0,0), (-1,0), VERDE),
            ('TEXTCOLOR', (0,0), (-1,0), OSCURO),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,1), (-1,-1), BG_TABLE),
            ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor("#e8f0f0")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [BG_TABLE, BG_CARD]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#1e3030")),
            ('PADDING', (0,0), (-1,-1), 6),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ]

        for i, f in enumerate(filas, start=1):
            gan = f.get('ganancia', 0)
            rend = f.get('rend_pct', 0)
            c_gan  = VERDE if gan  >= 0 else ROJO
            c_rend = VERDE if rend >= 0 else ROJO
            table_styles.append(('TEXTCOLOR', (5, i), (5, i), c_gan))
            table_styles.append(('TEXTCOLOR', (6, i), (6, i), c_rend))
            table_styles.append(('FONTNAME',  (5, i), (6, i), 'Helvetica-Bold'))

        detalle_table.setStyle(TableStyle(table_styles))
        story.append(detalle_table)

    story.append(Spacer(1, 24))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1e3030"), spaceAfter=8))
    story.append(Paragraph(
        f"Generado por Caracas Bull · caracasbull.com · {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        "Este reporte es de caracter informativo. Caracas Bull no es broker ni asesor financiero. No realizamos operaciones bursátiles. Consulte con un profesional antes de tomar decisiones de inversion.",
        footer_style
    ))

    doc.build(story)
    return buffer.getvalue()
