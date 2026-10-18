import os
import django
import sys

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.files import File
from riego.models import Especie

# Ruta a tu carpeta de fotos
FOTOS_DIR = r'C:\Users\mszam\Desktop\Electiva 1\fotosplantas'

# Mapeo: nombre del archivo -> nombre de la especie
MAPEO = {
    'suculenta.jpg': 'Suculenta (Pachyphytum)',
    'suculenta.png': 'Suculenta (Pachyphytum)',
    'suculenta.jpeg': 'Suculenta (Pachyphytum)',
    'cactus.jpg': 'Cactus Cholla (Cylindropuntia)',
    'cactus.png': 'Cactus Cholla (Cylindropuntia)',
    'cactus.jpeg': 'Cactus Cholla (Cylindropuntia)',
}


def main():
    if not os.path.exists(FOTOS_DIR):
        print(f"No se encontró la carpeta: {FOTOS_DIR}")
        print("Asegúrate de que las imágenes estén en:")
        print("  C:\\Users\\mszam\\Desktop\\Electiva 1\\fotosplantas\\")
        return

    archivos = os.listdir(FOTOS_DIR)
    imagenes = [f for f in archivos if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    if not imagenes:
        print("No se encontraron imágenes en la carpeta.")
        print(f"Buscando en: {FOTOS_DIR}")
        return

    print(f"Encontradas {len(imagenes)} imagen(es): {imagenes}")

    for archivo in imagenes:
        nombre_archivo = archivo.lower()

        # Buscar en el mapeo
        nombre_especie = MAPEO.get(nombre_archivo)

        # Si no está en el mapeo, intentar buscar por coincidencia de nombre
        if not nombre_especie:
            nombre_sin_ext = os.path.splitext(archivo)[0].lower()
            for especie in Especie.objects.all():
                if nombre_sin_ext in especie.nombre.lower() or especie.nombre.lower() in nombre_sin_ext:
                    nombre_especie = especie.nombre
                    break

        if not nombre_especie:
            print(f"  ⚠️  No se pudo identificar la especie para: {archivo}")
            continue

        try:
            especie = Especie.objects.get(nombre=nombre_especie)
        except Especie.DoesNotExist:
            print(f"  ⚠️  No existe la especie '{nombre_especie}' en la base de datos.")
            continue

        ruta_imagen = os.path.join(FOTOS_DIR, archivo)

        with open(ruta_imagen, 'rb') as f:
            especie.foto.save(archivo, File(f), save=True)

        print(f"  ✅ {especie.nombre} <- {archivo}")

    print("\n✨ ¡Listo! Las fotos se han asignado a las especies.")
    print("Ahora puedes recargar la página de Mis plantas y ver las imágenes.")


if __name__ == '__main__':
    main()
