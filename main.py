from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor  # 👈 Para que nos regrese diccionarios limpios como hacía SQLite
import qrcode
import os
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔗 ¡PEGA AQUÍ TU URL DE NEON CON LA CONTRASEÑA REAL QUE REVELASTE EN EL OJITO!
DB_URL = "postgresql://neondb_owner:npg_Bwky2iTD0unQ@ep-tiny-cell-aqg3ulus.c-8.us-east-1.aws.neon.tech/neondb?sslmode=require"
ADMIN_PASSWORD = "admin123"

def init_db():
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS productos (
                    codigo TEXT PRIMARY KEY,
                    familia TEXT,
                    marca TEXT,
                    descripcion TEXT NOT NULL,
                    estatus TEXT,
                    existencia INTEGER DEFAULT 0,
                    unidad TEXT,
                    ubicacion TEXT,
                    ultimo_costo REAL DEFAULT 0.0,
                    moneda TEXT,
                    precio_mayoreo REAL DEFAULT 0.0,
                    precio_publico REAL DEFAULT 0.0,
                    ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

init_db()

# Modelos de datos (Se quedan exactamente igual)
# Reemplaza esta clase en tu main.py
class Producto(BaseModel):
    codigo: str
    familia: Optional[str] = ""
    marca: Optional[str] = ""
    descripcion: str
    estatus: Optional[str] = ""
    existencia: Optional[int] = 0          # 👈 Si se manda vacío, se guarda como 0
    unidad: Optional[str] = ""
    ubicacion: Optional[str] = ""
    ultimo_costo: Optional[float] = 0.0    # 👈 Si se manda vacío, se guarda como 0.0
    moneda: Optional[str] = ""
    precio_mayoreo: Optional[float] = 0.0  # 👈 Si se manda vacío, se guarda como 0.0
    precio_publico: Optional[float] = 0.0  # 👈 Si se manda vacío, se guarda como 0.0

class Movimiento(BaseModel):
    id: str
    cantidad: int
class UpdateProducto(BaseModel):
    password: str
    familia: Optional[str] = ""
    marca: Optional[str] = ""
    descripcion: str
    estatus: Optional[str] = ""
    existencia: Optional[int] = 0          # 👈 Protegido si se manda vacío
    unidad: Optional[str] = ""
    ubicacion: Optional[str] = ""
    ultimo_costo: Optional[float] = 0.0    # 👈 Protegido si se manda vacío
    moneda: Optional[str] = ""
    precio_mayoreo: Optional[float] = 0.0  # 👈 Protegido si se manda vacío
    precio_publico: Optional[float] = 0.0  # 👈 Protegido si se manda vacío

@app.post("/productos")  #  ¡Listo! Ahora sí coincide con tu frontend
def crear_producto(producto: Producto):
    try:
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as cursor:
                # Cambiamos los '?' por '%s' que es lo que entiende Postgres
                cursor.execute("""
                    INSERT INTO productos (codigo, familia, marca, descripcion, estatus, existencia, unidad, ubicacion, ultimo_costo, moneda, precio_mayoreo, precio_publico) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (producto.codigo, producto.familia, producto.marca, producto.descripcion, producto.estatus, 
                      producto.existencia, producto.unidad, producto.ubicacion, producto.ultimo_costo, producto.moneda, 
                      producto.precio_mayoreo, producto.precio_publico))
                conn.commit()
        
        os.makedirs("qrs", exist_ok=True)
        qr_img = qrcode.make(producto.codigo)
        qr_img.save(f"qrs/{producto.codigo}.png")
        
        return {"status": "Producto registrado y QR generado"}
    except psycopg2.IntegrityError:  # Captura el error de duplicados de Postgres
        raise HTTPException(status_code=400, detail="El Código del producto ya existe")

@app.post("/movimiento")
def registrar_movimiento(movimiento: Movimiento):
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT existencia, descripcion FROM productos WHERE codigo = %s", (movimiento.id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Producto no encontrado")
            
            stock_actual, descripcion = row
            nuevo_stock = stock_actual + movimiento.cantidad
            
            if nuevo_stock < 0:
                raise HTTPException(status_code=400, detail=f"Stock insuficiente para {descripcion}")
            
            # AGREGAMOS LA FECHA AQUÍ:
            cursor.execute("""
                UPDATE productos 
                SET existencia = %s, ultima_actualizacion = NOW() 
                WHERE codigo = %s
            """, (nuevo_stock, movimiento.id))
            conn.commit()
        
    tipo = "Entrada" if movimiento.cantidad > 0 else "Salida/Venta"
    return {"status": f"{tipo} registrada", "producto": descripcion, "nuevo_stock": nuevo_stock}

@app.get("/productos")
def listar_productos():
    with psycopg2.connect(DB_URL) as conn:
        # Usamos RealDictCursor para mapear automáticamente las columnas a formato JSON JSON
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM productos")
            return list(cursor.fetchall())

@app.put("/productos/{codigo}")
def editar_producto(codigo: str, datos: dict = {}): # 👈 Le agregamos "= {}" para volverlo inmune a bodies vacíos
    # 1. Validar contraseña de administrador
    if datos.get("admin123") != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
        
    # 2. Función interna para limpiar números (si viene "" o "-", lo convierte en 0 de forma segura)
    def limpiar_numero(valor, defecto=0.0):
        if valor is None or str(valor).strip() in ("", "-", "null", "undefined"):
            return defecto
        try:
            return float(valor)
        except:
            return defecto

    # 3. Extraer y limpiar cada campo de forma segura (si no viene, usa un valor por defecto)
    familia = str(datos.get("familia") or "").strip()
    marca = str(datos.get("marca") or "").strip()
    descripcion = str(datos.get("descripcion") or "").strip()
    estatus = str(datos.get("estatus") or "").strip()
    existencia = int(limpiar_numero(datos.get("existencia"), 0))
    unidad = str(datos.get("unidad") or "").strip()
    ubicacion = str(datos.get("ubicacion") or "").strip()
    ultimo_costo = limpiar_numero(datos.get("ultimo_costo"), 0.0)
    moneda = str(datos.get("moneda") or "").strip()
    precio_mayoreo = limpiar_numero(datos.get("precio_mayoreo"), 0.0)
    precio_publico = limpiar_numero(datos.get("precio_publico"), 0.0)

    # 4. Validar que al menos la descripción no esté vacía
    if not descripcion:
        raise HTTPException(status_code=400, detail="La descripción es obligatoria")

    # 5. Guardar en la base de datos Neon
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE productos SET 
                    familia = %s, marca = %s, descripcion = %s, estatus = %s, existencia = %s, 
                    unidad = %s, ubicacion = %s, ultimo_costo = %s, moneda = %s, precio_mayoreo = %s, 
                    precio_publico = %s, ultima_actualizacion = NOW()
                WHERE codigo = %s
            """, (familia, marca, descripcion, estatus, existencia,
                  unidad, ubicacion, ultimo_costo, moneda, precio_mayoreo, 
                  precio_publico, codigo))
            conn.commit()
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Producto no encontrado")
                
    return {"status": "Producto actualizado correctamente"}