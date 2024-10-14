import random
import barcode
from barcode.writer import ImageWriter

def generar_codigo_barras_aleatorio():
    # Generar el identificador único del producto (4 dígitos)
    producto_id = str(random.randint(1000, 9999))
    
    # Código de género (H: Hombre, M: Mujer)
    genero = random.choice(['H', 'M'])
    
    # Código de talla (01: XS, 02: S, 03: M, 04: L, 05: XL)
    talla = str(random.choice(['01', '02', '03', '04', '05']))
    
    # Código de material (01: Algodón, 02: Poliéster, 03: Lana, 04: Seda, 05: Lino)
    material = str(random.choice(['01', '02', '03', '04', '05']))
    
    # País de fabricación (01: China, 02: India, 03: Bangladesh, 04: Vietnam, 05: México)
    pais = str(random.choice(['01', '02', '03', '04', '05']))
    
    # Año de producción (últimos dos dígitos del año actual)
    año = str(random.randint(20, 30))  # Genera un año de producción entre 2020 y 2030

    # Crear el código de barras con los elementos especificados
    codigo_barras = f"{producto_id}{genero}{talla}{material}{pais}{año}"
    return codigo_barras

def crear_imagen_codigo_barras(codigo):
    # Usar el generador de códigos de barras con el formato Code128
    codigo_de_barras = barcode.get('code128', codigo, writer=ImageWriter())
    # Guardar la imagen con el nombre del código
    nombre_archivo = codigo_de_barras.save(codigo)
    return nombre_archivo

# Generar un código de barras aleatorio
codigo = generar_codigo_barras_aleatorio()
# Crear la imagen del código de barras
nombre_archivo = crear_imagen_codigo_barras(codigo)

print(f"Código de barras generado y guardado como imagen: {nombre_archivo}.png")