#!/usr/bin/env python3
"""
Orchestrator ISA - Sistema de Referidos
Tracking de referencias + descuentos automáticos
"""

import sqlite3
import uuid
from datetime import datetime

class SistemaReferidos:
    DESCUENTO_REFERIDO = 100

    @staticmethod
    def registrar_referido(referente_id, referido_nombre, referido_telefono, db_path="orchestrator_isa.db"):
        codigo = f"REF-{referente_id[:4]}-{str(uuid.uuid4())[:4].upper()}"
        now = datetime.now().isoformat()

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS referidos (
                id TEXT PRIMARY KEY,
                referente_id TEXT,
                referido_nombre TEXT,
                referido_telefono TEXT,
                codigo TEXT UNIQUE,
                estado TEXT DEFAULT 'pendiente',
                descuento_aplicado INTEGER DEFAULT 0,
                fecha_registro TEXT,
                fecha_cierre TEXT
            )
        ''')

        ref_id = str(uuid.uuid4())[:8]
        c.execute('''INSERT INTO referidos VALUES (?,?,?,?,?,?,?,?,?)''',
                  (ref_id, referente_id, referido_nombre, referido_telefono, 
                   codigo, 'pendiente', 0, now, None))
        conn.commit()
        conn.close()

        return {
            "referido_id": ref_id,
            "codigo": codigo,
            "estado": "pendiente",
            "mensaje": f"Referido registrado. Descuento de {SistemaReferidos.DESCUENTO_REFERIDO} MAD al cerrar."
        }

    @staticmethod
    def cerrar_referido(codigo, db_path="orchestrator_isa.db"):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM referidos WHERE codigo = ?", (codigo,))
        referido = c.fetchone()
        if not referido:
            conn.close()
            return {"error": "Codigo no encontrado"}
        c.execute("UPDATE referidos SET estado=?, descuento_aplicado=?, fecha_cierre=? WHERE codigo=?",
                  ('cerrado', SistemaReferidos.DESCUENTO_REFERIDO, now, codigo))
        conn.commit()
        conn.close()
        return {"codigo": codigo, "descuento": SistemaReferidos.DESCUENTO_REFERIDO, "estado": "cerrado"}

SPEECH_REFERIDOS = """Hola [Nombre], Espero que todo vaya bien. Vi que ya recibio mensajes gracias al sistema. 
¿Conoce otros dueños de negocio que pierdan clientes? Si me recomienda y cierra, le descuento 100 MAD."""

if __name__ == "__main__":
    print("Sistema de Referidos - Descuento:", SistemaReferidos.DESCUENTO_REFERIDO, "MAD")
