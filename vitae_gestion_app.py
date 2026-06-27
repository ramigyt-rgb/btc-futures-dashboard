# vitae_gestion_app.py
# Ejecutar en VS Code / terminal:
# pip install streamlit pandas plotly openpyxl
# streamlit run vitae_gestion_app.py
from __future__ import annotations
import sqlite3
import json
import os
import gspread
import numpy as np
from google.oauth2.service_account import Credentials
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple
import pandas as pd
import plotly.express as px
import streamlit as st
# =========================================================
# CONFIG GENERAL
# =========================================================
APP_TITLE = "Sistema de Gestión"
DB_PATH = Path("vitae_gestion.db")
SHEET_ID = st.secrets.get("GOOGLE_SHEET_ID", "")
DATE_FMT = "%Y-%m-%d"
TECH_COLUMNS = ["id", "created_at", "updated_at"]
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        margin-bottom: 0.1rem;
    }
    .subtitle {
        color: #6b7280;
        margin-bottom: 1.2rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
    }
    .small-muted {
        color: #6b7280;
        font-size: 0.88rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# =========================================================
# DEFINICIÓN DE MÓDULOS
# =========================================================
MODULES: Dict[str, Dict[str, Any]] = {
    "Caja VMR": {
        "table": "caja_vmr",
        "empresa": "VMR",
        "tipo": "flujo",
        "descripcion": "Movimientos de efectivo de Vitae Medicina Reproductiva.",
        "fields": [
            ("fecha", "date", True),
            ("concepto", "text", True),
            ("categoria", "select", True, ["Ingreso", "Egreso", "Retiro", "Aporte", "Otro"]),
            ("medio", "select", True, ["Efectivo", "Transferencia", "Tarjeta", "Cheque", "Otro"]),
            ("ingreso", "money", False),
            ("egreso", "money", False),
            ("responsable", "text", False),
            ("observaciones", "textarea", False),
        ],
    },
    "Banco Macro VMR": {
        "table": "banco_macro_vmr",
        "empresa": "VMR",
        "tipo": "flujo",
        "descripcion": "Movimientos bancarios de Banco Macro pertenecientes a VMR.",
        "fields": [
            ("fecha", "date", True),
            ("concepto", "text", True),
            ("tipo_movimiento", "select", True, ["Crédito", "Débito", "Transferencia", "Débito automático", "Impuesto", "Otro"]),
            ("referencia", "text", False),
            ("ingreso", "money", False),
            ("egreso", "money", False),
            ("conciliado", "bool", False),
            ("observaciones", "textarea", False),
        ],
    },
    "Cuenta Corriente VMR": {
        "table": "cuenta_corriente_vmr",
        "empresa": "VMR",
        "tipo": "cuenta_corriente",
        "descripcion": "Cuentas por cobrar y pagar de VMR.",
        "fields": [
            ("fecha", "date", True),
            ("persona_entidad", "text", True),
            ("concepto", "text", True),
            ("tipo", "select", True, ["A cobrar", "A pagar"]),
            ("importe", "money", True),
            ("importe_usd", "money", False),
            ("pagado", "money", False),
            ("pagado_usd", "money", False),
            ("saldo", "money", False),
            ("saldo_usd", "money", False),
            ("vencimiento", "date", False),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado", "Vencido"]),
            ("observaciones", "textarea", False),
        ],
    },

    "Agenda Quirófano": {

        "table": "agenda_quirofano",
    
        "empresa": "VM",
    
        "tipo": "quirófano",
    
        "descripcion": "Agenda diaria, semanal y mensual de cirugías.",
    
        "fields": [

        ("fecha", "date", True),
    
        ("hora_inicio", "text", True),
    
        ("hora_fin", "text", True),
    
        ("duracion_min", "number", True),
    
        ("sala", "select", True, ["Quirófano 1"]),
    
        ("paciente", "text", True),
    
        ("procedimiento", "text", True),
    
        ("medico", "text", True),
    
        ("anestesista", "text", False),
    
        ("estado", "select", True,
    
         ["Programada", "En curso", "Finalizada", "Suspendida", "Cancelada"]),
    
        ("observaciones", "textarea", False),
    
    ],
  },
    "Facturación VMR": {
        "table": "facturacion_vmr",
        "empresa": "VMR",
        "tipo": "facturacion",
        "descripcion": "Control de facturación de procedimientos/pacientes de VMR según planilla quirófano.",
        "fields": [
            ("mes", "date", True),
            ("afiliado", "text", True),
            ("obra_social", "text", True),
            ("procedimiento", "text", True),
            ("medico_responsable", "text", True),
            ("fecha_factura", "date", False),
            ("numero_factura", "text", False),
            ("vencimiento", "date", False),
            ("fecha_pago", "text", False),
            ("valor_pesos", "money", False),
            ("valor_usd", "money", False),
            ("saldo", "money", False),
            ("saldo_usd", "money", False),
            ("estado", "select", True, ["Pendiente", "Completo", "Parcial", "Vencido", "Anulado"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Caja VM": {
        "table": "caja_vm",
        "empresa": "VM",
        "tipo": "flujo",
        "descripcion": "Movimientos de efectivo de Vitae Medical.",
        "fields": [
            ("fecha", "date", True),
            ("concepto", "text", True),
            ("categoria", "select", True, ["Ingreso", "Egreso", "Retiro", "Aporte", "Otro"]),
            ("medio", "select", True, ["Efectivo", "Transferencia", "Tarjeta", "Cheque", "Otro"]),
            ("ingreso", "money", False),
            ("egreso", "money", False),
            ("responsable", "text", False),
            ("observaciones", "textarea", False),
        ],
    },
    "Banco Galicia VM": {
        "table": "banco_galicia_vm",
        "empresa": "VM",
        "tipo": "flujo",
        "descripcion": "Movimientos bancarios de Banco Galicia pertenecientes a VM.",
        "fields": [
            ("fecha", "date", True),
            ("concepto", "text", True),
            ("tipo_movimiento", "select", True, ["Crédito", "Débito", "Transferencia", "Débito automático", "Impuesto", "Otro"]),
            ("referencia", "text", False),
            ("ingreso", "money", False),
            ("egreso", "money", False),
            ("conciliado", "bool", False),
            ("observaciones", "textarea", False),
        ],
    },
    "Cuenta Corriente VM": {
        "table": "cuenta_corriente_vm",
        "empresa": "VM",
        "tipo": "cuenta_corriente",
        "descripcion": "Cuentas por cobrar y pagar de VM.",
        "fields": [
            ("fecha", "date", True),
            ("persona_entidad", "text", True),
            ("concepto", "text", True),
            ("tipo", "select", True, ["A cobrar", "A pagar"]),
            ("importe", "money", True),
            ("importe_usd", "money", False),
            ("pagado", "money", False),
            ("pagado_usd", "money", False),
            ("vencimiento", "date", False),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado", "Vencido"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Facturación VM": {
        "table": "facturacion_vm",
        "empresa": "VM",
        "tipo": "facturacion",
        "descripcion": "Control de facturación de procedimientos/pacientes de Vitae Medical según planilla quirófano.",
        "fields": [
            ("mes", "date", True),
            ("afiliado", "text", True),
            ("obra_social", "text", True),
            ("procedimiento", "text", True),
            ("medico_responsable", "text", True),
            ("fecha_factura", "date", False),
            ("numero_factura", "text", False),
            ("vencimiento", "date", False),
            ("fecha_pago", "text", False),
            ("valor_pesos", "money", False),
            ("valor_usd", "money", False),
            ("estado", "select", True, ["Pendiente", "Completo", "Parcial", "Vencido", "Anulado"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Deudas Impositivas VMR": {
        "table": "deudas_impositivas_vmr",
        "empresa": "VMR",
        "tipo": "deuda",
        "descripcion": "IVA, Ganancias, cargas sociales, autónomos, monotributo u otros impuestos VMR.",
        "fields": [
            ("fecha", "date", True),
            ("impuesto", "select", True, ["IVA", "Ganancias", "Ingresos Brutos", "SUSS", "Monotributo", "Autónomos", "Municipal", "Otro"]),
            ("periodo", "text", True),
            ("importe", "money", True),
            ("pagado", "money", False),
            ("vencimiento", "date", True),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado", "Plan de pago", "Vencido"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Deudas Impositivas VM": {
        "table": "deudas_impositivas_vm",
        "empresa": "VM",
        "tipo": "deuda",
        "descripcion": "IVA, Ganancias, cargas sociales, autónomos, monotributo u otros impuestos VM.",
        "fields": [
            ("fecha", "date", True),
            ("impuesto", "select", True, ["IVA", "Ganancias", "Ingresos Brutos", "SUSS", "Monotributo", "Autónomos", "Municipal", "Otro"]),
            ("periodo", "text", True),
            ("importe", "money", True),
            ("pagado", "money", False),
            ("vencimiento", "date", True),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado", "Plan de pago", "Vencido"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Planes de pagos y préstamos": {
        "table": "planes_pagos_prestamos",
        "empresa": "VITAE",
        "tipo": "deuda",
        "descripcion": "Planes AFIP/ARCA, bancos, financieras, préstamos internos y externos.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("acreedor", "text", True),
            ("detalle", "text", True),
            ("cuotas_totales", "int", False),
            ("cuotas_pagadas", "int", False),
            ("importe_total", "money", True),
            ("saldo", "money", True),
            ("proximo_vencimiento", "date", False),
            ("estado", "select", True, ["Activo", "Finalizado", "Mora", "Refinanciado"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Pagos pendientes Vitae": {
        "table": "pagos_pendientes_vitae",
        "empresa": "VITAE",
        "tipo": "pago_pendiente",
        "descripcion": "Pagos pendientes globales de la empresa.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("proveedor", "text", True),
            ("concepto", "text", True),
            ("importe", "money", True),
            ("pagado", "money", False),
            ("vencimiento", "date", False),
            ("prioridad", "select", True, ["Alta", "Media", "Baja"]),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado", "Vencido"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Gastos comunes": {
        "table": "gastos_comunes",
        "empresa": "VITAE",
        "tipo": "gasto",
        "descripcion": "Gastos compartidos entre VMR y VM.",
        "fields": [
            ("fecha", "date", True),
            ("rubro", "select", True, ["Luz", "Agua", "Gas", "Internet", "Limpieza", "Mantenimiento", "Sueldos", "Insumos", "Alquiler", "Otro"]),
            ("concepto", "text", True),
            ("importe", "money", True),
            ("porcentaje_vmr", "number", False),
            ("porcentaje_vm", "number", False),
            ("pagado", "bool", False),
            ("observaciones", "textarea", False),
        ],
    },
    "Vencimientos": {
        "table": "vencimientos",
        "empresa": "VITAE",
        "tipo": "vencimiento",
        "descripcion": "Calendario general de vencimientos administrativos, impositivos, contratos, habilitaciones e insumos.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("tipo_vencimiento", "select", True, ["Impuesto", "Servicio", "Contrato", "Habilitación", "Seguro", "Medicamento", "Mantenimiento", "Otro"]),
            ("detalle", "text", True),
            ("importe", "money", False),
            ("vencimiento", "date", True),
            ("estado", "select", True, ["Pendiente", "Realizado", "Vencido", "Reprogramado"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Valores Alquileres": {
        "table": "valores_alquileres",
        "empresa": "VITAE",
        "tipo": "contrato_valor",
        "descripcion": "Control de alquileres, aumentos, valores mensuales y vigencia.",
        "fields": [
            ("fecha", "date", True),
            ("inmueble_area", "text", True),
            ("locador", "text", False),
            ("valor_mensual", "money", True),
            ("periodo", "text", True),
            ("fecha_desde", "date", False),
            ("fecha_hasta", "date", False),
            ("proximo_aumento", "date", False),
            ("estado", "select", True, ["Vigente", "Finalizado", "A renegociar"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Tareas Pendientes": {
        "table": "tareas_pendientes",
        "empresa": "VITAE",
        "tipo": "tarea",
        "descripcion": "Seguimiento de tareas administrativas y operativas.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("tarea", "text", True),
            ("responsable", "text", False),
            ("prioridad", "select", True, ["Alta", "Media", "Baja"]),
            ("vencimiento", "date", False),
            ("estado", "select", True, ["Pendiente", "En proceso", "Finalizada", "Cancelada"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Deuda total": {
        "table": "deuda_total_manual",
        "empresa": "VITAE",
        "tipo": "deuda",
        "descripcion": "Carga manual de deudas no contempladas en otros módulos. El tablero también calcula deuda total automática.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("acreedor", "text", True),
            ("concepto", "text", True),
            ("importe_original", "money", True),
            ("pagado", "money", False),
            ("saldo", "money", True),
            ("vencimiento", "date", False),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado", "Vencido", "Refinanciado"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Contratos": {
        "table": "contratos",
        "empresa": "VITAE",
        "tipo": "contrato",
        "descripcion": "Contratos con profesionales, proveedores, alquileres, servicios y convenios.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("contraparte", "text", True),
            ("tipo_contrato", "select", True, ["Profesional", "Proveedor", "Alquiler", "Servicio", "Convenio", "Otro"]),
            ("detalle", "text", True),
            ("inicio", "date", False),
            ("fin", "date", False),
            ("valor", "money", False),
            ("estado", "select", True, ["Vigente", "Vencido", "A renovar", "Finalizado"]),
            ("archivo_link", "text", False),
            ("observaciones", "textarea", False),
        ],
    },
    "Honorarios médicos": {
        "table": "honorarios_medicos",
        "empresa": "VITAE",
        "tipo": "honorario",
        "descripcion": "Honorarios por médico, prestación, estado de pago y empresa.",
        "fields": [
            ("fecha", "date", True),
            ("empresa", "select", True, ["VMR", "VM", "VITAE"]),
            ("medico", "text", True),
            ("paciente", "text", False),
            ("procedimiento", "text", True),
            ("importe", "money", True),
            ("pagado", "money", False),
            ("fecha_pago", "date", False),
            ("estado", "select", True, ["Pendiente", "Parcial", "Pagado"]),
            ("observaciones", "textarea", False),
        ],
    },
    "Gine Vitae": {
        "table": "gine_vitae",
        "empresa": "VM",
        "tipo": "unidad_medica",
        "descripcion": "Gestión de pacientes, prácticas, derivaciones y cirugías de la unidad Gine Vitae.",
        "fields": [
            ("fecha", "date", True),
            ("paciente", "text", True),
            ("dni", "text", False),
            ("telefono", "text", False),
            ("medico", "text", False),
            ("obra_social", "text", False),
            ("practica", "select", True, ["Consulta", "Control anual", "PAP", "Colposcopía", "HPV", "Ecografía", "Histeroscopía", "LEEP", "DIU", "Cirugía", "Otro"]),
            ("estado", "select", True, ["Pendiente", "Turno dado", "Realizado", "Derivado a quirófano", "Cancelado"]),
            ("importe", "money", False),
            ("cobrado", "money", False),
            ("proxima_accion", "text", False),
            ("observaciones", "textarea", False),
        ],
    },
}
# =========================================================
# BASE DE DATOS
# =========================================================
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def sql_type(field_type: str) -> str:
    if field_type in {"money", "number"}:
        return "REAL"
    if field_type == "int":
        return "INTEGER"
    if field_type == "bool":
        return "INTEGER"
    return "TEXT"
def init_db() -> None:
    """Crea tablas y agrega columnas nuevas si actualizás el esquema.

    SQLite no borra columnas viejas, pero la app muestra/exporta solo las columnas vigentes.
    """
    with connect() as conn:
        for cfg in MODULES.values():
            table = cfg["table"]
            columns = ["id INTEGER PRIMARY KEY AUTOINCREMENT", "created_at TEXT", "updated_at TEXT"]
            for field in cfg["fields"]:
                name, ftype = field[0], field[1]
                columns.append(f"{name} {sql_type(ftype)}")
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns)})")

            existing_cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            for field in cfg["fields"]:
                name, ftype = field[0], field[1]
                if name not in existing_cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type(ftype)}")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
        """)
        conn.commit()
def get_df(table: str) -> pd.DataFrame:
    return read_table_from_sheet(table)
               
def get_gs_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    raw_json = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw_json:
        raise RuntimeError("Falta GOOGLE_SERVICE_ACCOUNT_JSON en Secrets.")
    try:
        service_account_info = json.loads(raw_json)
    except json.JSONDecodeError:
        import re

        def fix_private_key(match):

            key = match.group(1)
            key = key.replace("\n", "\\n")
            return f'"private_key": "{key}"'
        fixed_json = re.sub(
            r'"private_key"\s*:\s*"([\s\S]*?)"',
            fix_private_key,
            raw_json,
            count=1
        )
        service_account_info = json.loads(fixed_json)
    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes,
    )
    return gspread.authorize(credentials)
def get_spreadsheet():
    if not SHEET_ID:
        raise RuntimeError("Falta GOOGLE_SHEET_ID en Secrets.")
    gc = get_gs_client()
    return gc.open_by_key(SHEET_ID)
def get_or_create_worksheet(sh, table: str):
    try:
        return sh.worksheet(table)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=table, rows=1000, cols=40)
def sync_table_to_sheet(table: str, allow_empty: bool = False) -> int:
    """
    Sube una tabla local SQLite a Google Sheets.
    No borra la pestaña si la tabla local está vacía, salvo allow_empty=True.
    """
    df = get_df(table)
    if df.empty and not allow_empty:
        st.warning(f"No se sincronizó {table}: tabla local vacía. No se toca Google Sheets.")
        return 0
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, table)
    df = df.copy()
    if df.empty:
        ws.clear()
        ws.update([["Sin datos"]])
        st_cache_data.clear()
        return 0
    df = df.replace([np.inf, -np.inf], "")
    df = df.where(pd.notnull(df), "")
    df = df.astype(str)
    data = [df.columns.tolist()] + df.values.tolist()
    ws.clear()
    ws.update(data)
    
    return len(df)
def sync_df_to_sheet(table: str, df: pd.DataFrame) -> int:
    sh = get_spreadsheet()
    ws = get_or_create_worksheet(sh, table)
    df = df.copy()
    df = df.replace([np.inf, -np.inf], "")
    df = df.where(pd.notnull(df), "")
    df = df.astype(str)
    ws.clear()
    if df.empty:
        ws.update([["Sin datos"]])
        return 0
    data = [df.columns.tolist()] + df.values.tolist()
    ws.update(data)
    
    return len(df)
def sync_all_to_sheets() -> Dict[str, int]:
    """
    Sube todas las tablas NO vacías a Google Sheets.
    No pisa pestañas con 'Sin datos'.
    """
    result: Dict[str, int] = {}
    for cfg in MODULES.values():
        table = cfg["table"]

        try:

            count = sync_table_to_sheet(table, allow_empty=False)
            result[table] = count
        except Exception as e:

            result[table] = -1

            st.warning(f"No se pudo sincronizar {table}: {e}")
    return result
@st.cache_data(ttl=60, show_spinner=False)
def read_table_from_sheet(table: str) -> pd.DataFrame:
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(table)
    except Exception:
        return pd.DataFrame()
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame()
    headers = [str(h).strip() for h in values[0]]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    df = df.dropna(how="all")
    df = df.loc[:, [c for c in df.columns if str(c).strip() != ""]]
    if df.empty:
        return pd.DataFrame()
    if len(df.columns) == 1 and str(df.iloc[0, 0]).strip().lower() == "sin datos":
        return pd.DataFrame()
    return df
def restore_table_from_sheet(table: str) -> int:
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(table)
    except gspread.WorksheetNotFound:
        return 0
    values = ws.get_all_records(expected_headers=ws.row_values(1))
    if not values:
        return 0
    if len(values) == 1:
        first_value = list(values[0].values())[0] if values[0] else ""
        if str(first_value).strip().lower() == "sin datos":
            return 0
    df = pd.DataFrame(values)
    if df.empty:
        return 0
    with connect() as conn:
        existing_cols = [
            r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if not existing_cols:
            return 0
        df = df[[c for c in df.columns if c in existing_cols]].copy()
        if df.empty:
            return 0
        conn.execute(f"DELETE FROM {table}")
        cols = list(df.columns)
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        values = df.replace([np.inf, -np.inf], "").where(pd.notnull(df), "").values.tolist()
        conn.executemany(sql, values)
        conn.commit()
    return len(df)
def restore_all_from_sheets() -> Dict[str, int]:
    result: Dict[str, int] = {}
    for cfg in MODULES.values():
        table = cfg["table"]
        try:
            result[table] = restore_table_from_sheet(table)
        except Exception as e:
            result[table] = -1
            st.warning(f"No se pudo leer {table}: {e}")
    return result
def insert_row(table: str, data: Dict[str, Any]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    data = data.copy()
    if "created_at" in cols:
        data["created_at"] = now
    if "updated_at" in cols:
        data["updated_at"] = now
    data = {k: v for k, v in data.items() if k in cols}
    cols = list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    with connect() as conn:
        conn.execute(sql, [data[c] for c in cols])
        conn.commit()
    sync_table_to_sheet(table)
def bulk_insert_rows(table: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        existing_cols = [
            r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        clean_rows = []
        for row in rows:
            data = dict(row)
            if "created_at" in existing_cols:
                data["created_at"] = now
            if "updated_at" in existing_cols:
                data["updated_at"] = now
            data = {k: v for k, v in data.items() if k in existing_cols}
            if data:
                clean_rows.append(data)
        if not clean_rows:
            return 0
        cols = list(clean_rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        values = [[row.get(c, "") for c in cols] for row in clean_rows]
        conn.executemany(sql, values)
        conn.commit()
    sync_table_to_sheet(table)
    return len(clean_rows)
def save_table_changes(table: str, edited_df: pd.DataFrame, allow_delete: bool = False) -> int:
    """

    - Guarda cambios del st.data_editor de forma segura:
    - No borra toda la tabla.
    - Actualiza filas existentes por id.
    - Inserta filas nuevas.
    - Opcionalmente borra filas eliminadas solo si allow_delete=False.
    """
    if edited_df is None or edited_df.empty:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df = edited_df.copy()
    df = df.replace([np.inf, -np.inf], "")
    df = df.where(pd.notnull(df), "")
    with connect() as conn:
        existing_cols = [
            r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if not existing_cols:
            raise Exception(f"La tabla {table} no existe.")
        current_df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        backup_name = f"{table}_backup"
        current_df.to_sql(backup_name, conn, if_exists="replace", index=False)
        valid_cols = [c for c in df.columns if c in existing_cols]
        if "id" not in valid_cols:
            raise Exception("La tabla editada no tiene columna id. No se puede guardar seguro.")
        df = df[valid_cols].copy()
        current_df["id"] = pd.to_numeric(current_df["id"], errors="coerce")
        current_df = current_df.dropna(subset=["id"])
        current_df["id"] = current_df["id"].astype(int)
        current_ids = set(current_df["id"].tolist())
        updated = 0
        inserted = 0
        deleted = 0
        conn.execute("BEGIN")
        for _, row in df.iterrows():
            raw_id = row.get("id", "")
            is_new = raw_id in ["", None] or str(raw_id).strip().lower() in ["nan", "none"]
            data = row.to_dict()
            if is_new:
                continue
                data.pop("id", None)
                if "created_at" in existing_cols:
                    data["created_at"] = now
                if "updated_at" in existing_cols:
                    data["updated_at"] = now
                insert_cols = [c for c in data.keys() if c in existing_cols and c != "id"]
                placeholders = ", ".join(["?"] * len(insert_cols))
                sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"
                conn.execute(sql, [data[c] for c in insert_cols])
                inserted += 1
            else:
                row_id = int(float(raw_id))
                if row_id not in current_ids:
                    continue
                    data.pop("id", None)
                    if "created_at" in existing_cols:
                        data["created_at"] = now
                    if "updated_at" in existing_cols:
                        data["updated_at"] = now
                    insert_cols = [c for c in data.keys() if c in existing_cols and c != "id"]
                    placeholders = ", ".join(["?"] * len(insert_cols))
                    sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"
                    conn.execute(sql, [data[c] for c in insert_cols])
                    inserted += 1
                else:
                    data.pop("id", None)
                    if "created_at" in data:
                        data.pop("created_at", None)
                    if "updated_at" in existing_cols:
                        data["updated_at"] = now
                    update_cols = [c for c in data.keys() if c in existing_cols and c != "id"]
                    if update_cols:
                        sets = ", ".join([f"{c} = ?" for c in update_cols])
                        sql = f"UPDATE {table} SET {sets} WHERE id = ?"
                        conn.execute(sql, [data[c] for c in update_cols] + [row_id])
                        updated += 1
        if allow_delete:
            edited_ids = set(
                int(float(x))
                for x in df["id"].tolist()
                if str(x).strip().lower() not in ["", "nan", "none"]
            )
            ids_to_delete = current_ids - edited_ids
            for row_id in ids_to_delete:
                conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
                deleted += 1
        conn.commit()
    try:
        sync_table_to_sheet(table)
    except Exception as e:
        st.warning(f"Los cambios se guardaron en la app, pero no se pudo sincronizar Google Sheets: {e}")
    return updated + inserted + deleted
def replace_table_rows(table: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    result = bulk_insert_rows_safe_replace(table, rows)
    return result
def bulk_insert_rows_safe_replace(table: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_rows = [{**row, "created_at": now, "updated_at": now} for row in rows]
    with connect() as conn:
        existing_cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        clean_rows = [
            {k: v for k, v in row.items() if k in existing_cols}
            for row in clean_rows
        ]
        cols = list(clean_rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        values = [[row.get(c, "") for c in cols] for row in clean_rows]
        conn.execute("BEGIN")
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(sql, values)
        conn.commit()
    sync_table_to_sheet(table)
    return len(clean_rows)
def update_row(table: str, row_id: int, data: Dict[str, Any]) -> None:
    data = {**data, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    sets = ", ".join([f"{k} = ?" for k in data.keys()])
    sql = f"UPDATE {table} SET {sets} WHERE id = ?"
    with connect() as conn:
        conn.execute(sql, [*data.values(), row_id])
        conn.commit()
    sync_table_to_sheet(table)
def delete_row(table: str, row_id: int) -> None:
    with connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        conn.commit()
    sync_table_to_sheet(table)
# =========================================================
# HELPERS
# =========================================================
def normalize_money_string(value: Any) -> str:
    if value is None:
        return "0"
    try:
        if pd.isna(value):
            return "0"
    except Exception:
        pass
    text = str(value).strip()
    if text == "":
        return "0"
    text = text.replace("$", "").replace("ARS", "").replace("USD", "")
    text = text.replace(" ", "").replace("\u00a0", "")
    text = text.replace("(", "-").replace(")", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    return text
def money(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if pd.isna(value) or value == "":
            return 0.0
        if isinstance(value, str):
            value = normalize_money_string(value)
        return float(value)
    except Exception:
        return 0.0
def money_usd(value):
    if value is None or str(value).strip().lower() in ["", "none", "nan"]:
        return 0.0
    text = str(value).strip().replace("USD", "").replace("$", "").replace(" ", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0
def fmt_money(value: Any) -> str:
    return f"$ {money(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None
def clean_for_db(value: Any, ftype: str) -> Any:
    if ftype == "date":
        parsed = parse_date(value)
        return parsed.strftime(DATE_FMT) if parsed else ""
    if isinstance(value, date):
        return value.strftime(DATE_FMT)
    if ftype == "bool":
        return 1 if value else 0
    if ftype in {"money", "number"}:
        return float(value or 0)
    if ftype == "int":
        return int(value or 0)
    return value or ""
def default_value(ftype: str, options: List[str] | None = None) -> Any:
    if ftype == "date":
        return date.today()
    if ftype in {"money", "number"}:
        return 0.0
    if ftype == "int":
        return 0
    if ftype == "bool":
        return False
    if ftype == "select":
        return options[0] if options else ""
    return ""
def input_field(field: Tuple, prefix: str, existing: Dict[str, Any] | None = None) -> Any:
    name, ftype, required = field[0], field[1], field[2]
    options = field[3] if len(field) > 3 else None
    label = name.replace("_", " ").title() + (" *" if required else "")
    key = f"{prefix}_{name}"
    old = existing.get(name) if existing else None

    if ftype == "date":
        value = parse_date(old) if old else date.today()
        if value is None:
            value = date.today()
        return st.date_input(label, value=value, key=key)
    if ftype == "money":
        return st.number_input(label, min_value=0.0, step=1000.0, value=money(old), key=key)
    if ftype == "number":
        return st.number_input(label, step=1.0, value=float(money(old)), key=key)
    if ftype == "int":
        return st.number_input(label, min_value=0, step=1, value=int(money(old)), key=key)
    if ftype == "bool":
        return st.checkbox(label, value=bool(old), key=key)
    if ftype == "select":
        idx = 0
        if options and old in options:
            idx = options.index(old)
        return st.selectbox(label, options or [], index=idx, key=key)
    if ftype == "textarea":
        return st.text_area(label, value=str(old or ""), key=key)
    return st.text_input(label, value=str(old or ""), key=key)
def validate_required(cfg: Dict[str, Any], data: Dict[str, Any]) -> List[str]:
    errors = []
    for field in cfg["fields"]:
        name, ftype, required = field[0], field[1], field[2]
        if required and ftype not in {"money", "number", "int", "bool"} and not data.get(name):
            errors.append(name.replace("_", " ").title())
        if required and ftype in {"money", "number"} and money(data.get(name)) <= 0:
            errors.append(name.replace("_", " ").title())
    return errors
def get_field_names(cfg: Dict[str, Any]) -> List[str]:
    return [field[0] for field in cfg["fields"]]
def business_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    cols = [c for c in df.columns if c not in TECH_COLUMNS]
    return df[cols].copy()
def module_business_df(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    field_names = get_field_names(cfg)
    calc_cols = ["saldo", "saldo_movimiento"]
    cols = [c for c in field_names + calc_cols if c in df.columns]
    return df[cols].copy()
def show_business_table(df: pd.DataFrame, height: int | None = None, **kwargs: Any) -> None:
    if height is not None:
        st.dataframe(business_df(df), use_container_width=True, hide_index=True, height=height, **kwargs)
    else:
        st.dataframe(business_df(df), use_container_width=True, hide_index=True, **kwargs)
def show_module_table(df: pd.DataFrame, cfg: Dict[str, Any], **kwargs: Any) -> None:
    st.dataframe(module_business_df(df, cfg), use_container_width=True, hide_index=True, **kwargs)
def add_balance_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    if "ingreso" in df.columns and "egreso" in df.columns:
        df["saldo_movimiento"] = df["ingreso"].apply(money) - df["egreso"].apply(money)
    if "importe" in df.columns and "pagado" in df.columns:
        pass
    if "importe_usd" in df.columns and "pagado_usd" in df.columns:
        pass
    if "valor_pesos" in df.columns:
        df["valor_pesos"] = df["valor_pesos"].apply(money)
    if "valor_usd" in df.columns:
        df["valor_usd"] = df["valor_usd"].apply(money)
    if "importe_total" in df.columns and "saldo" in df.columns:
        df["saldo"] = df["saldo"].apply(money)
    if "importe_original" in df.columns and "saldo" in df.columns:
        df["saldo"] = df["saldo"].apply(money)
    return df
def first_available_date_col(df: pd.DataFrame, module_name: str) -> str | None:
    if "fecha_factura" in df.columns:
        fechas_factura = pd.to_datetime(df["fecha_factura"], errors="coerce")
        if fechas_factura.notna().sum() > 0:
            return "fecha_factura"
    if "mes" in df.columns:
        return "mes"
    for candidate in ["fecha", "vencimiento", "fecha_pago", "fecha_cobro", "proximo_vencimiento", "fecha_desde", "fecha_hasta"]:
        if candidate in df.columns:
            return candidate
    return None
def apply_filters(df: pd.DataFrame, module_name: str) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    st.subheader("Filtros")
    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)

    with c1:
        search = st.text_input("Buscar texto", key=f"search_{module_name}")
    with c2:
        estado = "Todos"
        if "estado" in df.columns:
            estados = [str(x).strip() for x in df["estado"].dropna().unique().tolist() if str(x).strip() != ""]
            estado = st.selectbox("Estado", ["Todos"] + sorted(estados), key=f"estado_{module_name}")
    with c3:
        obra_social = "Todos"
        if "obra_social" in df.columns:
            obra_social = st.selectbox(
                "Obra Social",
                ["Todos"] + sorted(df["obra_social"].dropna().astype(str).unique().tolist())
            )
    with c4:
        procedimiento = "Todos"
        if "procedimiento" in df.columns:
            procedimiento = st.selectbox(
                "Procedimiento",
                ["Todos"] + sorted(df["procedimiento"].dropna().astype(str).unique().tolist())
            )
    with c5:
        medico = "Todos"
        if "medico_responsable" in df.columns:
            medico = st.selectbox(
                "Médico",
                ["Todos"] + sorted(df["medico_responsable"].dropna().astype(str).unique().tolist())
            )
    with c6:
        persona_entidad = "Todos"
        if "persona_entidad" in df.columns:
            persona_entidad = st.selectbox(
                "Proveedor",
                ["Todos"] + sorted(df["persona_entidad"].dropna().astype(str).unique().tolist()),
                key=f"persona_entidad_{module_name}"
            )        
    with c7:
        fecha_desde = st.date_input("Desde", value=date.today() - timedelta(days=3650), key=f"desde_{module_name}")
    with c8:
        fecha_hasta = st.date_input("Hasta", value=date.today() + timedelta(days=3650), key=f"hasta_{module_name}")

    if search:
        mask = df.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        df = df[mask]
    if "estado" in df.columns and estado != "Todos":
        df = df[df["estado"].astype(str).str.strip() == estado]
    if obra_social != "Todos":
        df = df[df["obra_social"].astype(str) == obra_social]
    if procedimiento != "Todos":
        df = df[df["procedimiento"].astype(str) == procedimiento]
    if medico != "Todos":
        df = df[df["medico_responsable"].astype(str) == medico]  
    if "persona_entidad" in df.columns and persona_entidad != "Todos":
        df = df[df["persona_entidad"].astype(str) == persona_entidad]         
    fecha_col = first_available_date_col(df, module_name)
    
    if fecha_col:
        fechas = pd.to_datetime(df[fecha_col], errors="coerce")
        desde_ts = pd.Timestamp(fecha_desde)
        hasta_ts = pd.Timestamp(fecha_hasta)
        # Conserva filas sin fecha para que no desaparezcan registros importados con fecha_factura vacía.
        df = df[fechas.isna() | ((fechas >= desde_ts) & (fechas <= hasta_ts))]
        
    return df
def render_caja_pro_panel(df: pd.DataFrame, module_name: str) -> None:
    if df.empty:
        st.warning("No hay movimientos cargados.")
        return
    data = df.copy()
    data["ingreso"] = data["ingreso"].apply(money) if "ingreso" in data.columns else 0
    data["egreso"] = data["egreso"].apply(money) if "egreso" in data.columns else 0
    data["saldo_movimiento"] = data["ingreso"] - data["egreso"]
    ingresos = data["ingreso"].sum()
    egresos = data["egreso"].sum()
    saldo = ingresos - egresos
    movimientos = len(data)
    ingreso_prom = ingresos / movimientos if movimientos else 0
    egreso_prom = egresos / movimientos if movimientos else 0
    if saldo > ingresos * 0.10:
        salud = "🟢 Excelente"
    elif saldo > 0:
        salud = "🟡 Atención"
    else:
        salud = "🔴 Crítica"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏦 Saldo actual", fmt_money(saldo))
    c2.metric("📈 Ingresos", fmt_money(ingresos))
    c3.metric("📉 Egresos", fmt_money(egresos))
    c4.metric("🧭 Salud financiera", salud)
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("📋 Movimientos", movimientos)
    c6.metric("💰 Resultado neto", fmt_money(saldo))
    c7.metric("💵 Ingreso promedio", fmt_money(ingreso_prom))
    c8.metric("💸 Egreso promedio", fmt_money(egreso_prom))
    st.divider()
    if "fecha" in data.columns:
        data["fecha_dt"] = pd.to_datetime(data["fecha"], errors="coerce")
        graph = data[data["fecha_dt"].notna()].copy()
        if not graph.empty:
            diario = graph.groupby("fecha_dt", as_index=False)[["ingreso", "egreso"]].sum()
            diario["saldo_dia"] = diario["ingreso"] - diario["egreso"]
            diario["saldo_acumulado"] = diario["saldo_dia"].cumsum()
            fig_saldo = px.line(
                diario,
                x="fecha_dt",
                y="saldo_acumulado",
                markers=True,
                title=f"Evolución del saldo - {module_name}",
            )
            fig_saldo.update_layout(
                xaxis_title="Fecha",
                yaxis_title="Saldo acumulado",
                height=420,
            )
            st.plotly_chart(fig_saldo, use_container_width=True)
            diario["mes"] = diario["fecha_dt"].dt.to_period("M").astype(str)
            mensual = diario.groupby("mes", as_index=False)[["ingreso", "egreso"]].sum()
            fig_mes = px.bar(
                mensual,
                x="mes",
                y=["ingreso", "egreso"],
                barmode="group",
                title="Ingresos vs Egresos por mes",
            )
            fig_mes.update_layout(
                xaxis_title="Mes",
                yaxis_title="Importe",
                height=420,
            )
            st.plotly_chart(fig_mes, use_container_width=True)
    g1 = st.container()
    if "concepto" in data.columns:
        gastos = data[data["egreso"] > 0].copy()
        if not gastos.empty:
            top_gastos = (
                gastos.groupby("concepto", as_index=False)["egreso"]
                .sum()
                .sort_values("egreso", ascending=False)
                .head(10)
            )
            fig_gastos = px.bar(
                top_gastos,
                x="concepto",
                y="egreso",
                title="Top 10 egresos por concepto",
            )
            fig_gastos.update_layout(
                xaxis_title="Concepto",
                yaxis_title="Egreso",
                height=420,
            )
            g1.plotly_chart(fig_gastos, use_container_width=True)
def render_banco_pro_panel(df, module_name):
    if df.empty:
        st.warning("No hay movimientos bancarios.")
        return
    data = df.copy()
    data["ingreso"] = data["ingreso"].apply(money)
    data["egreso"] = data["egreso"].apply(money)
    gastos_fijos = data[
        data["concepto"]
        .astype(str)
        .str.contains(
            "SUELDO|IVA|SEGURO|AFIP|DGR|TARJETA|PLAN DE PAGO",
            case=False,
            na=False
        )
    ]["egreso"].sum()
    ingresos = data["ingreso"].sum()
    egresos = data["egreso"].sum()
    saldo = ingresos - egresos
    movimientos = len(data)
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("🏦 Saldo Banco", fmt_money(saldo))
    c2.metric("📈 Créditos", fmt_money(ingresos))
    c3.metric("📉 Débitos", fmt_money(egresos))
    c4.metric("🔄 Movimientos", movimientos)
    c5.metric(
        "📊 Resultado",
        fmt_money(saldo)
    )
    c6, c7, c8 = st.columns(3)
    c6.metric("🏛 Gastos fijos", fmt_money(gastos_fijos))
    c7.metric(
        "💰 Ingreso promedio",
        fmt_money(ingresos / movimientos if movimientos else 0)
    )
    c8.metric(
        "💸 Egreso promedio",
        fmt_money(egresos / movimientos if movimientos else 0)
    )
    st.divider()
# =========================================================
# IMPORTADOR EXCEL / CSV
# =========================================================
def importar_planilla_caja_vitae(df_raw: pd.DataFrame) -> List[Dict[str, Any]]:
    df = df_raw.copy()
    # Buscar la fila donde están los encabezados reales
    header_idx = None
    for idx, row in df.iterrows():
        valores = [str(x) if pd.notna(x) else "" for x in row.tolist()]
        valores = [x.strip().upper() for x in valores]
        texto = " | ".join(valores)
        if "FECHA" in texto and ("DESCRIPCION" in texto or "DESCRIPCIÓN" in texto) and "ENTRADA" in texto and "SALIDA" in texto:
            header_idx = idx
            break
    if header_idx is None:
        raise Exception("No encontré encabezados FECHA / DESCRIPCION / ENTRADA / SALIDA.")
    # Tomar encabezados
    columnas = df.loc[header_idx].astype(str).str.strip().str.upper().tolist()
    data = df.loc[header_idx + 1:].copy()
    data.columns = columnas
    # Normalizar nombres
    data = data.rename(columns={
        "FECHA": "fecha",
        "DESCRIPCION": "concepto",
        "DESCRIPCIÓN": "concepto",
        "ENTRADA": "ingreso",
        "SALIDA": "egreso",
        "OBSERVACION": "observaciones",
        "OBSERVACIÓN": "observaciones",
    })
    columnas_necesarias = ["fecha", "concepto", "ingreso", "egreso", "observaciones"]
    for col in columnas_necesarias:
        if col not in data.columns:
            data[col] = ""
    data = data[columnas_necesarias].copy()
    # Sacar filas basura
    data = data.dropna(how="all")
    data["concepto"] = data["concepto"].astype(str).str.strip()
    data = data[
        ~data["concepto"].str.upper().isin([
            "",
            "TOTAL",
            "SALDO",
            "CAJA EN DOLARES",
            "CAJA EN DÓLARES",
        ])
    ]
    data = data[
        ~data["concepto"].str.upper().str.contains(
            "TOTAL|SALDO|CAJA EN DOLARES|CAJA EN DÓLARES",
            na=False
        )
    ]
    rows = []
    for _, row in data.iterrows():
        fecha = parse_date(row.get("fecha"))
        if not fecha:
            continue
        concepto = str(row.get("concepto", "")).strip()
        if concepto == "":
            continue
        rows.append({
            "fecha": fecha.strftime(DATE_FMT),
            "concepto": concepto,
            "categoria": "Ingreso" if money(row.get("ingreso")) > 0 else "Egreso",
            "medio": "Efectivo",
            "ingreso": money(row.get("ingreso")),
            "egreso": money(row.get("egreso")),
            "responsable": "",
            "observaciones": str(row.get("observaciones", "") or "").strip(),
        })
    return rows
def importar_planilla_banco_vitae(df_raw: pd.DataFrame) -> List[Dict[str, Any]]:
    rows_caja = importar_planilla_caja_vitae(df_raw)
    rows_banco = []
    for row in rows_caja:
        ingreso = money(row.get("ingreso"))
        egreso = money(row.get("egreso"))
        rows_banco.append({
            "fecha": row.get("fecha"),
            "concepto": row.get("concepto"),
            "tipo_movimiento": "Crédito" if ingreso > 0 else "Débito",
            "referencia": "",
            "ingreso": ingreso,
            "egreso": egreso,
            "conciliado": 0,
            "observaciones": row.get("observaciones", ""),
        })
    return rows_banco
def clean_tabular_sheet(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw.empty:
        return df_raw
    raw = df_raw.copy().dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw

    header_keywords = {
        "mes", "afiliado", "obra social", "procedimiento", "medico", "médico",
        "fecha factura", "factura", "vencimiento", "fecha pago", "valor", "estado",
        "cliente", "paciente", "importe", "concepto", "comprobante"
    }

    best_idx = raw.index[0]
    best_score = -1.0
    for idx, row in raw.iterrows():
        values = [str(x).strip().lower() for x in row.tolist() if pd.notna(x) and str(x).strip() != ""]
        if not values:
            continue
        joined = " | ".join(values)
        score = sum(1 for kw in header_keywords if kw in joined) + min(len(values), 10) * 0.05
        if score > best_score:
            best_score = score
            best_idx = idx

    header_values = raw.loc[best_idx].tolist()
    columns: List[str] = []
    used: Dict[str, int] = {}
    for i, value in enumerate(header_values):
        name = str(value).strip() if pd.notna(value) and str(value).strip() else f"Columna_{i + 1}"
        name = name.replace("\n", " ").replace("  ", " ").strip()
        if name in used:
            used[name] += 1
            name = f"{name}_{used[name]}"
        else:
            used[name] = 1
        columns.append(name)

    cleaned = raw.loc[raw.index > best_idx].copy()
    cleaned.columns = columns
    cleaned = cleaned.dropna(how="all")
    cleaned = cleaned.loc[:, [not str(c).lower().startswith("columna_") or not cleaned[c].isna().all() for c in cleaned.columns]]
    return cleaned.reset_index(drop=True)
def read_uploaded_sheet(uploaded_file: Any) -> Dict[str, pd.DataFrame]:
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        try:
            raw = pd.read_csv(uploaded_file, sep=None, engine="python", header=None)
        except Exception:
            uploaded_file.seek(0)
            raw = pd.read_csv(uploaded_file, header=None)
        return {"CSV": clean_tabular_sheet(raw)}
    raw_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None)
    return {name: clean_tabular_sheet(df) for name, df in raw_sheets.items()}
def field_label(field: Tuple) -> str:
    name, _ftype, required = field[0], field[1], field[2]
    return f"{name.replace('_', ' ').title()}{' *' if required else ''}"
def auto_guess_column(target_name: str, source_columns: List[str]) -> str:
    norm_target = target_name.lower().replace("_", " ")
    aliases = {
        "fecha": ["fecha", "dia", "día", "date"],
        "mes": ["mes", "periodo", "período"],
        "afiliado": ["afiliado", "paciente", "cliente", "nombre", "apellido y nombre"],
        "obra_social": ["obra social", "os", "prepaga"],
        "procedimiento": ["procedimiento", "practica", "práctica", "prestacion", "prestación"],
        "medico_responsable": ["medico responsable", "médico responsable", "medico", "médico", "doctor", "profesional", "responsable"],
        "fecha_factura": ["fecha factura", "fecha de factura", "fecha", "factura fecha"],
        "numero_factura": ["n° factura", "nº factura", "n factura", "numero factura", "número factura", "factura", "comprobante"],
        "fecha_pago": ["fecha pago", "fecha de pago", "pago fecha"],
        "valor_pesos": ["valor $", "valor pesos", "valor ars", "importe", "monto", "total", "valor"],
        "valor_usd": ["valor usd", "usd", "dolares", "dólares"],
        "cliente": ["cliente", "paciente", "nombre", "razon social", "razón social"],
        "concepto": ["concepto", "detalle", "descripcion", "descripción", "movimiento", "observacion"],
        "detalle": ["detalle", "concepto", "descripcion", "descripción"],
        "persona_entidad": ["persona", "entidad", "cliente", "proveedor", "paciente", "nombre"],
        "proveedor": ["proveedor", "acreedor", "contraparte", "entidad"],
        "acreedor": ["acreedor", "proveedor", "banco", "entidad"],
        "contraparte": ["contraparte", "proveedor", "profesional", "locador"],
        "medico": ["medico", "médico", "doctor", "profesional"],
        "importe": ["importe", "monto", "total", "valor", "debe", "saldo"],
        "importe_total": ["importe total", "total", "monto", "importe"],
        "importe_original": ["importe original", "deuda", "total", "importe", "monto"],
        "valor": ["valor", "importe", "monto", "total"],
        "valor_mensual": ["valor mensual", "alquiler", "importe", "monto", "total"],
        "ingreso": ["ingreso", "entradas", "haber", "credito", "crédito", "cobro"],
        "egreso": ["egreso", "salidas", "debe", "debito", "débito", "pago"],
        "pagado": ["pagado", "pago", "abonado", "cancelado"],
        "cobrado": ["cobrado", "cobro", "pagado", "abonado"],
        "saldo": ["saldo", "pendiente", "resta", "deuda"],
        "estado": ["estado", "situacion", "situación", "status"],
        "vencimiento": ["vencimiento", "vence", "fecha vencimiento"],
        "proximo_vencimiento": ["proximo vencimiento", "próximo vencimiento", "vencimiento", "vence"],
        "observaciones": ["observaciones", "observacion", "obs", "nota", "comentario"],
        "responsable": ["responsable", "usuario", "encargado"],
        "dni": ["dni", "documento"],
        "telefono": ["telefono", "teléfono", "celular", "whatsapp"],
        "practica": ["practica", "práctica", "prestacion", "prestación", "procedimiento"],
        "periodo": ["periodo", "período", "mes"],
        "comprobante": ["comprobante", "factura", "n factura", "n° factura", "nº factura"],
    }
    candidates = aliases.get(target_name, [norm_target])
    normalized_sources = {str(col).lower().replace("_", " ").strip(): col for col in source_columns}
    for cand in candidates:
        cand = cand.lower().strip()
        if cand in normalized_sources:
            return normalized_sources[cand]
    for cand in candidates:
        cand = cand.lower().strip()
        for src_norm, original in normalized_sources.items():
            if cand in src_norm or src_norm in cand:
                return original
    return "No usar"
def normalize_select_value(value: Any, options: List[str]) -> str:
    if value is None:
        return options[0] if options else ""
    try:
        if pd.isna(value):
            return options[0] if options else ""
    except Exception:
        pass
    text = str(value).strip()
    if text == "":
        return options[0] if options else ""
    for opt in options:
        if text.lower() == opt.lower():
            return opt
    aliases = {
        "cobrado": "Cobrado", "pagado": "Pagado", "pendiente": "Pendiente", "vencido": "Vencido",
        "parcial": "Parcial", "completo": "Completo", "completa": "Completo",
        "realizado": "Realizado", "finalizada": "Finalizada", "finalizado": "Finalizado",
        "alta": "Alta", "media": "Media", "baja": "Baja",
        "credito": "Crédito", "crédito": "Crédito", "debito": "Débito", "débito": "Débito",
    }
    wanted = aliases.get(text.lower())
    if wanted and wanted in options:
        return wanted
    return options[0] if options else text
def clean_import_value(value: Any, field: Tuple) -> Any:
    _name, ftype = field[0], field[1]
    options = field[3] if len(field) > 3 else None
    if ftype == "date":
        parsed = parse_date(value)
        return parsed.strftime(DATE_FMT) if parsed else ""
    if ftype in {"money", "number"}:
        num = pd.to_numeric(normalize_money_string(value), errors="coerce")
        return 0.0 if pd.isna(num) else float(num)
    if ftype == "int":
        num = pd.to_numeric(normalize_money_string(value), errors="coerce")
        return 0 if pd.isna(num) else int(num)
    if ftype == "bool":
        if value is None:
            return 0
        try:
            if pd.isna(value):
                return 0
        except Exception:
            pass
        return 1 if str(value).strip().lower() in ["1", "true", "si", "sí", "x", "ok", "pagado", "conciliado"] else 0
    if ftype == "select":
        return normalize_select_value(value, options or [])
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()
def render_importer(module_name: str, cfg: Dict[str, Any]) -> None:
    table = cfg["table"]
    st.subheader("Importar planilla Excel / CSV")
    st.caption("Subí una planilla, elegí la hoja, mapeá columnas y guardala dentro de este módulo.")

    uploaded_file = st.file_uploader("Subir archivo", type=["xlsx", "xls", "csv"], key=f"upload_{table}")
    if uploaded_file is None:
        st.info("Acepta Excel con varias hojas o CSV.")
        return

    try:
        sheets = read_uploaded_sheet(uploaded_file)
    except Exception as e:
        st.error(f"No pude leer el archivo. Detalle: {e}")
        return

    sheet_names = list(sheets.keys())
    selected_sheet = st.selectbox("Hoja a importar", sheet_names, key=f"sheet_{table}")
    df_original = sheets[selected_sheet].copy().dropna(how="all")
    df_original.columns = [str(c).strip() for c in df_original.columns]

    if df_original.empty:
        st.warning("La hoja seleccionada está vacía.")
        return
    if table in ["caja_vm", "caja_vmr"]:
        st.info("Importador específico de Caja detectado.")
        try:
            rows_caja = importar_planilla_caja_vitae(df_original)
            preview_df = pd.DataFrame(rows_caja)
            st.markdown("#### Previsualización Caja")
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
            modo_caja = st.radio(
                "Modo de importación",
                ["Agregar a registros existentes", "Reemplazar módulo completo"],
                key=f"modo_caja_{table}"
            )
            confirmar = st.checkbox("Confirmo la importación de Caja", key=f"confirm_caja_{table}")
            if st.button("Importar Caja", type="primary", disabled=not confirmar, key=f"btn_caja_{table}"):
                if modo_caja == "Reemplazar módulo completo":
                    count = replace_table_rows(table, rows_caja)
                else:
                    count = bulk_insert_rows(table, rows_caja)
                st.success(f"Caja importada correctamente. Registros cargados: {count}")
                st.rerun()
            return
        except Exception as e:
            st.error(f"No pude procesar esta planilla de caja: {e}")
            return
    if table in ["banco_galicia_vm", "banco_macro_vmr"]:
        st.info("Importador específico de Banco detectado.")
        try:
            rows_banco = importar_planilla_banco_vitae(df_original)
            preview_df = pd.DataFrame(rows_banco)
            st.markdown("#### Previsualización Banco")
            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True
            )
            modo_banco = st.radio(
                "Modo de importación",
                [
                    "Agregar a registros existentes",
                    "Reemplazar módulo completo"
                ],
                key=f"modo_banco_{table}"
            )
            confirmar = st.checkbox(
                "Confirmo la importación bancaria",
                key=f"confirm_banco_{table}"
            )
            if st.button(
                "Importar Banco",
                type="primary",
                disabled=not confirmar,
                key=f"btn_banco_{table}"
            ):
                if modo_banco == "Reemplazar módulo completo":
                    count = replace_table_rows(table, rows_banco)
                else:
                    count = bulk_insert_rows(table, rows_banco)
                st.success(
                    f"Banco importado correctamente. Registros: {count}"
                )
                st.rerun()
            return
        except Exception as e:
            st.error(f"Error procesando planilla bancaria: {e}")
            return
    
    st.markdown("#### Vista previa")
    show_business_table(
        df_original,
        height=700,
    )

    columnas = df_original.columns.tolist()
    st.markdown("#### Mapeo de columnas")
    mapping: Dict[str, str] = {}
    cols = st.columns(2)
    for i, field in enumerate(cfg["fields"]):
        name = field[0]
        guessed = auto_guess_column(name, columnas)
        options = ["No usar"] + columnas
        index = options.index(guessed) if guessed in options else 0
        with cols[i % 2]:
            mapping[name] = st.selectbox(field_label(field), options, index=index, key=f"map_{table}_{name}")

    with st.expander("Opciones avanzadas"):
        modo = st.radio("Modo de importación", ["Agregar a registros existentes", "Reemplazar módulo completo"], key=f"modo_import_{table}")
        saltar_filas_vacias = st.checkbox("Saltar filas completamente vacías", value=True, key=f"skip_empty_{table}")
        validar_obligatorios = st.checkbox("Validar campos obligatorios", value=False, key=f"valid_required_{table}")

    rows: List[Dict[str, Any]] = []
    rejected_rows: List[Dict[str, Any]] = []
    for idx, source_row in df_original.iterrows():
        if saltar_filas_vacias and source_row.isna().all():
            continue
        new_row: Dict[str, Any] = {}
        for field in cfg["fields"]:
            name = field[0]
            mapped_col = mapping.get(name, "No usar")
            if mapped_col == "No usar":
                new_row[name] = clean_for_db(default_value(field[1], field[3] if len(field) > 3 else None), field[1])
                if field[1] == "date" and not field[2]:
                    new_row[name] = ""
            else:
                new_row[name] = clean_import_value(source_row.get(mapped_col), field)
        errors = validate_required(cfg, new_row) if validar_obligatorios else []
        if errors:
            rejected_rows.append({"fila_excel": idx + 2, "motivo": ", ".join(errors), **new_row})
        else:
            rows.append(new_row)

    st.markdown("#### Previsualización final")
    preview_df = pd.DataFrame(rows)
    if preview_df.empty:
        st.warning("No hay filas válidas para importar con el mapeo actual.")
    else:
        show_business_table(preview_df.head(50))
        st.success(f"Filas listas para importar: {len(rows)}")

    if rejected_rows:
        with st.expander(f"Filas rechazadas: {len(rejected_rows)}"):
            show_business_table(pd.DataFrame(rejected_rows))

    col_a, col_b = st.columns([1, 2])
    with col_a:
        confirm_import = st.checkbox("Confirmo la importación", key=f"confirm_import_{table}")
    with col_b:
        st.caption("Si reemplazás el módulo completo, se borran los registros anteriores de este módulo.")
    if st.button("Importar planilla al módulo", type="primary", disabled=(not confirm_import or not rows), key=f"btn_import_{table}"):
        if modo == "Reemplazar módulo completo":
            count = replace_table_rows(table, rows)
        else:
            df_existente = get_df(table)
            df_nuevo = pd.DataFrame(rows)            
            clave = ["mes", "afiliado", "obra_social", "procedimiento", "medico_responsable"]            
            if not df_existente.empty:            
                cols_clave = [c for c in clave if c in df_existente.columns and c in df_nuevo.columns]            
                if cols_clave:           
                    df_existente["_clave"] = df_existente[cols_clave].fillna("").astype(str).agg("|".join, axis=1)            
                    df_nuevo["_clave"] = df_nuevo[cols_clave].fillna("").astype(str).agg("|".join, axis=1)           
                    df_para_agregar = df_nuevo[            
                        ~df_nuevo["_clave"].isin(df_existente["_clave"])            
                    ].copy()           
                    df_para_agregar = df_para_agregar.drop(columns=["_clave"], errors="ignore")          
                else:            
                    df_para_agregar = df_nuevo.copy()            
            else:            
                df_para_agregar = df_nuevo.copy()            
            rows_para_agregar = df_para_agregar.to_dict("records")
            
            count = bulk_insert_rows(table, rows_para_agregar)
            st.info(f"Registros existentes: {len(df_existente)}")
            st.info(f"Registros del archivo: {len(df_nuevo)}")
            st.warning(f"Duplicados evitados: {len(df_nuevo) - len(df_para_agregar)}")
        st.success(f"Importación completada. Registros importados en {module_name}: {count}")
        st.rerun()
# =========================================================
# VISTAS
# =========================================================
def render_header() -> None:
    col1, col2 = st.columns([6.5, 1.2])
    with col1:
        st.markdown(
            '<div class="main-title">🏥 Sistema de Gestión | VITAE </div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div class="subtitle">VMR · Vitae Medicina Reproductiva | VM · Vitae Medical</div>',
            unsafe_allow_html=True
        )
    with col2:
        logo_path = Path("logo_vitae.png")
        if logo_path.exists():
            st.markdown(
                """
                <style>
                .vitae-logo img {
                    width: 170px !important;
                    max-width: 170px !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="vitae-logo">', unsafe_allow_html=True)
            st.image(str(logo_path))
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning("Logo no encontrado")
def get_setting(key: str, default: Any = None) -> Any:
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]
def set_setting(key: str, value: Any) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(value, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, payload, now),
        )
        conn.commit()
DEFAULT_FACT_LABELS = {
    "mes": "Mes",
    "afiliado": "Paciente / Afiliado",
    "obra_social": "Obra social",
    "procedimiento": "Procedimiento",
    "medico_responsable": "Médico",
    "fecha_factura": "Fecha factura",
    "numero_factura": "N° factura",
    "vencimiento": "Vencimiento",
    "fecha_pago": "Fecha pago",
    "valor_pesos": "Valor facturado",
    "valor_usd": "Valor USD",
    "estado": "Estado",
    "observaciones": "Observaciones",
}
def get_fact_labels(module_name: str, cfg: Dict[str, Any]) -> Dict[str, str]:
    key = f"labels_{cfg['table']}"
    saved = get_setting(key, {})
    labels = DEFAULT_FACT_LABELS.copy()
    if isinstance(saved, dict):
        labels.update(saved)
    return labels
def rename_fact_df(df: pd.DataFrame, labels: Dict[str, str]) -> pd.DataFrame:

    return df.rename(columns={c: labels.get(c, c.replace("_", " ").title()) for c in df.columns})
def format_facturacion_table(df: pd.DataFrame, labels: Dict[str, str]) -> pd.DataFrame:
    if df.empty:
        return df
    show = df.copy()
    if "mes" in show.columns:
        show["mes"] = pd.to_datetime(
            show["mes"],
            errors="coerce"            
        ).dt.strftime("%d/%m/%Y")
    show = show.drop(
        columns=[
            "id",
            "created_at",
            "updated_at"
        ],
        errors="ignore"
    )
    for col in ["fecha_factura", "vencimiento", "fecha_pago"]:

        if col in show.columns:
            show[col] = pd.to_datetime(show[col], errors="coerce").dt.strftime("%d/%m/%Y")
            show[col] = show[col].fillna("")
    for col in ["valor_pesos"]:
        if col in show.columns:
            show[col] = show[col].apply(fmt_money)
    if "valor_usd" in show.columns:
        show["valor_usd"] = show["valor_usd"].apply(lambda x: f"USD {money(x):,.2f}")
    show = show.rename(columns={c: labels.get(c, c.replace("_", " ").title()) for c in show.columns})
    return show
def render_analisis_mensual_2026(df: pd.DataFrame):
    st.subheader("📈 Análisis mensual 2026")
    if df.empty or "mes" not in df.columns:
        st.info("No hay datos suficientes para analizar.")
        return
    data = df.copy()
    data["mes"] = pd.to_datetime(data["mes"], errors="coerce")
    data = data[data["mes"].dt.year == 2026]
    if data.empty:
        st.info("No hay registros de 2026.")
        return
    monto_col = None
    for col in [
        "valor_pesos",
        "importe",
        "monto",
        "facturado",
        "total"
    ]:
        if col in data.columns:
            monto_col = col
            break
    if not monto_col:
        st.warning("No encontré columna de monto para calcular facturación.")
        return
    data[monto_col] = data[monto_col].apply(money)
    data["mes_nombre"] = data["mes"].dt.strftime("%Y-%m")
    mensual = (
        data.groupby("mes_nombre")[monto_col]
        .sum()
        .reset_index()
        .rename(columns={monto_col: "facturacion"})
    )
    acumulado = mensual["facturacion"].sum()
    promedio = mensual["facturacion"].mean()
    mejor_mes = mensual.loc[mensual["facturacion"].idxmax()]
    proyeccion = promedio * 12
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Facturación 2026", fmt_money(acumulado))
    col2.metric("Promedio mensual", fmt_money(promedio))
    col3.metric("Mejor mes", mejor_mes["mes_nombre"])
    col4.metric("Proyección anual", fmt_money(proyeccion))
    fig = px.bar(
        mensual,
        x="mes_nombre",
        y="facturacion",
        title="Facturación mensual 2026",
        text_auto=".2s",
    )
    fig.update_layout(
        xaxis_title="Mes",
        yaxis_title="Facturación",
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)
    mensual["acumulado"] = mensual["facturacion"].cumsum()
    fig2 = px.line(
        mensual,
        x="mes_nombre",
        y="acumulado",
        markers=True,
        title="Evolución acumulada 2026",
    )
    fig2.update_layout(
        xaxis_title="Mes",
        yaxis_title="Acumulado",
        height=380,
    )
    st.plotly_chart(fig2, use_container_width=True)
def render_facturacion_pro(module_name: str, cfg: Dict[str, Any]) -> None:
    table = cfg["table"]
    if table != "facturacion_vm":
        try:
            restore_table_from_sheet(table)
        except Exception as e:
            st.warning(f"No se pudo leer Google Sheets para {table}: {e}")
    render_header()
    st.header(module_name)
    st.caption(cfg["descripcion"])
    labels = get_fact_labels(module_name, cfg)
    tab_panel, tab_cargar, tab_importar, tab_editar, tab_columnas, tab_exportar = st.tabs([
        "📊 Panel PRO",
        "➕ Cargar",
        "📥 Importar",
        "✏️ Editar tabla",
        "🏷️ Editar columnas",
        "📤 Exportar",
    ])
    with tab_panel:
        df = add_balance_columns(get_df(table))
        filtered = df.copy()
        if df.empty:
            st.warning("No hay registros cargados.")
        else:
            filtered = apply_filters(df, module_name)            
            if table in ["caja_vm", "caja_vmr"]:
                render_caja_pro_panel(filtered, module_name)
            if table == "cuenta_corriente_vm":
                filtered = filtered.drop(columns=["importe_usd", "pagado_usd"], errors="ignore")
                st.divider()
            if table in ["cuenta_corriente_vm", "cuenta_corriente_vmr"]:
                st.divider()
                st.markdown("#### Tabla limpia")
                tabla_general = module_business_df(
                    add_balance_columns(filtered),
                    cfg
                ).drop(
                    columns=["responsable", "observaciones"],
                    errors="ignore"
                )
                st.dataframe(
                    tabla_general,
                    use_container_width=True,
                    hide_index=True,
                )
                st.markdown("### Tabla limpia")
                tabla_caja = module_business_df(
                    add_balance_columns(filtered),
                    cfg
                ).drop(columns=["observaciones"], errors="ignore")
                tabla = module_business_df(
                    add_balance_columns(filtered),
                    cfg
                )
                tabla = tabla.drop(
                    columns=["responsable", "observaciones"],
                    errors="ignore"
                )
                st.dataframe(
                    tabla,
                    use_container_width=True,
                    hide_index=True,
                )
                # ==================================================
                # DASHBOARD FINANCIERO PROVEEDORES VM
                # ==================================================
                
                st.divider()
                st.markdown("## 📊 Dashboard Financiero Proveedores VM")
                # ---------------------------------------
                # Deuda por proveedor
                # ---------------------------------------
                graf_deuda = filtered.copy()
                graf_deuda["Deuda"] = (
                    pd.to_numeric(graf_deuda["importe"], errors="coerce").fillna(0)
                    -
                    pd.to_numeric(graf_deuda["pagado"], errors="coerce").fillna(0)
                )
                graf_deuda = (
                    graf_deuda[graf_deuda["Deuda"] > 0]
                    .groupby("persona_entidad", as_index=False)["Deuda"]
                    .sum()
                    .rename(columns={"persona_entidad": "Proveedor"})
                    .sort_values("Deuda", ascending=False)
                )
                if not graf_deuda.empty:
                    fig1 = px.bar(
                        graf_deuda,
                        x="Deuda",
                        y="Proveedor",
                        orientation="h",
                        text="Deuda",
                        title="💰 Ranking de deuda por proveedor"
                    )
                    fig1.update_layout(
                        height=500,
                        yaxis=dict(categoryorder="total ascending")
                    )
                    st.plotly_chart(
                        fig1,
                        use_container_width=True
                    )
                # ---------------------------------------
                # Vencimientos próximos
                # ---------------------------------------
                if "vencimiento" in filtered.columns:
                    venc_df = filtered.copy()
                    venc_df["vencimiento"] = pd.to_datetime(
                        venc_df["vencimiento"],
                        dayfirst=True,
                        errors="coerce"
                    )
                    venc_df["saldo"] = (
                        pd.to_numeric(
                            venc_df["importe"],
                            errors="coerce"
                        ).fillna(0)
                        -
                        pd.to_numeric(
                            venc_df["pagado"],
                            errors="coerce"
                        ).fillna(0)
                    )
                    venc_df = venc_df[
                        venc_df["saldo"] > 0
                    ]
                    venc_resumen = (
                        venc_df.groupby("vencimiento")["saldo"]
                        .sum()
                        .reset_index()
                        .sort_values("vencimiento")
                    )
                    if not venc_resumen.empty:
                        fig2 = px.bar(
                            venc_resumen,
                            x="vencimiento",
                            y="saldo",
                            text="saldo",
                            title="📅 Calendario de vencimientos"
                        )
                        fig2.update_layout(
                            height=400
                        )
                        st.plotly_chart(
                            fig2,
                            use_container_width=True
                        )
                # ---------------------------------------
                # Pagado vs pendiente
                # ---------------------------------------
                pagado_total = pd.to_numeric(filtered["pagado"], errors="coerce").fillna(0).sum()
                pendiente_total = (
                    pd.to_numeric(filtered["importe"], errors="coerce").fillna(0).sum()
                    -
                    pagado_total
                )
                pagado_total = pd.to_numeric(filtered["pagado"], errors="coerce").fillna(0).sum()
                pendiente_total = (
                    pd.to_numeric(filtered["importe"], errors="coerce").fillna(0).sum()
                    -
                    pagado_total
                )
                pie_df = pd.DataFrame({
                    "Estado": [
                        "Pagado",
                        "Pendiente"
                    ],
                    "Monto": [
                        pagado_total,
                        pendiente_total
                    ]
                })
                fig3 = px.pie(
                    pie_df,
                    names="Estado",
                    values="Monto",
                    hole=0.55,
                    title="💳 Pagado vs Pendiente"
                )
                fig3.update_layout(
                    height=450
                )
                st.plotly_chart(
                    fig3,
                    use_container_width=True
                )
                # ---------------------------------------
                # Top facturas pendientes
                # ---------------------------------------
                st.divider()
                st.markdown("### 🚨 Facturas más importantes pendientes")
                top_facturas = filtered.copy()
                top_facturas["saldo"] = (
                    pd.to_numeric(
                        top_facturas["importe"],
                        errors="coerce"
                    ).fillna(0)
                    -
                    pd.to_numeric(
                        top_facturas["pagado"],
                        errors="coerce"
                    ).fillna(0)
                )
                top_facturas = top_facturas[
                    top_facturas["saldo"] > 0
                ]
                top_facturas = top_facturas.sort_values(
                    "saldo",
                    ascending=False
                )
                cols = [
                    c for c in [
                        "persona_entidad",
                        "comprobante",
                        "fecha",
                        "vencimiento",
                        "saldo"
                    ]
                    if c in top_facturas.columns
                ]
                if not top_facturas.empty:
                    st.dataframe(
                        top_facturas[cols].head(15),
                        use_container_width=True,
                        hide_index=True
                    )                
            if table in ["banco_galicia_vm", "banco_macro_vmr"]:
                render_banco_pro_panel(filtered, module_name)
                st.divider()
                st.markdown("### Movimientos bancarios")
                tabla_banco = module_business_df(
                    add_balance_columns(filtered),
                    cfg
                ).drop(
                    columns=["responsable", "observaciones"],
                    errors="ignore"
                )
                st.dataframe(
                    tabla_banco,
                    use_container_width=True,
                    hide_index=True,
                )
                                
            col_monto = None
            for c in ["valor_pesos", "importe", "monto", "saldo", "valor"]:
                if c in filtered.columns:
                    col_monto = c
                    break
            total_facturado = filtered[col_monto].apply(money).sum() if col_monto else 0 
            if "estado" in filtered.columns:
                total_cobrado = filtered[filtered["estado"].astype(str).str.lower().isin(["completo", "pagado", "cobrado"])]
                cobrado = total_cobrado[col_monto].apply(money).sum() if col_monto else 0
            else:
                total_cobrado = 0
                cobrado = 0
            pendiente = total_facturado - cobrado
            pacientes = len(filtered)
            ticket_promedio = total_facturado / pacientes if pacientes > 0 else 0
            if table == "Cuenta Corriente VMR":
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("💰 Facturado ARS", fmt_money(total_facturado))
                c2.metric("💵 Facturado USD", f"USD {total_usd:,.2f}")
                c3.metric("💸 Pagado ARS", fmt_money(cobrado))
                c4.metric("💵 Pagado USD", f"USD {pagado_usd:,.2f}")
                c5.metric("⏳ A pagar ARS", fmt_money(pendiente))
                c6.metric("💵 A pagar USD", f"USD {pendiente_usd:,.2f}")
            if table == "cuenta_corriente_vm":
                c1, c2, c3 = st.columns(3)
                c1.metric("💰 Total Facturas", fmt_money(total_facturado))
                c2.metric("💸 Total Pagado", fmt_money(cobrado))
                c3.metric("⏳ Deuda Total", fmt_money(pendiente))
                st.divider()
                st.markdown("### 🏥 Estado de proveedores")
                proveedores_vm = [
                    "DROGUERIA CAPDEVILLA",
                    "OXITESA",
                    "SALUZZI",
                    "DROGUERIA SALTA SALUD",
                    "DROGUERIA PLAZA OÑA",
                    "PHARMA LIGHT",
                    "FARMACORP",
                    "DISTRIMED",
                    "SALUS",
                    "DROGUERIA LARPOS",
                    "MEDICFARMA"
                ]
                resumen = []
                for proveedor in proveedores_vm:
                    df_prov = filtered[
                        filtered["persona_entidad"]
                        .astype(str)
                        .str.upper()
                        .str.strip()
                        == proveedor
                    ]
                    deuda = (
                        pd.to_numeric(df_prov["importe"], errors="coerce").fillna(0).sum()
                        -
                        pd.to_numeric(df_prov["pagado"], errors="coerce").fillna(0).sum()
                    )
                    if not df_prov.empty:
                        prox_vto = (
                            pd.to_datetime(
                                df_prov["vencimiento"],
                                dayfirst=True,
                                errors="coerce"
                            ).min()
                        )
                    else:
                        prox_vto = pd.NaT
                    resumen.append({
                        "Proveedor": proveedor,
                        "Deuda": deuda,
                        "Próximo vencimiento": prox_vto
                    })
                resumen_df = pd.DataFrame(resumen)
                resumen_df = resumen_df.sort_values(
                    by=["Próximo vencimiento", "Deuda"],
                    ascending=[True, False]
                )
                st.dataframe(
                    resumen_df,
                    use_container_width=True,
                    hide_index=True
                ) 
            if table != "Cuenta Corriente VM":
                total_usd = filtered["importe_usd"].apply(money_usd).sum() if "importe_usd" in filtered.columns else 0
                pagado_usd = filtered["pagado_usd"].apply(money_usd).sum() if "pagado_usd" in filtered.columns else 0
                pendiente_usd = total_usd - pagado_usd
            
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("💰 Facturado", fmt_money(total_facturado))
                c2.metric("✅ Cobrado", fmt_money(cobrado))
                c3.metric("⏳ Pendiente", fmt_money(pendiente))
                c4.metric("👥 Pacientes", pacientes)
        st.divider()
        if table == "cuenta_corriente_vm":
            filtered = df.drop(columns=["importe_usd", "pagado_usd"], errors="ignore")
        if "mes" in filtered.columns:
            filtered = filtered.sort_values(
                by="mes",
                ascending=False,
                na_position="last"
            )
        col_orden = "mes" if "mes" in filtered.columns else "Mes" if "Mes" in filtered.columns else None
        if col_orden:
            filtered[col_orden] = pd.to_datetime(
                filtered[col_orden],
                errors="coerce",
                dayfirst=True
            )
            filtered = filtered.sort_values(
                by=col_orden,
                ascending=False,
                na_position="last"
            )
        if table == "cuenta_corriente_vm":
            df = df.drop(columns=["importe_usd", "pagado_usd"], errors="ignore")
        elif table == "cuenta_corriente_vmr":
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("🛒 Compras ARS", fmt_money(total_facturado))
            c2.metric("🛒 Compras USD", f"USD {total_usd:,.2f}")
            c3.metric("💵 Pagado ARS", fmt_money(cobrado))
            c4.metric("💵 Pagado USD", f"USD {pagado_usd:,.2f}")
            c5.metric("📌 A Pagar ARS", fmt_money(pendiente))
            c6.metric("📌 A Pagar USD", f"USD {pendiente_usd:,.2f}")
            st.divider()
            st.markdown("### 🏥 Estado de proveedores VMR")
            proveedores_vmr = [
                "DIVILAB",
                "EUROFARMA",
                "FERRING",
                "MEDICAL ENGINEERING",
                "MERCK",
                "VITAGEN",
                "CAMPO NITRO",
                "DANIEL CAMACHO",
            ]
            rows = []
            for proveedor in proveedores_vmr:
                df_prov = filtered[
                    filtered["persona_entidad"]
                    .astype(str)
                    .str.upper()
                    .str.strip()
                    .str.contains(proveedor, na=False)
                ]
                importe_ars = pd.to_numeric(df_prov["importe"], errors="coerce").fillna(0).sum()
                pagado_ars = pd.to_numeric(df_prov["pagado"], errors="coerce").fillna(0).sum()
                deuda_ars = importe_ars - pagado_ars
                importe_usd = pd.to_numeric(df_prov["importe_usd"], errors="coerce").fillna(0).sum() if "importe_usd" in df_prov.columns else 0
                pagado_usd_prov = pd.to_numeric(df_prov["pagado_usd"], errors="coerce").fillna(0).sum() if "pagado_usd" in df_prov.columns else 0
                deuda_usd = importe_usd - pagado_usd_prov
                if not df_prov.empty and "vencimiento" in df_prov.columns:
                    prox_vto = pd.to_datetime(
                        df_prov["vencimiento"],
                        dayfirst=True,
                        errors="coerce"
                    ).min()
                else:
                    prox_vto = pd.NaT
                rows.append({
                    "Proveedor": proveedor,
                    "Importe ARS": importe_ars,
                    "Pagado ARS": pagado_ars,
                    "Deuda ARS": deuda_ars,
                    "Importe USD": importe_usd,
                    "Pagado USD": pagado_usd_prov,
                    "Deuda USD": deuda_usd,
                    "Próximo vencimiento": prox_vto,
                    "Facturas": len(df_prov),
                })
            resumen_vmr = pd.DataFrame(rows)
            resumen_vmr = resumen_vmr.sort_values(
                by=["Deuda ARS", "Deuda USD", "Próximo vencimiento"],
                ascending=[False, False, True]
            )
            st.dataframe(
                resumen_vmr,
                use_container_width=True,
                hide_index=True
            )
            st.divider()
            st.markdown("## 📊 Dashboard Financiero Proveedores VMR")
            graf_ars = resumen_vmr[resumen_vmr["Deuda ARS"] > 0].copy()
            if not graf_ars.empty:
                fig1 = px.bar(
                    graf_ars,
                    x="Deuda ARS",
                    y="Proveedor",
                    orientation="h",
                    text="Deuda ARS",
                    title="💰 Ranking deuda ARS por proveedor",
                )
                fig1.update_layout(
                    height=500,
                    yaxis=dict(categoryorder="total ascending")
                )
                st.plotly_chart(fig1, use_container_width=True)
            graf_usd = resumen_vmr[resumen_vmr["Deuda USD"] > 0].copy()
            if not graf_usd.empty:
                fig2 = px.bar(
                    graf_usd,
                    x="Deuda USD",
                    y="Proveedor",
                    orientation="h",
                    text="Deuda USD",
                    title="💵 Ranking deuda USD por proveedor",
                )
                fig2.update_layout(
                    height=500,
                    yaxis=dict(categoryorder="total ascending")
                )
                st.plotly_chart(fig2, use_container_width=True)
            venc_df = filtered.copy()
            if "vencimiento" in venc_df.columns:
                venc_df["vencimiento"] = pd.to_datetime(
                    venc_df["vencimiento"],
                    dayfirst=True,
                    errors="coerce"
                )
                venc_df["saldo_ars"] = (
                    pd.to_numeric(venc_df["importe"], errors="coerce").fillna(0)
                    -
                    pd.to_numeric(venc_df["pagado"], errors="coerce").fillna(0)
                )
                venc_df["saldo_usd"] = (
                    pd.to_numeric(venc_df["importe_usd"], errors="coerce").fillna(0)
                    -
                    pd.to_numeric(venc_df["pagado_usd"], errors="coerce").fillna(0)
                ) if "importe_usd" in venc_df.columns and "pagado_usd" in venc_df.columns else 0
                venc_resumen = (
                    venc_df.groupby("vencimiento")[["saldo_ars", "saldo_usd"]]
                    .sum()
                    .reset_index()
                    .sort_values("vencimiento")
                )
                venc_resumen = venc_resumen[
                    (venc_resumen["saldo_ars"] > 0) |
                    (venc_resumen["saldo_usd"] > 0)
                ]
                if not venc_resumen.empty:
                    fig3 = px.bar(
                        venc_resumen,
                        x="vencimiento",
                        y=["saldo_ars", "saldo_usd"],
                        title="📅 Vencimientos próximos ARS / USD",
                        barmode="group"
                    )
                    fig3.update_layout(height=430)
                    st.plotly_chart(fig3, use_container_width=True)
            pie_ars = pd.DataFrame({
                "Estado": ["Pagado ARS", "Pendiente ARS"],
                "Monto": [cobrado, pendiente],
            })
            fig4 = px.pie(
                pie_ars,
                names="Estado",
                values="Monto",
                hole=0.55,
                title="💳 ARS Pagado vs Pendiente",
            )
            st.plotly_chart(fig4, use_container_width=True)
            pie_usd = pd.DataFrame({
                "Estado": ["Pagado USD", "Pendiente USD"],
                "Monto": [pagado_usd, pendiente_usd],
            })
            fig5 = px.pie(
                pie_usd,
                names="Estado",
                values="Monto",
                hole=0.55,
                title="💵 USD Pagado vs Pendiente",
            )
            st.plotly_chart(fig5, use_container_width=True)
    st.divider()
    st.markdown("#### Tabla limpia")
    try:
        tabla_limpia = read_table_from_sheet(table)
    except Exception as e:
        tabla_limpia = pd.DataFrame()
        st.warning(f"No se pudo leer la tabla limpia desde Google Sheets: {e}")
    if tabla_limpia is None or tabla_limpia.empty:
        st.warning("No hay datos en Google Sheets para este módulo.")
    else:
        tabla_limpia = tabla_limpia.drop(
            columns=["id", "created_at", "updated_at"],
            errors="ignore"
        )
        st.dataframe(
            tabla_limpia,
            use_container_width=True,
            hide_index=True,
        )
    st.markdown("### Gráficos útiles")
    g1, g2 = st.columns(2)
    if "valor_pesos" in filtered.columns:
        graph = filtered.copy()
        fecha_grafico = None
        if "fecha_factura" in graph.columns:
            tmp = pd.to_datetime(graph["fecha_factura"], errors="coerce")
            if tmp.notna().sum() > 0:
                fecha_grafico = "fecha_factura"
        if fecha_grafico is None and "mes" in graph.columns:
            tmp = pd.to_datetime(graph["mes"], errors="coerce", dayfirst=True)
            if tmp.notna().sum() > 0:
                fecha_grafico = "mes"
        if fecha_grafico:
            graph[fecha_grafico] = pd.to_datetime(
                graph[fecha_grafico],
                errors="coerce",
                dayfirst=True
            )
            graph = graph[graph[fecha_grafico].notna()]
            if not graph.empty:
                graph["Mes"] = graph[fecha_grafico].dt.to_period("M").astype(str)
                chart = (
                    graph.groupby("Mes")["valor_pesos"]
                    .apply(lambda x: x.apply(money).sum())
                    .reset_index()
                )
                fig = px.bar(
                    chart,
                    x="Mes",
                    y="valor_pesos",
                    title="Facturación por mes"
                )
                g1.plotly_chart(fig, use_container_width=True)
    if "obra_social" in filtered.columns and "valor_pesos" in filtered.columns:
        chart = filtered.groupby("obra_social")["valor_pesos"].apply(lambda x: x.apply(money).sum()).reset_index()
        chart = chart.sort_values("valor_pesos", ascending=False).head(10)
        fig = px.bar(chart, x="obra_social", y="valor_pesos", title="Facturación por obra social")
        g2.plotly_chart(fig, use_container_width=True)
    g3, g4 = st.columns(2)
    if "medico_responsable" in filtered.columns and "valor_pesos" in filtered.columns:
        chart = filtered.groupby("medico_responsable")["valor_pesos"].apply(lambda x: x.apply(money).sum()).reset_index()
        chart = chart.sort_values("valor_pesos", ascending=False).head(10)
        fig = px.bar(chart, x="medico_responsable", y="valor_pesos", title="Facturación por médico")
        g3.plotly_chart(fig, use_container_width=True)
    if "procedimiento" in filtered.columns and "valor_pesos" in filtered.columns:

        chart = filtered.groupby("procedimiento")["valor_pesos"].apply(lambda x: x.apply(money).sum()).reset_index()

        chart = chart.sort_values("valor_pesos", ascending=False).head(10)

        fig = px.bar(chart, x="procedimiento", y="valor_pesos", title="Facturación por procedimiento")

        g4.plotly_chart(fig, use_container_width=True)    
    with tab_cargar:
        st.subheader("Nuevo registro")
        with st.form(f"form_add_{table}", clear_on_submit=False):
            data: Dict[str, Any] = {}
            cols = st.columns(2)
            for i, field in enumerate(cfg["fields"]):
                with cols[i % 2]:
                    raw = input_field(field, f"add_{table}")
                    data[field[0]] = clean_for_db(raw, field[1])
            submitted = st.form_submit_button("Guardar registro", type="primary")
            if submitted:
                errors = validate_required(cfg, data)            
                if errors:            
                    st.error("Faltan completar campos obligatorios: " + ", ".join(errors))            
                    st.write("DEBUG DATA:", data)            
                else:            
                    try:            
                        df_actual = get_df(table)      
                        duplicado = False     
                        if not df_actual.empty:
                            cols_check = [c for c in data.keys() if c in df_actual.columns]    
                            duplicado = (      
                                df_actual[cols_check].fillna("").astype(str)    
                                == pd.Series(data)[cols_check].fillna("").astype(str)      
                            ).all(axis=1).any()         
                        if duplicado:      
                            st.warning("Este registro ya existe. No se volvió a cargar.")        
                        else:       
                            insert_row(table, data)          
                            st.success("Registro guardado correctamente.")         
                        st.write("DEBUG GUARDADO EN TABLA:", table)            
                        st.write(data)            
                    except Exception as e:
                        st.error("Error al guardar el registro")
                        st.exception(e)
    with tab_importar:
        render_importer(module_name, cfg)    
    with tab_editar:
        st.subheader("Editar registros cargados")
        df = add_balance_columns(get_df(table))
        if df.empty:
            st.warning("No hay registros para editar.")
        else:
            df_edit = df.copy()
            if table == "cuenta_corriente_vm":
                df_edit = df_edit.drop(columns=["importe_usd", "pagado_usd"], errors="ignore")
            columnas_ocultas = ["created_at", "updated_at"]
            df_edit = df_edit.drop(columns=columnas_ocultas, errors="ignore")
            for col in ["importe_usd", "pagado_usd"]:
                if col in df_edit.columns:
                    df_edit[col] = pd.to_numeric(df_edit[col], errors="coerce")
            # Ordenar desde la fecha actual hacia atrás
            if "mes" in df_edit.columns:
                df_edit["mes"] = pd.to_datetime(df_edit["mes"], errors="coerce").dt.strftime("%Y-%m-%d")
            if "mes" in df_edit.columns:
                df_edit["mes"] = pd.to_datetime(
                    df_edit["mes"],
                    errors="coerce"
                )
                df_edit = df_edit.sort_values(
                    by="mes",
                    ascending=False
                )
                df_edit["mes"] = df_edit["mes"].dt.strftime("%Y-%m-%d")
            estado_editor = "Todos"
            if "estado" in df_edit.columns:
                estados = sorted(
                    df_edit["estado"].dropna().astype(str).unique().tolist()
                )
                estado_editor = st.selectbox(
                    "Filtrar por estado",
                    ["Todos"] + estados,
                    key=f"estado_editor_{table}"
                )
                if estado_editor != "Todos":
                    df_edit = df_edit[
                        df_edit["estado"].astype(str) == estado_editor
                    ]
            edited_df = st.data_editor(
                df_edit,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                },
                disabled=["id"],
                key=f"editor_{table}",
            )
            col1, col2 = st.columns(2)
            with col1:
                guardar = st.button("Guardar cambios", type="primary", key=f"guardar_editor_{table}")
            with col2:
               st.info("Edición segura: podés modificar celdas. No se borran filas aunque las elimines del editor.")
            if guardar:
                try:
                    limpio = edited_df.copy()
                    columnas_no_db = ["saldo", "saldo_usd", "saldo_movimiento"]
                    limpio = limpio.drop(columns=columnas_no_db, errors="ignore")
                    limpio = limpio.drop_duplicates()
                    total_guardado = sync_df_to_sheet(table, limpio)
                    st.success(
                        f"Cambios guardados correctamente. Registros procesados: {total_guardado}"
                    )
                    
                except Exception as e:
                    st.error("ERROR AL GUARDAR")
                    st.exception(e)
    with tab_exportar:
        df = add_balance_columns(get_df(table))
        if table == "cuenta_corriente_vm":
            df = df.drop(columns=["importe_usd", "pagado_usd"], errors="ignore")
        if df.empty:
            st.info("No hay datos para exportar.")
        else:
            export_df = format_facturacion_table(df, labels)
            csv = export_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Descargar CSV", data=csv, file_name=f"{table}.csv", mime="text/csv")
            xlsx_path = Path(f"{table}.xlsx")
            export_df.to_excel(xlsx_path, index=False)
            with open(xlsx_path, "rb") as f:
                st.download_button(
                    "Descargar Excel",
                    data=f,
                    file_name=f"{table}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
def render_analisis_global_vitae():
    ANIO_ANALISIS = 2026
    st.divider()
    st.markdown(f"## 📊 Análisis Global VITAE {ANIO_ANALISIS}")
    rows = []
    for module_name, cfg in MODULES.items():
        df = get_df(cfg["table"])
        if df.empty:
            continue
        empresa = cfg.get("empresa", "VITAE")
        for _, row in df.iterrows():
            fecha = (
                row.get("fecha")
                or row.get("vencimiento")
                or row.get("created_at")
            )
            fecha = pd.to_datetime(fecha, errors="coerce")
            if pd.isna(fecha):
                continue
            if fecha.year != ANIO_ANALISIS:
                continue
            ingreso = money(row.get("ingreso", 0))
            egreso = money(row.get("egreso", 0))
            valor = (
                money(row.get("valor_pesos", 0))
                or money(row.get("importe", 0))
                or money(row.get("monto", 0))
                or money(row.get("valor", 0))
            )
            estado = str(row.get("estado", "")).lower()
            facturado = valor if valor else ingreso
            cobrado = (
                valor
                if estado in [
                    "cobrado",
                    "pagado",
                    "realizado",
                    "completo",
                    "finalizado"
                ]
                else ingreso
            )
            pendiente = (
                valor
                if estado in [
                    "pendiente",
                    "a cobrar",
                    "adeudado",
                    "deuda"
                ]
                else 0
            )
            rows.append({
                "Fecha": fecha,
                "Mes": fecha.strftime("%Y-%m"),
                "Empresa": empresa,
                "Módulo": module_name,
                "Facturado": facturado,
                "Cobrado": cobrado,
                "Pendiente": pendiente,
                "Egreso": egreso,
                "Resultado": cobrado - egreso,
            })
    if not rows:
        st.info("No hay datos de 2026 para analizar.")
        return
    global_df = pd.DataFrame(rows)
    facturado_total = global_df["Facturado"].sum()
    cobrado_total = global_df["Cobrado"].sum()
    pendiente_total = global_df["Pendiente"].sum()
    egreso_total = global_df["Egreso"].sum()
    resultado_total = global_df["Resultado"].sum()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "💰 Facturado",
        fmt_money(facturado_total)
    )
    c2.metric(
        "✅ Cobrado",
        fmt_money(cobrado_total)
    )
    c3.metric(
        "⏳ Pendiente",
        fmt_money(pendiente_total)
    )
    c4.metric(
        "📤 Egresos",
        fmt_money(egreso_total)
    )
    c5.metric(
        "📈 Resultado",
        fmt_money(resultado_total)
    )
    mensual = global_df.groupby(
        "Mes",
        as_index=False
    )[
        [
            "Facturado",
            "Cobrado",
            "Pendiente",
            "Egreso",
            "Resultado"
        ]
    ].sum()
    st.markdown("### 📅 Resumen mensual 2026")
    fig = px.bar(
        mensual,
        x="Mes",
        y=[
            "Facturado",
            "Cobrado",
            "Pendiente",
            "Egreso"
        ],
        barmode="group",
        title="Movimientos mensuales"
    )
    fig.update_layout(height=450)
    st.plotly_chart(
        fig,
        use_container_width=True,
        key="global_mensual_2026"
    )
    mensual["Acumulado"] = mensual["Resultado"].cumsum()
    st.markdown("### 📈 Evolución acumulada")
    fig2 = px.line(
        mensual,
        x="Mes",
        y="Acumulado",
        markers=True,
        title="Resultado acumulado 2026"
    )
    fig2.update_layout(height=400)
    st.plotly_chart(
        fig2,
        use_container_width=True,
        key="global_acumulado_2026"
    )
    resumen_modulos = global_df.groupby(
        ["Módulo", "Empresa"],
        as_index=False
    )[
        [
            "Facturado",
            "Cobrado",
            "Pendiente",
            "Egreso",
            "Resultado"
        ]
    ].sum()
    st.markdown("### 📋 Resumen por módulo")
    
    st.dataframe(
        resumen_modulos.sort_values(
            "Facturado",
            ascending=False
        ),
        use_container_width=True,
        hide_index=True
    )
def render_dashboard() -> None:
    render_header()
    st.markdown("### Resumen General")
    dfs = {name: add_balance_columns(get_df(cfg["table"])) for name, cfg in MODULES.items()}
    def total_mod(nombre):
        df = dfs.get(nombre, pd.DataFrame())
        if df.empty:
            return 0.0
        if "saldo" in df.columns:
            return df["saldo"].apply(money).sum()
        if "saldo_movimiento" in df.columns:
            return df["saldo_movimiento"].apply(money).sum()
        if "importe" in df.columns:
            return df["importe"].apply(money).sum()
        if "valor_pesos" in df.columns:
            return df["valor_pesos"].apply(money).sum()
        if "monto" in df.columns:
            return df["monto"].apply(money).sum()
        return 0.0
    def deuda_mod(nombre):
        df = dfs.get(nombre, pd.DataFrame())
        if df.empty:
            return 0.0
        col_monto = None
        for c in ["valor_pesos", "importe", "monto", "saldo", "valor"]:
            if c in df.columns:
                col_monto = c
                break
        if not col_monto:
            return 0.0
        if "estado" not in df.columns:
            return df[col_monto].apply(money).sum()
        estados_deuda = ["pendiente", "a pagar", "adeudado", "deuda"]
        deuda = df[
            df["estado"].astype(str).str.lower().isin(estados_deuda)
        ]
        return deuda[col_monto].apply(money).sum()
    caja_vmr = total_mod("Caja VMR")
    banco_vmr = total_mod("Banco Macro VMR")
    caja_vm = total_mod("Caja VM")
    banco_vm = total_mod("Banco Galicia VM")
    gine_vitae = total_mod("Gine Vitae")
    pagos_pendientes = total_mod("Pagos pendientes Vitae")
    planes_pago = total_mod("Planes de pagos y préstamos")
    honorarios = total_mod("Honorarios médicos")
    deuda_imp_vmr = total_mod("Deudas Impositivas VMR")
    deuda_imp_vm = total_mod("Deudas Impositivas VM")
    liquidez_total = caja_vmr + banco_vmr + caja_vm + banco_vm + gine_vitae
    deuda_total_global = pagos_pendientes + planes_pago + honorarios + deuda_imp_vmr + deuda_imp_vm
    caja_bancos = 0.0
    ingresos_mes = 0.0
    egresos_mes = 0.0
    facturacion_mes = 0.0
    cobrado_mes = 0.0
    a_cobrar = 0.0
    a_pagar = 0.0
    deuda_total = 0.0
    vencidos = 0
    tareas_pend = 0
    pacientes_mes = 0
    medicos_activos = set()
    hoy = pd.Timestamp.today().normalize()
    inicio_mes = hoy.replace(day=1)
    fin_mes = inicio_mes + pd.offsets.MonthEnd(0)
    estados_cerrados = ["pagado", "cobrado", "completo", "realizado", "finalizada", "finalizado", "anulado", "cancelado"]
    for name, df in dfs.items():
        if df.empty:
            continue
        if "fecha" in df.columns:
            fechas = pd.to_datetime(df["fecha"], errors="coerce")
        elif "fecha_factura" in df.columns:
            fechas = pd.to_datetime(df["fecha_factura"], errors="coerce")
        else:
            fechas = pd.Series([pd.NaT] * len(df), index=df.index)
        es_mes = fechas.notna() & (fechas >= inicio_mes) & (fechas <= fin_mes)
        if name in ["Caja VMR", "Caja VM", "Banco Macro VMR", "Banco Galicia VM"]:
            ingresos = df["ingreso"].apply(money).sum() if "ingreso" in df.columns else 0
            egresos = df["egreso"].apply(money).sum() if "egreso" in df.columns else 0
            caja_bancos += ingresos - egresos
            if "ingreso" in df.columns:
                ingresos_mes += df.loc[es_mes, "ingreso"].apply(money).sum()
            if "egreso" in df.columns:
                egresos_mes += df.loc[es_mes, "egreso"].apply(money).sum()
        if name in ["facturacion_vmr", "facturacion_vm"]:
            if "valor_pesos" in df.columns:
                total_facturado = df["valor_pesos"].apply(money).sum()
                facturacion_mes += df.loc[es_mes, "valor_pesos"].apply(money).sum()
                estado = df["estado"].astype(str).str.lower().str.strip() if "estado" in df.columns else pd.Series([""] * len(df), index=df.index)
                cobrado = df[estado.isin(["completo", "cobrado", "pagado"])]["valor_pesos"].apply(money).sum()
                cobrado_mes += df.loc[es_mes & estado.isin(["completo", "cobrado", "pagado"]), "valor_pesos"].apply(money).sum()
                a_cobrar += max(0, total_facturado - cobrado)
                pacientes_mes += int(es_mes.sum())
                if "medico_responsable" in df.columns:
                    medicos_activos.update(
                        df.loc[es_mes, "medico_responsable"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .replace("", pd.NA)
                        .dropna()
                        .tolist()
                    )
        if name in ["Cuenta Corriente VMR", "Cuenta Corriente VM"]:
            if "tipo" in df.columns and "importe" in df.columns:
                tipo = df["tipo"].astype(str).str.lower()
                pagado = df["pagado"].apply(money) if "pagado" in df.columns else 0
                saldo = df["importe"].apply(money) - pagado
                a_cobrar += saldo[tipo.eq("a cobrar")].sum()
                a_pagar += saldo[tipo.eq("a pagar")].sum()
        if name in ["Deudas Impositivas VMR", "Deudas Impositivas VM", "Planes de pagos y préstamos", "Pagos pendientes Vitae", "Deuda total", "Honorarios médicos"]:
            if "saldo" in df.columns:
                deuda_total += df["saldo"].apply(money).sum()
            elif "importe" in df.columns:
                pagado = df["pagado"].apply(money) if "pagado" in df.columns else 0
                deuda_total += max(0, df["importe"].apply(money).sum() - pagado.sum())
        if "vencimiento" in df.columns:
            venc = pd.to_datetime(df["vencimiento"], errors="coerce")
            estado = df["estado"].astype(str).str.lower().str.strip() if "estado" in df.columns else pd.Series([""] * len(df), index=df.index)
            vencidos += int((venc.notna() & (venc < hoy) & (~estado.isin(estados_cerrados))).sum())
        if name == "Tareas Pendientes" and "estado" in df.columns:
            tareas_pend += int(df[~df["estado"].isin(["Finalizada", "Cancelada"])].shape[0])
    resultado_mes = ingresos_mes + cobrado_mes - egresos_mes
    pendiente_cobro = a_cobrar
    promedio_facturacion = facturacion_mes / pacientes_mes if pacientes_mes > 0 else 0
    cuenta_corriente_vmr = deuda_mod("Cuenta Corriente VMR")
    cuenta_corriente_vm = deuda_mod("Cuenta Corriente VM")
    def deuda_usd_mod(nombre):
        df = dfs.get(nombre, pd.DataFrame())
        if df.empty:
            return 0.0
        if "importe_usd" in df.columns:
            total_usd = df["importe_usd"].apply(money_usd).sum()
            pagado_usd = df["pagado_usd"].apply(money_usd).sum() if "pagado_usd" in df.columns else 0
            return max(0, total_usd - pagado_usd)
        if "saldo_usd" in df.columns:
            return df["saldo_usd"].apply(money_usd).sum()
        return 0.0
    cuenta_corriente_vmr_usd = deuda_usd_mod("Cuenta Corriente VMR")
    cuenta_corriente_vm_usd = deuda_usd_mod("Cuenta Corriente VM")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Liquidez actual", fmt_money(caja_bancos))
    c2.metric("Facturación mes", fmt_money(facturacion_mes))
    c3.metric("Cobrado mes", fmt_money(cobrado_mes))
    c4.metric("A cobrar", fmt_money(pendiente_cobro))
    c5.metric("Resultado mes", fmt_money(resultado_mes))
    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("A pagar", fmt_money(a_pagar))
    c7.metric("Deuda total", fmt_money(deuda_total))
    c8.metric("Vencidos / críticos", vencidos)
    c9.metric("Tareas pendientes", tareas_pend)
    c10.metric("Promedio por paciente", fmt_money(promedio_facturacion))
    c11, c12 = st.columns(2)
    c11.metric(
        "💸 Deuda Proveedores VMR",
        f"{fmt_money(cuenta_corriente_vmr)} | USD {cuenta_corriente_vmr_usd:,.2f}"
    )
    c12.metric(
        "💸 Deuda Proveedores VM",
        f"{fmt_money(cuenta_corriente_vm)} | USD {cuenta_corriente_vm_usd:,.2f}"
    )
    st.divider()
    render_resumen_empresa("Resumen VMR", "VMR")
    render_resumen_empresa("Resumen VM", "VM")
    render_analisis_global_vitae()
    rows_global = []
    for name, cfg in MODULES.items():
        df_g = get_df(cfg["table"])
        if df_g.empty:
            continue
        if "valor_pesos" in df_g.columns:
            total_g = df_g["valor_pesos"].apply(money).sum()
        elif "importe" in df_g.columns:
            total_g = df_g["importe"].apply(money).sum()
        else:
            total_g = 0
        if total_g > 0:
            rows_global.append({
                "Módulo": name,
                "Empresa": cfg["empresa"],
                "Total": total_g,
            })
    resumen_global = pd.DataFrame(rows_global)
    if not resumen_global.empty:
        fig = px.bar(
            resumen_global,
            x="Módulo",
            y="Total",
            color="Empresa",
            title="Importes registrados por módulo"
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True, key="grafico_modulos_unico")
def render_resumen_empresa(titulo, empresa):
        mods = {
            name: get_df(cfg["table"])
            for name, cfg in MODULES.items()
            if cfg.get("empresa") == empresa
        }
        liquidez = 0
        facturacion = 0
        cobrado = 0
        a_cobrar = 0
        a_pagar_emp = 0
        deuda_emp = 0
        vencidos_emp = 0
        tareas_emp = 0
        pacientes = 0
        for name, df in mods.items():
            if df.empty:
                continue
            df = df.copy()
            for col in ["valor_pesos", "importe", "monto", "pagado", "saldo"]:
                if col in df.columns:
                    df[col] = df[col].apply(money)
            tipo = MODULES[name].get("tipo", "")
            if tipo in ["caja", "banco"]:
                liquidez += total_mod(name)
            if "valor_pesos" in df.columns:
                facturacion += df["valor_pesos"].apply(money).sum()
                pacientes += len(df)
                if "estado" in df.columns:
                    cobrado += df[df["estado"].astype(str).str.lower().isin(["completo", "cobrado", "pagado"])]["valor_pesos"].apply(money).sum()
                    a_cobrar += df[df["estado"].astype(str).str.lower().isin(["pendiente", "parcial", "vencido"])]["valor_pesos"].apply(money).sum()
            if "monto" in df.columns and "estado" in df.columns:

                a_pagar_emp += df[df["estado"].astype(str).str.lower().isin(["pendiente", "vencido"])]["monto"].apply(money).sum()

            if "vencimiento" in df.columns:

                vencidos_emp += len(df)

            if name == "Tareas Pendientes" and "estado" in df.columns:

                tareas_emp += len(df[~df["estado"].astype(str).str.lower().isin(["finalizada", "cancelada"])])
        resultado = cobrado - a_pagar_emp
        promedio = facturacion / pacientes if pacientes > 0 else 0
        st.divider()
        st.markdown(f"### {titulo}")
        r1, r2, r3, r4, r5 = st.columns(5)
        r1.metric("Liquidez actual", fmt_money(liquidez))
        r2.metric("Facturación mes", fmt_money(facturacion))
        r3.metric("Cobrado mes", fmt_money(cobrado))
        r4.metric("A cobrar", fmt_money(a_cobrar))
        r5.metric("Resultado mes", fmt_money(resultado))
        r6, r7, r8, r9, r10 = st.columns(5)
        r6.metric("A pagar", fmt_money(a_pagar_emp))
        r7.metric("Deuda total", fmt_money(deuda_emp))
        r8.metric("Vencidos / críticos", vencidos_emp)
        r9.metric("Tareas pendientes", tareas_emp)
        r10.metric("Promedio por paciente", fmt_money(promedio))
        rows = []
        for name, cfg in MODULES.items():
            df = get_df(cfg["table"])
            if df.empty:
                continue
            if "valor_pesos" in df.columns:
                total = df["valor_pesos"].apply(money).sum()
            elif "importe" in df.columns:
                total = df["importe"].apply(money).sum()
            else:
                total = 0
            if total > 0:
                rows.append({
                "Módulo": name,
                "Empresa": MODULES[name]["empresa"],
                "Total": total,
                "Registros": len(df),
            })
        resumen = pd.DataFrame(rows)           
        st.divider()                                
def render_configuracion() -> None:
    render_header()
    st.header("Configuración")
    tab1, tab2, tab3, tab4 = st.tabs([
        "👤 Usuarios",
        "🔐 Permisos",
        "🏢 Empresas",
        "⚙️ Sistema"
    ])
    with tab1:
        st.subheader("Usuarios")
        st.info("Acá irá la gestión de usuarios.")
    with tab2:
        st.subheader("Permisos")
        st.info("Acá irá la gestión de permisos.")
    with tab3:
        st.subheader("Empresas")
        st.info("Acá irá la gestión de empresas.")
    with tab4:
        st.subheader("Sistema")
        st.info("Acá irá la configuración general del sistema.")
        if st.button("🧹 Limpiar USD mal cargados en cuenta corriente"):
            with connect() as conn:
                for table in ["cuenta_corriente_vmr", "cuenta_corriente_vm"]:
                    conn.execute(f"""
                        UPDATE {table}
                        SET importe_usd = 0
                        WHERE CAST(importe_usd AS REAL) > 10000
                    """)
                    conn.execute(f"""
                        UPDATE {table}
                        SET pagado_usd = 0
                        WHERE CAST(pagado_usd AS REAL) > 10000
                    """)
                conn.commit()
            st.success("USD mal cargados limpiados.")
            st.markdown("### 🗑️ Borrar base de un módulo")
        modulo_borrar = st.selectbox(
            "Módulo a borrar",
            list(MODULES.keys()),
            key="modulo_borrar_db"
        )
        confirmar = st.checkbox(
            f"Confirmo borrar todos los datos de {modulo_borrar}",
            key="confirmar_borrar_db"
        )
        st.markdown("### 🗑️ Borrar base de un módulo")
        modulo_borrar = st.selectbox(
            "Módulo a borrar",
            list(MODULES.keys()),
            key="modulo_borrar_db_2"
        )
        confirmar = st.checkbox(
            f"Confirmo borrar todos los datos de {modulo_borrar}",
            key="confirmar_borrar_db_2"
        )
        if st.button("Borrar base del módulo", type="primary"):
            if confirmar:
                tabla = MODULES[modulo_borrar]["table"]
                # 1) Borra SQLite
                with connect() as conn:
                    conn.execute(f"DELETE FROM {tabla}")
                    conn.commit()
                # 2) Borra Google Sheets
                sh = get_spreadsheet()
                try:
                    ws = sh.worksheet(tabla)
                    ws.clear()
                    ws.update([["Sin datos"]])
                except Exception as e:
                    st.warning(f"No se pudo borrar Google Sheets: {e}")
                st.success(f"Base borrada en SQLite y Google Sheets: {modulo_borrar}")
                st.rerun()
            else:
                st.warning("Marcá la confirmación antes de borrar.")
    st.markdown("### Sincronización Google Sheets")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬆️ Subir datos actuales a Google Sheets"):
            try:
                result = sync_all_to_sheets()
                st.success("Sincronización ejecutada.")
                st.write(result)
            except Exception as e:
                st.error("No se pudo subir a Google Sheets.")
                st.exception(e)
    with col2:
        if st.button("⬇️ Leer datos desde Google Sheets"):
            try:
                restore_all_from_sheets()
                st.success("Datos restaurados desde Google Sheets.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo leer desde Google Sheets: {e}")    
def seed_examples() -> None:
    examples = [
        ("caja_vmr", {"fecha": date.today().strftime(DATE_FMT), "concepto": "Ingreso muestra fertilidad", "categoria": "Ingreso", "medio": "Efectivo", "ingreso": 150000, "egreso": 0, "responsable": "Administración", "observaciones": "Ejemplo"}),
        ("banco_galicia_vm", {"fecha": date.today().strftime(DATE_FMT), "concepto": "Pago proveedor quirófano", "tipo_movimiento": "Débito", "referencia": "OP-001", "ingreso": 0, "egreso": 80000, "conciliado": 1, "observaciones": "Ejemplo"}),
        ("pagos_pendientes_vitae", {"fecha": date.today().strftime(DATE_FMT), "empresa": "VITAE", "proveedor": "Proveedor insumos", "concepto": "Insumos médicos", "importe": 120000, "pagado": 0, "vencimiento": (date.today() + timedelta(days=7)).strftime(DATE_FMT), "prioridad": "Alta", "estado": "Pendiente", "observaciones": "Ejemplo"}),
        ("tareas_pendientes", {"fecha": date.today().strftime(DATE_FMT), "empresa": "VM", "tarea": "Revisar stock quirófano", "responsable": "Enfermería", "prioridad": "Alta", "vencimiento": (date.today() + timedelta(days=3)).strftime(DATE_FMT), "estado": "Pendiente", "observaciones": "Ejemplo"}),
    ]
    for table, data in examples:
        insert_row(table, data)
# =========================================================
# APP
# =========================================================
def main() -> None:

    st.sidebar.title("VITAE")
    st.sidebar.caption("Sistema interno de gestión")
    page = st.sidebar.radio("Navegación", ["Dashboard Global", "Módulos", "Administración", "Configuración"])
    if page == "Dashboard Global":    
        render_dashboard()    
    elif page == "Módulos":    
        empresas = ["Todos", "VMR", "VM", "VITAE"]    
        empresa_filter = st.sidebar.selectbox("Empresa", empresas)   
        module_names = list(MODULES.keys())    
        if empresa_filter != "Todos":    
            module_names = [   
                m for m in module_names    
                if MODULES[m]["empresa"] == empresa_filter or MODULES[m]["empresa"] == "VITAE"    
            ]    
        module_name = st.sidebar.selectbox("Módulo", module_names)    
        render_facturacion_pro(module_name, MODULES[module_name])
    elif page == "Administración":    
        st.title("Administración")
        st.subheader("Panel Administrativo")
        
    elif page == "Configuración":    
        render_configuracion()
    st.sidebar.divider()
    st.sidebar.markdown("**Módulos incluidos**")
    st.sidebar.caption(f"{len(MODULES)} módulos activos")
if __name__ == "__main__":
    main()
