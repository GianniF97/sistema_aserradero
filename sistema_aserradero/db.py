import sqlite3

def obtener_conexion():
    conexion = sqlite3.connect('aserradero.db')
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON;")
    return conexion

def insertar_usuario_inicial():
    conexion = obtener_conexion()
    conexion.execute('''
        INSERT OR IGNORE INTO usuarios (id_usuario, nombre_usuario, clave_hash, rol) 
        VALUES (1, 'admin', 'admin123', 'Administrador')
    ''')
    conexion.commit()
    conexion.close()



if __name__ == '__main__':
    insertar_usuario_inicial()
    print("Usuario administrador verificado/creado con éxito.")