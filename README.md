# Apúntalo ✏️

[![PyPI](https://img.shields.io/pypi/v/apuntalo)](https://pypi.org/project/apuntalo/)
[![Python](https://img.shields.io/pypi/pyversions/apuntalo)](https://pypi.org/project/apuntalo/)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green)](https://github.com/BV-cs0/apuntalo/blob/main/LICENSE)

**Toma nota de la clase.** Programa gratuito y de código abierto para sacar apuntes de clase en Windows, pensado para quien no tiene una herramienta para tomarlos. Escribes tus notas, o dejas que la app las tome sola de lo que se oye y se ve en la pantalla. Después las ordenas por asignatura y las exportas a PDF o a Word.

![Captura de la aplicación](https://raw.githubusercontent.com/BV-cs0/apuntalo/main/docs/captura.png)

## Qué hace

- **Apuntes organizados**: una carpeta por asignatura, un apunte por clase, con etiquetas y buscador. Cada apunte es un archivo Markdown (`.md`) normal, así que tus apuntes son tuyos y se abren con cualquier editor.
- **Encima del vídeo de la clase**: la ventana se puede fijar siempre encima (📌), hacerse pequeña y semitransparente (🗗 Compacto; con el ratón encima se ve entera), y mostrarse u ocultarse desde cualquier programa con **Ctrl+Alt+A**. Fijada sobre un vídeo a pantalla completa, puede esconder la barra de tareas de Windows mientras escribes (clic derecho en 📌).
- **Listas y esquemas como en Canva**: numeración automática con subniveles `a.` e `i.`, flechas (`->` da →), bloques de color (💡 idea, ⚠ ojo, ✅ resumen...) y **modo oscuro** (botón ☾). El título sale grande y centrado, y los comandos entre `comillas` en un recuadro.
- **✓ Corrector en español e inglés**: subraya en rojo las faltas mientras escribes y, con **F7**, te pregunta «¿Quieres corregir estas palabras?» con la sugerencia de cada una. No marca el código, los enlaces ni las siglas.
- **🤖 Apuntes automáticos**:
  - 🎧 Transcribe lo que se escucha con los *Subtítulos en directo* de Windows 11, sin internet.
  - 🖥 Guarda cada diapositiva nueva con su texto, leído con el OCR de Windows.
  - Puedes usar las dos cosas a la vez.
- **✨ Resumir con IA**: convierte la clase en apuntes ordenados (resumen, ideas clave, definiciones, tareas) con:
  - **ChatGPT**, gratis y sin claves: la app copia el texto y abre chatgpt.com; pegas, copias la respuesta y la app crea el apunte.
  - **Google Gemini**, con una clave gratuita de [Google AI Studio](https://aistudio.google.com/apikey). En el plan gratuito, Google puede usar los textos para mejorar sus productos.
  - **Claude** (Anthropic), con una clave de pago de [console.anthropic.com](https://console.anthropic.com). Cuesta unos céntimos por clase.
- **📤 Exportar**: un apunte, una asignatura entera o todo. Eliges el formato (*Guardar como*) y la carpeta (*Guardar en*):
  - **PDF**, para imprimir o enviar.
  - **Word (.docx)** y **OpenDocument (.odt)**, para seguir editando en Word, Google Docs o LibreOffice.
  - **Página web (.html)**, que se abre en cualquier navegador con las imágenes dentro.
  - **Markdown (.md)**, para Obsidian, Notion o GitHub.
  - **Texto sin formato (.txt)**.
- **📥 Importar**: trae tus apuntes de Word (.docx), LibreOffice (.odt), páginas web (.html), Markdown (.md) o texto (.txt) para seguir editándolos aquí. Conserva títulos, negritas, cursivas, listas, tablas e imágenes.
- **🖼 Imágenes con Ctrl+V**: haz un recorte con Win+Shift+S (o copia una imagen) y pégalo en el apunte. En el editor se ve solo la imagen, y sale también al exportar. Para quitarla, pulsa Retroceso justo detrás de ella.
- **▦ Tablas y 🗺 mapa mental**: inserta tablas que se ven alineadas en el editor, se recorren con Tab y salen como tablas de verdad al exportar. Convierte los títulos y listas del apunte en un mapa mental que se guarda entero como imagen SVG (o PNG, con Pillow).
- **⏱ Marcas de tiempo, ▶ cronómetro y 📎 adjuntar capturas o PDF.**

## Instalar

Hay dos formas. Elige la que te resulte más cómoda.

### Opción 1: descargar el programa (`.exe`), la más fácil

1. Descarga `Apuntalo.exe` desde [**Releases**](https://github.com/BV-cs0/apuntalo/releases/latest).
2. Guárdalo en una carpeta tuya (por ejemplo, `Documentos\Apuntes`).
3. Ábrelo con doble clic. Windows te preguntará si quieres que haga cambios en el equipo: pulsa **Sí**. Apúntalo pide permisos de administrador solo, para que todas las funciones (atajos globales, captura de pantalla y subtítulos en directo) funcionen bien. Si pulsas *No*, se abre igual, sin esos permisos. Tus apuntes se guardan en `notas/`, al lado del `.exe`, así que puedes llevarlo en un pendrive.

La primera vez que lo abres, Apúntalo deja un acceso directo en el Escritorio y en el menú Inicio (apuntando a ese `.exe`, sin moverlo ni copiarlo), para que luego no tengas que volver a buscar la carpeta.

Cada vez que haya una versión nueva, te avisa con un pequeño aviso 🔔 arriba a la derecha de la ventana: haz clic para ir a la página de descargas. La versión que tienes aparece en el título de la ventana y lo que cambia en cada una está en [Releases](https://github.com/BV-cs0/apuntalo/releases).

**Si tienes activado el Control inteligente de aplicaciones** de Windows 11, Apúntalo no crea accesos directos a un `.exe` recién descargado, porque Windows no dejaría abrirlos (y quita los que hubiera creado una versión anterior): ábrelo directamente desde el `.exe`.

Al abrirlo puede pasar esto:
- Windows avisa con «Windows protegió su PC» porque el programa no está firmado: pulsa *Más información* → *Ejecutar de todas formas*.
- Si tienes activado el **Control inteligente de aplicaciones** de Windows 11, puede que el `.exe` quede bloqueado. En ese caso usa la opción 2.
- Si al abrir el acceso directo «Apúntalo» Windows dice que bloqueó una «extensión de archivo peligrosa de web», abre `Apuntalo.exe` directamente. Las versiones nuevas ya no crean ese acceso.

### Opción 2: instalar con Python (`pip`)

Apúntalo está en [PyPI](https://pypi.org/project/apuntalo/).

Necesitas [Python 3.10 o superior](https://www.python.org/downloads/). Al instalarlo, marca «Add python.exe to PATH». Después abre una terminal y escribe:

```
py -m pip install apuntalo
```

Para abrirlo, escribe `py -m apuntalo` (o solo `apuntalo`) y pulsa **Sí** cuando Windows pida permisos de administrador. Tus apuntes se guardan en `Documentos\Apuntalo`.

- Para el resumen con Claude: `py -m pip install "apuntalo[claude]"`.
- Para actualizar a la última versión: `py -m pip install -U apuntalo`.

### Opción 3: desde el código

Descarga el código, abre **`Abrir apuntes.bat`** y pulsa **Sí** cuando Windows pida permisos de administrador. Los apuntes se guardan en la propia carpeta del proyecto.

> En las tres opciones puedes elegir otra carpeta para los apuntes con la variable de entorno `APUNTALO_DATOS`.

## Atajos

| Tecla | Acción |
|---|---|
| Ctrl+N / Ctrl+S | Nuevo apunte / Guardar |
| Ctrl+F | Buscar |
| Ctrl+V | Pegar texto o **imágenes**: un recorte (Win+Shift+S), una imagen copiada del navegador o archivos copiados en el Explorador. Se guardan en los adjuntos del apunte y se ven dentro del texto |
| Ctrl+T | Insertar la hora, o el minuto del vídeo si el cronómetro está en marcha |
| Ctrl+E | Exportar (PDF, Word, OpenDocument, web, Markdown o texto) |
| Ctrl+I | Importar apuntes de otros programas |
| F8 | Empezar o parar los apuntes automáticos |
| F9 / F10 | Fijar encima / Modo compacto |
| Ctrl+Alt+A | Mostrar u ocultar la ventana desde cualquier programa |
| Ctrl + / Ctrl - / Ctrl 0 (o Ctrl + rueda) | Letra más grande / más pequeña / normal |
| Ctrl+Retroceso / Ctrl+Supr | Borrar la palabra entera a la izquierda / a la derecha |
| Mayús+Supr | Borrar la palabra a la derecha (o cortar la selección, según el ajuste del clic derecho) |
| Ctrl+B / Ctrl+K / Ctrl+Mayús+X | **Negrita** / *cursiva* / ~~tachado~~ (con texto seleccionado lo envuelve) |
| `(` `[` `{` `"` `¿` `¡` `«` | Se cierran solos con el cursor en medio. Al escribir el cierre se lo salta, y Retroceso en un par vacío borra los dos |
| Tab / Enter en una tabla | Celda siguiente / primera celda de la fila siguiente; al final añade una fila nueva y alinea las columnas (botón ▦ Tabla) |
| Enter en una lista | Siguiente elemento (`1.` → `2.`, `a.` → `b.`). En un elemento vacío, termina la lista |
| Tab / Mayús+Tab | Bajar o subir un nivel de la lista (`1.` → `a.` → `i.`) |
| Retroceso tras la viñeta | En `2.` vacío pasa a `a.`; en `a.` vuelve al número; otra vez, quita la viñeta |
| `->` `=>` `<=` `!=` `...` + espacio | Se convierten en → ⇒ ≤ ≠ … (Ctrl+Z lo deshace) |
| Espacio tras una palabra sin tilde | Se corrige sola (`aqui` → `aquí`), también antes de punto o paréntesis. Ctrl+Z lo deshace |
| Letra al empezar línea o frase | Sale en mayúscula, también tras `¿`, `¡`, `(` o comillas. Se desactiva en el clic derecho |
| `/idea` `/ojo` `/resumen` `/nota` `/pregunta` `/definicion` + espacio | Bloque destacado de color (también en el botón ➕ Bloque) |
| F7 | Revisar la ortografía: «¿Quieres corregir estas palabras?» con la sugerencia de cada una (también en ✓ Ortografía) |
| Clic derecho en una palabra subrayada | Sugerencias, o «Añadir a mi diccionario» para que no se marque más |
| Clic derecho en 📌 Fijar | Ocultar la barra de tareas mientras escribes sobre un vídeo a pantalla completa |

Mientras escribes, el editor colorea el formato: títulos, **negritas**, *cursivas*, `código`, citas, tareas hechas y marcas de tiempo. Además:
- Se guarda solo cada 15 segundos, al cambiar de apunte y al cerrar.
- Al abrir la app vuelve al último apunte en el que estabas.
- Corrector en **español e inglés a la vez**: subraya en rojo lo mal escrito, pero no el código entre `comillas`, los enlaces, las rutas ni las siglas. Usa el diccionario de Windows; si a Windows le falta el inglés, usa `pyspellchecker` (va incluido en el `.exe`; con pip: `pip install apuntalo[ortografia]`).

## Apuntes automáticos: detalles

- **Audio**: la primera vez que se usan los Subtítulos en directo de Windows, hay que aceptar su aviso de privacidad y descargar el idioma. Captan el sonido del PC (el vídeo o la videollamada) y, si se activa en los subtítulos, también el micrófono.
- **Pantalla**: con **✂ Elegir zona del vídeo** recortas solo el vídeo o las diapositivas, y el texto sale mucho más limpio. La ventana de Apúntalo no aparece en las capturas.
- **Ventana encima del vídeo**: funciona sobre vídeos en ventana y sobre la pantalla completa del navegador. No puede ponerse encima de un programa en pantalla completa *exclusiva*.
- **Respeta a los demás**: pide permiso antes de grabar o transcribir una clase o una reunión.

## Privacidad

Tus apuntes se quedan en tu PC. Solo salen de él si usas **Resumir con IA**: con ChatGPT los pegas tú; con Gemini o Claude, la app envía el texto del apunte a ese servicio. Las claves de API se guardan en `config.json`, en tu PC, y nunca se suben al repositorio.

## Estructura del código

| Archivo | Qué hace |
|---|---|
| `apuntalo/app.py` | La aplicación (Python + tkinter, solo con la biblioteca estándar). |
| `apuntalo/editor.py` | Lógica del editor sin ventanas: listas que se numeran solas, Tab y Retroceso en listas, borrar palabras, flechas y bloques. |
| `apuntalo/ortografia.py` | Corrector en español e inglés con el diccionario de Windows (por COM, con `ctypes`) y `pyspellchecker` de respaldo. |
| `apuntalo/exportar.py` | Exportar a PDF (imprimiendo HTML con Microsoft Edge), DOCX y ODT (generados a mano), HTML, Markdown y texto. |
| `apuntalo/importar.py` | Importar DOCX, ODT, HTML, Markdown y texto, convirtiéndolos a Markdown. |
| `apuntalo/portapapeles.py` | Leer imágenes y archivos copiados (Ctrl+V) sin librerías externas. |
| `apuntalo/actualizar.py` | Comprueba en segundo plano si hay una versión nueva y la avisa con el 🔔. |
| `apuntalo/accesos.py` | Crea los accesos directos del `.exe` y quita los que Windows no dejaría abrir. |
| `apuntalo/control_apps.py` | Detecta el Control inteligente de aplicaciones de Windows 11 y la marca de «descargado de Internet». |
| `apuntalo/captura.ps1` | Ayudante de PowerShell para el modo automático: lee los Subtítulos en directo y hace capturas con OCR. |
| `apuntalo/crear_acceso.ps1` | Crea un acceso directo del `.exe` (lo usa `accesos.py`). |
| `apuntes.pyw` | Lanzador para abrir la app desde el código con doble clic. |
| `pyproject.toml` | Configuración del paquete de PyPI (`pip install apuntalo`). |

## Contribuir

¡Las contribuciones son bienvenidas!

1. Abre un *issue* para contar el error o la idea.
2. Haz un *fork*, crea una rama y envía un *pull request* con una descripción breve.
3. Mantén la app sin dependencias obligatorias: debe funcionar solo con Python y Windows. Las dependencias opcionales, como `anthropic`, se importan solo cuando se usan.
4. Escribe la interfaz y los mensajes en español, claros para alguien que no sabe de informática.

Antes de enviar cambios, pasa las pruebas desde la carpeta del proyecto: `py -3 -m unittest -v`.

### Publicar una versión nueva (mantenedores)

1. Sube el número en `apuntalo/__init__.py` (`__version__`).
2. Crea una *Release* en GitHub con la etiqueta `vX.Y.Z` y escribe en ella qué cambia.
3. Al publicar la *Release*, GitHub Actions genera `Apuntalo.exe` con PyInstaller, lo adjunta junto con la versión a PyPI (`.github/workflows/publicar.yml`). Usa *Trusted Publishing*, sin contraseñas ni tokens. También se puede lanzar a mano: *Actions* → **Publicar en PyPI y en la Release** → *Run workflow* (eso solo reconstruye para comprobar que compila, sin publicar nada). PyPI no deja volver a subir un número de versión que ya existe: si ya está, el workflow se la salta.

## Licencia

[MIT](https://github.com/BV-cs0/apuntalo/blob/main/LICENSE): puedes usarlo, copiarlo, modificarlo y compartirlo libremente.
