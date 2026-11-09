# Apúntalo ✏️

**Toma nota de la clase.** Programa gratuito y de código abierto para sacar apuntes de clase en Windows, pensado para quien no tiene una herramienta para tomarlos. Escribes tus notas, o dejas que la app las tome sola de lo que se oye y se ve en la pantalla. Después las ordenas por asignatura y las exportas a PDF o a Word.

![Captura de la aplicación](docs/captura.png)

## Qué hace

- **Apuntes organizados**: una carpeta por asignatura, un apunte por clase, con etiquetas y buscador. Cada apunte es un archivo Markdown (`.md`) normal, así que tus apuntes son tuyos y se abren con cualquier editor.
- **Encima del vídeo de la clase**: la ventana se puede fijar siempre encima (📌), hacerse pequeña y semitransparente (🗗 Compacto), y mostrarse u ocultarse desde cualquier programa con **Ctrl+Alt+A**.
- **🤖 Apuntes automáticos**:
  - 🎧 Transcribe lo que se escucha con los *Subtítulos en directo* de Windows 11, sin internet.
  - 🖥 Guarda cada diapositiva nueva con su texto, leído con el OCR de Windows.
  - Puedes usar las dos cosas a la vez.
- **✨ Resumir con IA**: convierte la clase en apuntes ordenados (resumen, ideas clave, definiciones, tareas) con:
  - **ChatGPT**, gratis y sin claves: la app copia el texto y abre chatgpt.com; pegas, copias la respuesta y la app crea el apunte.
  - **Google Gemini**, con una clave gratuita de [Google AI Studio](https://aistudio.google.com/apikey). En el plan gratuito, Google puede usar los textos para mejorar sus productos.
  - **Claude** (Anthropic), con una clave de pago de [console.anthropic.com](https://console.anthropic.com). Cuesta unos céntimos por clase.
- **📤 Exportar a PDF y Word**: un apunte, una asignatura entera o todo, con títulos, negritas, listas, asignatura y fecha.
- **⏱ Marcas de tiempo, ▶ cronómetro y 📎 adjuntar capturas o PDF.**

## Descargar y usar

1. Descarga `Apuntalo.exe` desde la sección [**Releases**](../../releases).
2. Guárdalo en una carpeta tuya (por ejemplo, `Documentos\Apuntes`) y ábrelo con doble clic. Tus apuntes se guardan en `notas/`, al lado del `.exe`.

Al abrirlo puede pasar esto:
- Windows avisa con «Windows protegió su PC» porque el programa no está firmado: pulsa *Más información* → *Ejecutar de todas formas*.
- Si tienes activado el **Control inteligente de aplicaciones** de Windows 11, puede que el `.exe` quede bloqueado. En ese caso usa la versión con Python (abajo).

### Con Python (sin `.exe`)

Necesitas [Python 3.10 o superior](https://www.python.org/downloads/). Descarga el código y haz doble clic en **`Abrir apuntes.bat`**. No hace falta instalar nada más, salvo para el resumen con Claude: `py -3 -m pip install anthropic`.

## Atajos

| Tecla | Acción |
|---|---|
| Ctrl+N / Ctrl+S | Nuevo apunte / Guardar |
| Ctrl+F | Buscar |
| Ctrl+T | Insertar la hora, o el minuto del vídeo si el cronómetro está en marcha |
| Ctrl+E | Exportar a PDF o Word |
| F8 | Empezar o parar los apuntes automáticos |
| F9 / F10 | Fijar encima / Modo compacto |
| Ctrl+Alt+A | Mostrar u ocultar la ventana desde cualquier programa |
| Ctrl + / Ctrl - / Ctrl 0 (o Ctrl + rueda) | Letra más grande / más pequeña / normal |

Mientras escribes, el editor colorea el formato: títulos, **negritas**, *cursivas*, `código`, citas, tareas hechas y marcas de tiempo. Además:
- Se guarda solo cada 15 segundos, al cambiar de apunte y al cerrar.
- Al abrir la app vuelve al último apunte en el que estabas.

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
| `apuntes.pyw` | La aplicación (Python + tkinter, solo con la biblioteca estándar). |
| `exportar.py` | Exportar a DOCX (generado a mano) y a PDF (imprimiendo HTML con Microsoft Edge). |
| `captura.ps1` | Ayudante de PowerShell para el modo automático: lee los Subtítulos en directo y hace capturas con OCR. |
| `crear_exe.bat` | Genera `Apuntalo.exe` con PyInstaller. |

## Contribuir

¡Las contribuciones son bienvenidas!

1. Abre un *issue* para contar el error o la idea.
2. Haz un *fork*, crea una rama y envía un *pull request* con una descripción breve.
3. Mantén la app sin dependencias obligatorias: debe funcionar solo con Python y Windows. Las dependencias opcionales, como `anthropic`, se importan solo cuando se usan.
4. Escribe la interfaz y los mensajes en español, claros para alguien que no sabe de informática.

Antes de enviar cambios, pasa las pruebas desde la carpeta del proyecto: `py -3 -m unittest -v`.

Para generar el `.exe`: `py -3 -m pip install -r requirements.txt` y después ejecuta `crear_exe.bat`.

## Qué probar (lista para la versión 1.0)

- [ ] **Abrir:** doble clic en `Apuntalo.exe` (o en `Abrir apuntes.bat`). La ventana se abre y, la segunda vez, vuelve al último apunte.
- [ ] **Organizar:** crea la carpeta `Matemáticas/Tema 1` y un apunte con la plantilla *Clase / estudio*. Ponle etiquetas y búscalo con Ctrl+F.
- [ ] **Formato:** escribe `# Título`, `**negrita**` y `- [x] tarea` y comprueba que se colorean. Prueba Ctrl + y Ctrl - para cambiar el tamaño de la letra.
- [ ] **Autoguardado:** escribe algo, espera 15 segundos y cierra la app desde el Administrador de tareas. Al volver a abrirla, el texto sigue ahí.
- [ ] **Sobre un vídeo:** pon un vídeo de YouTube y pulsa F9 (fijar) y F10 (compacto). Ajusta la transparencia y prueba Ctrl+Alt+A desde el navegador.
- [ ] **Automático con audio:** F8, marca solo 🎧 y pon un vídeo con voz. Comprueba que el texto aparece en párrafos con su `[hh:mm:ss]` y sin repeticiones.
- [ ] **Automático con pantalla:** F8, marca 🖥 y elige con ✂ la zona de unas diapositivas. Cambia de diapositiva y comprueba que aparece una captura con su texto.
- [ ] **ChatGPT:** ✨ Resumir con IA → ChatGPT. Pega en chatgpt.com, copia la respuesta y pulsa «Crear apunte con la respuesta».
- [ ] **Gemini:** crea una clave gratis en aistudio.google.com/apikey y usa ✨ Resumir con IA → Gemini.
- [ ] **Exportar:** Ctrl+E y exporta a PDF y a Word un apunte y una asignatura entera. Abre el `.docx` en Word, LibreOffice o Google Docs y comprueba que se ve bien.
- [ ] **Compacto:** al pasar a modo compacto (F10), todos los botones de la barra pequeña funcionan.

## Licencia

[MIT](LICENSE): puedes usarlo, copiarlo, modificarlo y compartirlo libremente.
