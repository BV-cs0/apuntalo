"""Leer imágenes y archivos del portapapeles de Windows sin librerías externas.

- imagen_png(): la imagen copiada (Win+Shift+S, «Copiar imagen» del navegador...) como PNG.
- archivos(): rutas de archivos copiados en el Explorador.
"""
import ctypes
import struct
import sys
import zlib

CF_DIB, CF_HDROP, CF_DIBV5 = 8, 15, 17


def _win():
    if sys.platform != "win32":
        return None
    from ctypes import wintypes
    u, k, s = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.shell32
    u.OpenClipboard.argtypes = [wintypes.HWND]
    u.GetClipboardData.argtypes = [wintypes.UINT]
    u.GetClipboardData.restype = ctypes.c_void_p
    u.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k.GlobalSize.argtypes = [ctypes.c_void_p]
    k.GlobalSize.restype = ctypes.c_size_t
    s.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_wchar_p, wintypes.UINT]
    s.DragQueryFileW.restype = wintypes.UINT
    return u, k, s


def _leer(formato):
    """Bytes crudos de un formato del portapapeles, o None."""
    api = _win()
    if not api:
        return None
    u, k, _ = api
    if not u.IsClipboardFormatAvailable(formato) or not u.OpenClipboard(None):
        return None
    try:
        h = u.GetClipboardData(formato)
        if not h:
            return None
        p = k.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.string_at(p, k.GlobalSize(h))
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def hay_texto():
    """True si lo copiado es texto (entonces Ctrl+V pega texto normal, aunque haya también una imagen,
    como pasa al copiar celdas de Excel o párrafos de Word)."""
    api = _win()
    return bool(api and api[0].IsClipboardFormatAvailable(13))  # CF_UNICODETEXT


def archivos():
    """Rutas de los archivos copiados en el Explorador (Ctrl+C sobre archivos)."""
    api = _win()
    if not api:
        return []
    u, _, s = api
    if not u.IsClipboardFormatAvailable(CF_HDROP) or not u.OpenClipboard(None):
        return []
    try:
        h = u.GetClipboardData(CF_HDROP)
        if not h:
            return []
        n = s.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
        rutas = []
        for i in range(n):
            largo = s.DragQueryFileW(h, i, None, 0) + 1
            buf = ctypes.create_unicode_buffer(largo)
            s.DragQueryFileW(h, i, buf, largo)
            rutas.append(buf.value)
        return rutas
    finally:
        u.CloseClipboard()


def imagen_png():
    """La imagen del portapapeles convertida a PNG (bytes), o None si no hay imagen."""
    datos = _leer(CF_DIBV5) or _leer(CF_DIB)
    if not datos:
        return None
    try:
        return dib_a_png(datos)
    except (ValueError, struct.error):
        return None


def dib_a_png(dib):
    """Convierte un DIB de Windows (BITMAPINFOHEADER + píxeles) de 24 o 32 bits a PNG."""
    tam_cab, ancho, alto, _, bits, compresion = struct.unpack_from("<IiiHHI", dib, 0)
    colores_usados = struct.unpack_from("<I", dib, 32)[0]
    if bits not in (24, 32) or compresion not in (0, 3) or ancho <= 0 or alto == 0:
        raise ValueError("formato de imagen no admitido")
    inicio = tam_cab
    if compresion == 3 and tam_cab == 40:      # BI_BITFIELDS: 3 máscaras detrás de la cabecera
        inicio += 12
    inicio += colores_usados * 4
    paso = ((ancho * bits + 31) // 32) * 4
    bpp = bits // 8
    filas_abajo_arriba = alto > 0
    alto = abs(alto)
    if len(dib) < inicio + paso * alto:
        raise ValueError("imagen incompleta")
    crudo = bytearray()
    for y in range(alto):
        fila_origen = (alto - 1 - y) if filas_abajo_arriba else y
        fila = dib[inicio + fila_origen * paso: inicio + fila_origen * paso + ancho * bpp]
        rgb = bytearray(ancho * 3)
        rgb[0::3] = fila[2::bpp]   # BGR(A) -> RGB
        rgb[1::3] = fila[1::bpp]
        rgb[2::3] = fila[0::bpp]
        crudo += b"\x00" + rgb     # filtro PNG «ninguno»
    return png(ancho, alto, bytes(crudo))


def png(ancho, alto, filas_rgb):
    def trozo(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n"
            + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(filas_rgb, 6))
            + trozo(b"IEND", b""))


def tamano_png(datos):
    """(ancho, alto) de un PNG, o None."""
    if datos[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", datos[16:24])
