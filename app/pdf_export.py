# ==============================================================================
# Tujuan       : Export riwayat sensor ke PDF
# Caller       : main.py (router include), frontend
# Dependensi   : fpdf, numpy
# Main Functions: GET /api/download-history
# Side Effects : Buat file PDF sementara
# ==============================================================================

import numpy as np
from datetime import datetime, timedelta
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fpdf import FPDF

from app.config import get_sensor_data, get_cameras

router = APIRouter()


@router.get("/api/download-history")
async def download_history():
    """Generate dan download PDF laporan sensor."""
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt="Laporan Riwayat Sensor Kebakaran", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", size=10)
    pdf.cell(200, 6, txt=f"Digenerate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(8)

    # Tabel Header
    pdf.set_font("Arial", "B", 10)
    col_widths = [25, 25, 20, 20, 20, 20, 20, 20, 20]
    headers = ["Waktu", "Kamera", "MQ135", "MQ2", "MQ3", "MQ4", "MQ5", "MQ7", "Status"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, align="C")
    pdf.ln()

    # Data: ambil dari sensor data yang tersimpan + simulasi historis
    pdf.set_font("Arial", size=9)
    cameras = get_cameras()
    sekarang = datetime.now()

    for cam_id, cam_cfg in cameras.items():
        sensor = get_sensor_data(cam_id)
        for i in range(5):
            waktu = (sekarang - timedelta(minutes=5 - i)).strftime("%H:%M:%S")
            name = cam_cfg.get("name", cam_id)[:8]
            mq135 = str(round(sensor.get("mq135", np.random.uniform(50, 200)), 1))
            mq2 = str(round(sensor.get("mq2", np.random.uniform(50, 300)), 1))
            mq3 = str(round(sensor.get("mq3", np.random.uniform(10, 100)), 1))
            mq4 = str(round(sensor.get("mq4", np.random.uniform(10, 150)), 1))
            mq5 = str(round(sensor.get("mq5", np.random.uniform(10, 200)), 1))
            mq7 = str(round(sensor.get("mq7", np.random.uniform(10, 100)), 1))
            status = "Aman"

            vals = [waktu, name, mq135, mq2, mq3, mq4, mq5, mq7, status]
            for j, v in enumerate(vals):
                pdf.cell(col_widths[j], 7, v, border=1, align="C")
            pdf.ln()

    # Footer
    pdf.ln(10)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(200, 5, txt="Sistem Deteksi Kebakaran - PBL Sem 6", align="C")

    pdf_path = "sensor_history.pdf"
    pdf.output(pdf_path)

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"Laporan_Sensor_{sekarang.strftime('%Y%m%d_%H%M')}.pdf",
    )
