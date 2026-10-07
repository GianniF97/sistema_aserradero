from datetime import datetime
import functools
import math
import os
from dotenv import load_dotenv
from flask import (Flask, flash, redirect, render_template, request, session,
                   url_for)
from werkzeug.security import check_password_hash
from db import obtener_conexion

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'clave_por_defecto_desarrollo')


def calcular_volumen_lote(cantidad_rollos, diametro_cm, largo_metros):
    radio_cm = diametro_cm / 2
    volumen_rollo_m3 = math.pi * (radio_cm / 100)**2 * largo_metros
    return round(volumen_rollo_m3 * cantidad_rollos, 3)


def calcular_volumen_smalian(d_mayor_cm: float, d_menor_cm: float, largo_m: float) -> float:
    """
    Calcula el volumen geométrico de un rollo mediante la fórmula de Smalian.
    
    :param d_mayor_cm: Diámetro mayor en centímetros (base gruesa)
    :param d_menor_cm: Diámetro menor en centímetros (despunte)
    :param largo_m: Longitud del rollo en metros
    :return: Volumen en metros cúbicos (m3) redondeado a 4 decimales
    """
    # Conversión de cm a metros
    d1 = d_mayor_cm / 100.0
    d2 = d_menor_cm / 100.0
    
    # Áreas de las secciones transversales (m2)
    area_1 = (math.pi * (d1 ** 2)) / 4.0
    area_2 = (math.pi * (d2 ** 2)) / 4.0
    
    # Smalian: promedio de áreas multiplicado por el largo
    volumen_m3 = ((area_1 + area_2) / 2.0) * largo_m
    
    return round(volumen_m3, 4)

def solo_dueno(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get('es_dueno'):
            flash(
                'Acceso restringido: Ingresá la clave de administración.',
                'error',
            )
            return redirect(url_for('login_dueno'))
        return view(**kwargs)

    return wrapped_view


@app.route('/login-dueno', methods=['GET', 'POST'])
def login_dueno():
    if request.method == 'POST':
        clave_ingresada = request.form.get('password', '').strip()
        conexion = obtener_conexion()
        usuario = conexion.execute(
            "SELECT clave_hash, rol FROM usuarios WHERE nombre_usuario ="
            " 'admin'"
        ).fetchone()
        conexion.close()

        if usuario and check_password_hash(
            usuario['clave_hash'], clave_ingresada
        ):
            session['es_dueno'] = True
            flash('Sesión de administración iniciada con éxito.', 'success')
            return redirect(url_for('inicio'))
        else:
            flash('Contraseña incorrecta. Intente nuevamente.', 'error')

    return render_template('login_dueno.html')


@app.route('/logout-dueno')
def logout_dueno():
    session.pop('es_dueno', None)
    flash('Sesión cerrada. Ahora estás en modo Operario.', 'success')
    return redirect(url_for('inicio'))


@app.route('/')
def inicio():
    es_dueno = session.get('es_dueno', False)
    conexion = obtener_conexion()

    total_rollos = conexion.execute(
        "SELECT COUNT(*) AS total, SUM(volumen_total_m3) AS vol FROM"
        " lotes_rollos WHERE estado = 'En Playón'"
    ).fetchone()
    ordenes_pendientes = conexion.execute(
        "SELECT COUNT(*) AS total FROM ordenes_corte WHERE estado = 'Pendiente'"
    ).fetchone()['total']
    total_proveedores = conexion.execute(
        'SELECT COUNT(*) AS total FROM proveedores'
    ).fetchone()['total']
    total_clientes = conexion.execute(
        'SELECT COUNT(*) AS total FROM clientes'
    ).fetchone()['total']

    conexion.close()

    resumen = {
        'lotes_playon': total_rollos['total'] or 0,
        'volumen_playon': round(total_rollos['vol'] or 0.0, 2),
        'ordenes_pendientes': ordenes_pendientes,
        'total_proveedores': total_proveedores,
        'total_clientes': total_clientes,
    }

    return render_template('inicio.html', resumen=resumen, es_dueno=es_dueno)


# --- Operaciones de Planta ---


@app.route('/ingreso-rollos', methods=['GET', 'POST'])
def ingresar_rollos():
    if request.method == 'POST':
        id_proveedor = int(request.form['id_proveedor'])
        especie = request.form['especie']
        cantidad_rollos = int(request.form['cantidad_rollos'])
        diametro_cm = float(request.form['diametro'])
        largo_metros = float(request.form['largo'])

        volumen_total = calcular_volumen_lote(
            cantidad_rollos, diametro_cm, largo_metros
        )

        conexion = obtener_conexion()
        conexion.execute(
            '''
            INSERT INTO lotes_rollos 
            (id_proveedor, especie, cantidad_rollos, diametro_promedio_cm, largo_promedio_m, volumen_total_m3)
            VALUES (?, ?, ?, ?, ?, ?)
        ''',
            (
                id_proveedor,
                especie,
                cantidad_rollos,
                diametro_cm,
                largo_metros,
                volumen_total,
            ),
        )
        conexion.commit()
        conexion.close()

        flash(
            f'Lote registrado exitosamente. Volumen total: {volumen_total} m³',
            'success',
        )
        return redirect(url_for('ingresar_rollos'))

    conexion = obtener_conexion()
    proveedores = conexion.execute(
        'SELECT id_proveedor, nombre FROM proveedores'
    ).fetchall()
    conexion.close()
    return render_template(
        'ingreso_rollos.html',
        proveedores=proveedores,
        es_dueno=session.get('es_dueno', False),
    )


@app.route('/stock-rollos', methods=['GET'])
def stock_rollos():
    conexion = obtener_conexion()
    rollos = conexion.execute('''
        SELECT l.id_lote, p.nombre AS proveedor, l.especie, l.cantidad_rollos,
               l.diametro_promedio_cm, l.largo_promedio_m, l.volumen_total_m3,
               l.fecha_ingreso, l.estado
        FROM lotes_rollos l
        JOIN proveedores p ON l.id_proveedor = p.id_proveedor
        WHERE l.estado = 'En Playón'
        ORDER BY l.fecha_ingreso DESC
    ''').fetchall()
    conexion.close()
    return render_template(
        'stock_rollos.html', rollos=rollos, es_dueno=session.get('es_dueno', False)
    )


# --- NUEVA: Creación de Órdenes de Corte por el Dueño ---
@app.route('/crear-orden-corte', methods=['GET', 'POST'])
@solo_dueno
def crear_orden_corte():
    conexion = obtener_conexion()
    cols_prod = [
        c[1]
        for c in conexion.execute(
            'PRAGMA table_info(productos_terminados)'
        ).fetchall()
    ]
    col_nom = 'tipo_pieza' if 'tipo_pieza' in cols_prod else 'nombre'

    if request.method == 'POST':
        id_lote = int(request.form['id_lote'])
        id_producto_solicitado = int(request.form['id_producto_solicitado'])
        indicaciones = request.form.get('indicaciones', '').strip()

        # Validar estado del lote
        lote = conexion.execute(
            "SELECT estado FROM lotes_rollos WHERE id_lote = ?", (id_lote,)
        ).fetchone()
        if not lote or lote['estado'] != 'En Playón':
            flash(
                'El lote seleccionado no está disponible en el playón.', 'error'
            )
            conexion.close()
            return redirect(url_for('crear_orden_corte'))

        conexion.execute(
            '''
            INSERT INTO ordenes_corte (id_lote, id_usuario, estado, porcentaje_desperdicio, id_producto_solicitado, indicaciones)
            VALUES (?, 1, 'Pendiente', 0.0, ?, ?)
        ''',
            (id_lote, id_producto_solicitado, indicaciones),
        )

        conexion.execute(
            "UPDATE lotes_rollos SET estado = 'En Banco de Aserrado' WHERE"
            ' id_lote = ?',
            (id_lote,),
        )
        conexion.commit()
        conexion.close()

        flash(
            'Orden de corte emitida exitosamente para los operarios de sierra.',
            'success',
        )
        return redirect(url_for('listar_ordenes_corte'))

    # Lotes disponibles en playón
    lotes_disponibles = conexion.execute('''
        SELECT l.id_lote, l.especie, l.cantidad_rollos, l.volumen_total_m3, p.nombre AS proveedor
        FROM lotes_rollos l
        JOIN proveedores p ON l.id_proveedor = p.id_proveedor
        WHERE l.estado = 'En Playón'
        ORDER BY l.id_lote ASC
    ''').fetchall()

    productos = conexion.execute(
        f'SELECT id_producto, {col_nom} AS nombre FROM productos_terminados'
    ).fetchall()
    conexion.close()

    id_lote_seleccionado = request.args.get('id_lote', type=int)

    return render_template(
        'crear_orden_corte.html',
        lotes=lotes_disponibles,
        productos=productos,
        id_lote_seleccionado=id_lote_seleccionado,
        es_dueno=True,
    )


# --- Banco de Aserrado (Visualización y Ejecución) ---
@app.route('/ordenes-corte', methods=['GET'])
def listar_ordenes_corte():
    conexion = obtener_conexion()
    cols_oc = [
        col[1]
        for col in conexion.execute('PRAGMA table_info(ordenes_corte)').fetchall()
    ]
    col_fecha = (
        'oc.fecha_creacion'
        if 'fecha_creacion' in cols_oc
        else ('oc.fecha_orden' if 'fecha_orden' in cols_oc else 'oc.id_orden')
    )

    cols_prod = [
        col[1]
        for col in conexion.execute(
            'PRAGMA table_info(productos_terminados)'
        ).fetchall()
    ]
    campo_nombre = 'tipo_pieza' if 'tipo_pieza' in cols_prod else 'nombre'

    ordenes = conexion.execute(f'''
        SELECT oc.id_orden, oc.id_lote, {col_fecha} AS fecha_orden, oc.estado,
               oc.indicaciones, oc.id_producto_solicitado,
               l.especie, l.volumen_total_m3, l.cantidad_rollos,
               p.nombre AS proveedor,
               pt.{campo_nombre} AS producto_pedido
        FROM ordenes_corte oc
        JOIN lotes_rollos l ON oc.id_lote = l.id_lote
        JOIN proveedores p ON l.id_proveedor = p.id_proveedor
        LEFT JOIN productos_terminados pt ON oc.id_producto_solicitado = pt.id_producto
        WHERE oc.estado = 'Pendiente'
        ORDER BY oc.id_orden ASC
    ''').fetchall()

    productos = conexion.execute(
        f'SELECT id_producto, {campo_nombre} AS nombre FROM'
        ' productos_terminados'
    ).fetchall()
    conexion.close()

    return render_template(
        'ordenes_corte.html',
        ordenes=ordenes,
        productos=productos,
        es_dueno=session.get('es_dueno', False),
    )


@app.route('/finalizar-corte/<int:id_orden>', methods=['POST'])
def finalizar_corte(id_orden):
    id_producto = int(request.form['id_producto'])
    cantidad_producida = float(request.form['cantidad_obtenida'])
    volumen_rollo_m3 = float(request.form['volumen_rollo'])
    volumen_util_m3 = float(request.form.get('volumen_aserrado_m3', 0))

    porcentaje_desperdicio = 0.0
    if volumen_rollo_m3 > 0 and volumen_util_m3 > 0:
        desperdicio = volumen_rollo_m3 - volumen_util_m3
        porcentaje_desperdicio = round((desperdicio / volumen_rollo_m3) * 100, 2)

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        '''
        INSERT INTO detalles_orden_corte (id_orden, id_producto, cantidad_producida)
        VALUES (?, ?, ?)
    ''',
        (id_orden, id_producto, cantidad_producida),
    )

    cursor.execute(
        '''
        UPDATE ordenes_corte 
        SET estado = 'Finalizada', porcentaje_desperdicio = ? 
        WHERE id_orden = ?
    ''',
        (porcentaje_desperdicio, id_orden),
    )

    cursor.execute(
        '''
        UPDATE lotes_rollos 
        SET estado = 'Procesado' 
        WHERE id_lote = (SELECT id_lote FROM ordenes_corte WHERE id_orden = ?)
    ''',
        (id_orden,),
    )

    cursor.execute(
        '''
        UPDATE productos_terminados 
        SET stock_actual = stock_actual + ? 
        WHERE id_producto = ?
    ''',
        (cantidad_producida, id_producto),
    )

    conexion.commit()
    conexion.close()

    flash(
        'Corte finalizado. Producción asentada y desperdicio calculado:'
        f' {porcentaje_desperdicio}%',
        'success',
    )
    return redirect(url_for('listar_ordenes_corte'))


# --- Módulos Administrativos y Remito Interno (Dueño) ---


@app.route('/remitos', methods=['GET'])
@solo_dueno
def listar_remitos():
    conexion = obtener_conexion()
    remitos = conexion.execute('''
        SELECT r.id_remito, r.numero_remito, r.fecha, r.chofer_transporte, r.patente_vehiculo,
               c.nombre AS cliente
        FROM remitos r
        JOIN clientes c ON r.id_cliente = c.id_cliente
        ORDER BY r.id_remito DESC
    ''').fetchall()
    conexion.close()
    return render_template('remitos_lista.html', remitos=remitos, es_dueno=True)


@app.route('/remitos/nuevo', methods=['GET', 'POST'])
@solo_dueno
def nuevo_remito():
    conexion = obtener_conexion()
    cols_prod = [
        c[1]
        for c in conexion.execute(
            'PRAGMA table_info(productos_terminados)'
        ).fetchall()
    ]
    col_nom = 'tipo_pieza' if 'tipo_pieza' in cols_prod else 'nombre'

    if request.method == 'POST':
        id_cliente = int(request.form['id_cliente'])
        chofer = request.form.get('chofer_transporte', '').strip()
        patente = request.form.get('patente_vehiculo', '').strip()
        productos_ids = request.form.getlist('id_producto[]')
        cantidades = request.form.getlist('cantidad[]')

        # Generar número de remito autoincremental legible (R-0001)
        ultimo = conexion.execute(
            'SELECT MAX(id_remito) AS ultimo FROM remitos'
        ).fetchone()['ultimo'] or 0
        numero_remito = f'REM-{ultimo + 1:04d}'

        cursor = conexion.cursor()
        cursor.execute(
            '''
            INSERT INTO remitos (numero_remito, id_cliente, chofer_transporte, patente_vehiculo)
            VALUES (?, ?, ?, ?)
        ''',
            (numero_remito, id_cliente, chofer, patente),
        )
        id_remito_creado = cursor.lastrowid

        # Insertar detalle y descontar stock
        for pid, cant in zip(productos_ids, cantidades):
            cant_float = float(cant)
            if cant_float > 0:
                cursor.execute(
                    '''
                    INSERT INTO detalles_remito (id_remito, id_producto, cantidad)
                    VALUES (?, ?, ?)
                ''',
                    (id_remito_creado, int(pid), cant_float),
                )

                cursor.execute(
                    '''
                    UPDATE productos_terminados 
                    SET stock_actual = stock_actual - ? 
                    WHERE id_producto = ?
                ''',
                    (cant_float, int(pid)),
                )

        conexion.commit()
        conexion.close()
        flash(f'Remito interno {numero_remito} emitido con éxito.', 'success')
        return redirect(
            url_for('ver_remito_detalle', id_remito=id_remito_creado)
        )

    clientes = conexion.execute(
        'SELECT id_cliente, nombre FROM clientes ORDER BY nombre ASC'
    ).fetchall()
    productos = conexion.execute(
        f'SELECT id_producto, {col_nom} AS nombre, stock_actual FROM'
        f' productos_terminados WHERE stock_actual > 0 ORDER BY {col_nom} ASC'
    ).fetchall()
    conexion.close()

    return render_template(
        'remito_form.html',
        clientes=clientes,
        productos=productos,
        es_dueno=True,
    )


@app.route('/remitos/<int:id_remito>')
@solo_dueno
def ver_remito_detalle(id_remito):
    conexion = obtener_conexion()
    cols_prod = [
        c[1]
        for c in conexion.execute(
            'PRAGMA table_info(productos_terminados)'
        ).fetchall()
    ]
    col_nom = 'tipo_pieza' if 'tipo_pieza' in cols_prod else 'nombre'

    remito = conexion.execute(
        '''
        SELECT r.*, c.nombre AS cliente_nombre, c.cuit_dni, c.direccion, c.telefono
        FROM remitos r
        JOIN clientes c ON r.id_cliente = c.id_cliente
        WHERE r.id_remito = ?
    ''',
        (id_remito,),
    ).fetchone()

    items = conexion.execute(
        f'''
        SELECT dr.cantidad, pt.{col_nom} AS producto_nombre
        FROM detalles_remito dr
        JOIN productos_terminados pt ON dr.id_producto = pt.id_producto
        WHERE dr.id_remito = ?
    ''',
        (id_remito,),
    ).fetchall()

    conexion.close()
    return render_template('remito_detalle.html', remito=remito, items=items)


@app.route('/proveedores', methods=['GET', 'POST'])
@solo_dueno
def gestionar_proveedores():
    conexion = obtener_conexion()
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        cuit_dni = request.form.get('cuit_dni', '').strip()
        telefono = request.form.get('telefono', '').strip()
        direccion = request.form.get('direccion', '').strip()

        if nombre:
            try:
                conexion.execute(
                    '''
                    INSERT INTO proveedores (nombre, cuit_dni, telefono, direccion)
                    VALUES (?, ?, ?, ?)
                ''',
                    (nombre, cuit_dni, telefono, direccion),
                )
                conexion.commit()
                flash(f'Proveedor "{nombre}" registrado con éxito.', 'success')
                return redirect(url_for('gestionar_proveedores'))
            except Exception as e:
                flash(f'Error al registrar proveedor: {e}', 'error')

    proveedores = conexion.execute(
        'SELECT * FROM proveedores ORDER BY id_proveedor DESC'
    ).fetchall()
    conexion.close()
    return render_template(
        'proveedores.html', proveedores=proveedores, es_dueno=True
    )


@app.route('/proveedores/eliminar/<int:id_proveedor>', methods=['POST'])
@solo_dueno
def eliminar_proveedor(id_proveedor):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    lotes = cursor.execute(
        'SELECT COUNT(*) AS total FROM lotes_rollos WHERE id_proveedor = ?',
        (id_proveedor,),
    ).fetchone()['total']
    if lotes > 0:
        flash(
            'No se puede eliminar: tiene lotes de rollos asociados.', 'error'
        )
    else:
        cursor.execute(
            'DELETE FROM proveedores WHERE id_proveedor = ?', (id_proveedor,)
        )
        conexion.commit()
        flash('Proveedor eliminado.', 'success')
    conexion.close()
    return redirect(url_for('gestionar_proveedores'))


@app.route('/clientes', methods=['GET', 'POST'])
@solo_dueno
def gestionar_clientes():
    conexion = obtener_conexion()
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        cuit_dni = request.form.get('cuit_dni', '').strip()
        telefono = request.form.get('telefono', '').strip()
        direccion = request.form.get('direccion', '').strip()
        email = request.form.get('email', '').strip()

        if nombre:
            try:
                conexion.execute(
                    '''
                    INSERT INTO clientes (nombre, cuit_dni, telefono, direccion, email)
                    VALUES (?, ?, ?, ?, ?)
                ''',
                    (nombre, cuit_dni, telefono, direccion, email),
                )
                conexion.commit()
                flash(f'Cliente "{nombre}" registrado.', 'success')
                return redirect(url_for('gestionar_clientes'))
            except Exception as e:
                flash(f'Error al registrar cliente: {e}', 'error')

    clientes = conexion.execute(
        'SELECT * FROM clientes ORDER BY id_cliente DESC'
    ).fetchall()
    conexion.close()
    return render_template('clientes.html', clientes=clientes, es_dueno=True)


@app.route('/clientes/eliminar/<int:id_cliente>', methods=['POST'])
@solo_dueno
def eliminar_cliente(id_cliente):
    conexion = obtener_conexion()
    conexion.execute(
        'DELETE FROM clientes WHERE id_cliente = ?', (id_cliente,)
    )
    conexion.commit()
    conexion.close()
    flash('Cliente eliminado.', 'success')
    return redirect(url_for('gestionar_clientes'))


@app.route('/productos', methods=['GET', 'POST'])
@solo_dueno
def gestionar_productos():
    conexion = obtener_conexion()
    info_cols = conexion.execute(
        'PRAGMA table_info(productos_terminados)'
    ).fetchall()
    cols_nombres = [c[1] for c in info_cols]
    col_nom = 'tipo_pieza' if 'tipo_pieza' in cols_nombres else 'nombre'

    if request.method == 'POST':
        nombre_pieza = request.form.get('nombre', '').strip()
        if nombre_pieza:
            campos = [col_nom]
            valores = [nombre_pieza]
            for col in info_cols:
                c_name, c_type, c_notnull, c_dflt, c_pk = (
                    col[1],
                    (col[2] or '').upper(),
                    col[3],
                    col[4],
                    col[5],
                )
                if c_pk or c_name == col_nom:
                    continue
                if c_name == 'stock_actual':
                    campos.append('stock_actual')
                    valores.append(0)
                elif c_notnull and c_dflt is None:
                    campos.append(c_name)
                    valores.append(
                        0.0
                        if any(
                            t in c_type
                            for t in ['INT', 'REAL', 'NUM', 'FLOAT']
                        )
                        else '-'
                    )

            sql = (
                f'INSERT INTO productos_terminados ({", ".join(campos)}) VALUES'
                f' ({", ".join(["?"] * len(campos))})'
            )
            conexion.execute(sql, valores)
            conexion.commit()
            flash(f'Producto "{nombre_pieza}" registrado.', 'success')
            return redirect(url_for('gestionar_productos'))

    productos = conexion.execute(
        f'SELECT id_producto, {col_nom} AS nombre, stock_actual FROM'
        ' productos_terminados ORDER BY id_producto DESC'
    ).fetchall()
    conexion.close()
    return render_template(
        'productos.html', productos=productos, es_dueno=True
    )
@app.route('/productos/eliminar/<int:id_producto>', methods=['POST'])
@solo_dueno
def eliminar_producto(id_producto):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    
    # Validar si ya se usó en órdenes finalizadas o remitos
    usado_corte = cursor.execute(
        "SELECT COUNT(*) AS total FROM detalles_orden_corte WHERE id_producto = ?", 
        (id_producto,)
    ).fetchone()['total']
    
    usado_remito = cursor.execute(
        "SELECT COUNT(*) AS total FROM detalles_remito WHERE id_producto = ?", 
        (id_producto,)
    ).fetchone()['total']

    if usado_corte > 0 or usado_remito > 0:
        flash('No se puede eliminar: el producto tiene registros históricos en cortes o remitos.', 'error')
    else:
        cursor.execute("DELETE FROM productos_terminados WHERE id_producto = ?", (id_producto,))
        conexion.commit()
        flash('Producto terminado eliminado correctamente.', 'success')

    conexion.close()
    return redirect(url_for('gestionar_productos'))

@app.route('/rollos/nuevo', methods=['POST'])
def agregar_rollo():
    d_mayor = float(request.form.get('diametro_mayor'))
    d_menor = float(request.form.get('diametro_menor'))
    largo = float(request.form.get('largo'))

    volumen = calcular_volumen_smalian(d_mayor, d_menor, largo)

    # Guardar en base de datos (SQLite)
    conexion = obtener_conexion()
    conexion.execute(
        "INSERT INTO rollos (diametro_mayor, diametro_menor, largo, volumen_m3) VALUES (?, ?, ?, ?)",
        (d_mayor, d_menor, largo, volumen)
    )
    conexion.commit()
    conexion.close()

    return redirect(url_for('stock_rollos'))


if __name__ == '__main__':
    app.run(debug=True)