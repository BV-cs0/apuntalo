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

Para generar el `.exe`: `py -3 -m pip install -r requirements.txt` y después ejecuta `crear_exe.bat`.

## Licencia

[MIT](LICENSE): puedes usarlo, copiarlo, modificarlo y compartirlo libremente.
