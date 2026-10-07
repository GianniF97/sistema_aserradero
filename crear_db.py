import sqlite3

def inicializar_bd():
    conexion = sqlite3.connect('aserradero.db')
    cursor = conexion.cursor()

    # Habilitar soporte estricto de claves foráneas en SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Tabla Usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_usuario TEXT NOT NULL UNIQUE,
            clave_hash TEXT NOT NULL,
            rol TEXT CHECK(rol IN ('Operario', 'Administrador')) NOT NULL
        )
    ''')

    # 2. Tabla Proveedores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id_proveedor INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cuit_dni TEXT UNIQUE,
            telefono TEXT,
            direccion TEXT
        )
    ''')

    # 3. Tabla Clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cuit_dni TEXT UNIQUE,
            telefono TEXT,
            localidad TEXT
        )
    ''')

    # 4. Tabla Productos Terminados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS productos_terminados (
            id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_pieza TEXT NOT NULL,
            espesor_pulg REAL NOT NULL,
            ancho_pulg REAL NOT NULL,
            largo_pies REAL NOT NULL,
            stock_actual INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 10,
            precio_unitario REAL NOT NULL
        )
    ''')

    # 5. Tabla Lotes de Rollos (Materia Prima)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lotes_rollos (
            id_lote INTEGER PRIMARY KEY AUTOINCREMENT,
            id_proveedor INTEGER NOT NULL,
            especie TEXT NOT NULL,
            cantidad_rollos INTEGER NOT NULL,
            diametro_promedio_cm REAL NOT NULL,
            largo_promedio_m REAL NOT NULL,
            volumen_total_m3 REAL NOT NULL,
            fecha_ingreso DATETIME DEFAULT CURRENT_TIMESTAMP,
            estado TEXT CHECK(estado IN ('En Playón', 'Pendiente de Cubicación', 'En Banco de Aserrado', 'Procesado')) DEFAULT 'En Playón',
            FOREIGN KEY (id_proveedor) REFERENCES proveedores (id_proveedor) ON DELETE RESTRICT
        )
    ''')

    # 6. Tabla Órdenes de Corte
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordenes_corte (
            id_orden INTEGER PRIMARY KEY AUTOINCREMENT,
            id_lote INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_finalizacion DATETIME,
            estado TEXT CHECK(estado IN ('Pendiente', 'En Proceso', 'Finalizada', 'Cancelada')) DEFAULT 'Pendiente',
            porcentaje_desperdicio REAL DEFAULT 0.0,
            FOREIGN KEY (id_lote) REFERENCES lotes_rollos (id_lote) ON DELETE RESTRICT,
            FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario) ON DELETE RESTRICT
        )
    ''')

    # 7. Tabla Detalle de Orden de Corte
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detalle_orden_corte (
            id_detalle_orden INTEGER PRIMARY KEY AUTOINCREMENT,
            id_orden INTEGER NOT NULL,
            id_producto INTEGER NOT NULL,
            cantidad_piezas INTEGER NOT NULL,
            FOREIGN KEY (id_orden) REFERENCES ordenes_corte (id_orden) ON DELETE CASCADE,
            FOREIGN KEY (id_producto) REFERENCES productos_terminados (id_producto) ON DELETE RESTRICT
        )
    ''')

    # 8. Tabla Ventas y Remitos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventas_remitos (
            id_venta INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL,
            fecha_emision DATETIME DEFAULT CURRENT_TIMESTAMP,
            numero_remito_pdf TEXT UNIQUE,
            transportista TEXT,
            total_monto REAL NOT NULL,
            FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente) ON DELETE RESTRICT,
            FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario) ON DELETE RESTRICT
        )
    ''')

    # 9. Tabla Detalle de Venta
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detalle_venta (
            id_detalle_venta INTEGER PRIMARY KEY AUTOINCREMENT,
            id_venta INTEGER NOT NULL,
            id_producto INTEGER NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            FOREIGN KEY (id_venta) REFERENCES ventas_remitos (id_venta) ON DELETE CASCADE,
            FOREIGN KEY (id_producto) REFERENCES productos_terminados (id_producto) ON DELETE RESTRICT
        )
    ''')

    conexion.commit()
    conexion.close()
    print("Base de datos 'aserradero.db' y tablas creadas exitosamente.")

if __name__ == '__main__':
    inicializar_bd()