import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from flask import Response, render_template, request, send_file
from flask_login import current_user, login_required
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func

from app.extensions import db
from app.models import Account, Payment, PosSale, PosSaleItem, Reservation
from app.security import permission_required
from app.services.local_time import local_now, local_today, utc_bounds_for_local_dates

from . import bp


def parse_period():
    today = local_today()
    default_start = today - timedelta(days=6)
    try:
        start = date.fromisoformat(request.args.get("start", default_start.isoformat()))
        end = date.fromisoformat(request.args.get("end", today.isoformat()))
    except ValueError:
        start, end = default_start, today
    if start > end:
        start, end = end, start
    return start, end


def report_data(start, end):
    start_dt, end_dt = utc_bounds_for_local_dates(start, end)
    query = Payment.query.filter(Payment.status == "CONFIRMADO", Payment.created_at.between(start_dt, end_dt))
    method = request.args.get("method", "")
    if method:
        query = query.filter(Payment.method == method)
    payments = query.order_by(Payment.created_at.desc()).all()
    total = sum((Decimal(p.amount) for p in payments), Decimal("0"))
    by_method = {name: sum((Decimal(p.amount) for p in payments if p.method == name), Decimal("0")) for name in ("EFECTIVO", "TARJETA", "TRANSFERENCIA", "PIX")}
    reservations = Reservation.query.filter(Reservation.date.between(start, end), Reservation.status != "CANCELADA").count()
    pending = db.session.scalar(db.select(func.coalesce(func.sum(Account.balance), 0)).where(Account.status.in_(["ABIERTA", "PARCIALMENTE_PAGADA"]))) or 0
    units = db.session.scalar(
        db.select(func.coalesce(func.sum(PosSaleItem.qty), 0))
        .join(PosSale, PosSaleItem.sale_id == PosSale.id)
        .where(PosSale.created_at.between(start_dt, end_dt), PosSale.status == "PAGADA")
    ) or 0
    ticket_average = total / len(payments) if payments else Decimal("0")
    return {"payments": payments, "total": total, "by_method": by_method, "reservations": reservations, "pending": pending, "units": units, "ticket_average": ticket_average}


@bp.get("")
@login_required
@permission_required("reports.view")
def index():
    start, end = parse_period()
    data = report_data(start, end)
    return render_template("reports/index.html", start=start, end=end, **data)


@bp.get("/exportar.csv")
@login_required
@permission_required("reports.view")
def export_csv():
    start, end = parse_period()
    data = report_data(start, end)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["PROFUT - Reporte de ingresos", f"{start:%d/%m/%Y} al {end:%d/%m/%Y}"])
    writer.writerow(["Fecha", "Comprobante", "Método", "Importe", "Operador"])
    for payment in data["payments"]:
        writer.writerow([payment.created_at.strftime("%d/%m/%Y %H:%M"), payment.receipt_number, payment.method, payment.amount, payment.user.name])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=profut-reporte.csv"})


@bp.get("/exportar.xlsx")
@login_required
@permission_required("reports.view")
def export_excel():
    start, end = parse_period()
    data = report_data(start, end)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ingresos"
    sheet.append(["PROFUT - Reporte de ingresos", f"{start:%d/%m/%Y} al {end:%d/%m/%Y}"])
    sheet.append(["Fecha", "Comprobante", "Método", "Importe", "Operador"])
    for payment in data["payments"]:
        sheet.append([payment.created_at, payment.receipt_number, payment.method, float(payment.amount), payment.user.name])
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 24
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 16
    sheet.column_dimensions["E"].width = 24
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return send_file(stream, as_attachment=True, download_name="profut-reporte.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.get("/exportar.pdf")
@login_required
@permission_required("reports.view")
def export_pdf():
    start, end = parse_period()
    data = report_data(start, end)
    stream = BytesIO()
    pdf = Canvas(stream, pagesize=A4)
    width, height = A4
    pdf.setTitle("PROFUT - Reporte de ingresos")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(45, height - 55, "PROFUT - Reporte de ingresos")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(45, height - 75, f"Periodo: {start:%d/%m/%Y} al {end:%d/%m/%Y}")
    pdf.drawString(45, height - 91, f"Generado por: {current_user.name} - {local_now():%d/%m/%Y %H:%M}")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(45, height - 125, f"Ingresos totales: G. {data['total']:,.0f}")
    y = height - 160
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(45, y, "Fecha")
    pdf.drawString(145, y, "Comprobante")
    pdf.drawString(285, y, "Metodo")
    pdf.drawRightString(width - 45, y, "Importe")
    pdf.setFont("Helvetica", 8)
    for payment in data["payments"]:
        y -= 18
        if y < 55:
            pdf.showPage()
            y = height - 55
        pdf.drawString(45, y, payment.created_at.strftime("%d/%m/%Y %H:%M"))
        pdf.drawString(145, y, payment.receipt_number)
        pdf.drawString(285, y, payment.method)
        pdf.drawRightString(width - 45, y, f"G. {payment.amount:,.0f}")
    pdf.save()
    stream.seek(0)
    return send_file(stream, as_attachment=True, download_name="profut-reporte.pdf", mimetype="application/pdf")
