# Ayudante de captura automática para Apúntalo (Windows PowerShell 5.1, sin instalar nada).
# Emite una línea JSON por evento en la salida estándar:
#   {"tipo":"voz","texto":"..."}                     -> frase de los Subtítulos en directo de Windows
#   {"tipo":"diapo","png":"ruta","texto":"..."}      -> la pantalla cambió: captura + texto (OCR)
#   {"tipo":"aviso","texto":"..."}                   -> mensajes para mostrar al usuario
param(
    [string]$Carpeta,
    [switch]$Pantalla,
    [switch]$Audio,
    [double]$Intervalo = 2,
    [string]$Zona = ""   # "x,y,ancho,alto" en píxeles reales; vacío = pantalla principal
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Emitir($obj) { [Console]::Out.WriteLine(($obj | ConvertTo-Json -Compress)); [Console]::Out.Flush() }

Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace Win -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[Win.Dpi]::SetProcessDPIAware() | Out-Null

# ---------- OCR (Windows.Media.Ocr) ----------
$ocr = $null
if ($Pantalla) {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $script:asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    function Esperar($op, [Type]$tipo) {
        $t = $script:asTask.MakeGenericMethod($tipo).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
    }
    $ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $ocr) { Emitir @{ tipo = "aviso"; texto = "El OCR de Windows no está disponible: solo se guardarán las capturas." } }
}

function Leer-Texto($ruta) {
    if (-not $ocr) { return "" }
    try {
        $f = Esperar ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ruta)) ([Windows.Storage.StorageFile])
        $s = Esperar ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $d = Esperar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $b = Esperar ($d.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $r = Esperar ($ocr.RecognizeAsync($b)) ([Windows.Media.Ocr.OcrResult])
        $s.Dispose()
        return (($r.Lines | ForEach-Object { $_.Text }) -join "`n")
    } catch { return "" }
}

# ---------- Pantalla ----------
$W = 64; $H = 36
function Miniatura([System.Drawing.Bitmap]$bmp) {
    $mini = New-Object System.Drawing.Bitmap $W, $H
    $g = [System.Drawing.Graphics]::FromImage($mini)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBilinear
    $g.DrawImage($bmp, 0, 0, $W, $H); $g.Dispose()
    $v = New-Object 'int[]' ($W * $H)
    for ($y = 0; $y -lt $H; $y++) { for ($x = 0; $x -lt $W; $x++) {
            $p = $mini.GetPixel($x, $y); $v[$y * $W + $x] = [int](($p.R * 3 + $p.G * 6 + $p.B) / 10) } }
    $mini.Dispose(); return , $v
}
function Diferencia($a, $b) {   # fracción de píxeles que cambiaron
    if (-not $a -or -not $b) { return 1.0 }
    $n = 0; for ($i = 0; $i -lt $a.Length; $i++) { if ([Math]::Abs($a[$i] - $b[$i]) -gt 24) { $n++ } }
    return $n / $a.Length
}
function Capturar {
    if ($Zona) { $z = $Zona.Split(",") | ForEach-Object { [int]$_ }; $r = New-Object System.Drawing.Rectangle $z[0], $z[1], $z[2], $z[3] }
    else { $r = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds }
    $bmp = New-Object System.Drawing.Bitmap $r.Width, $r.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.Location, [System.Drawing.Point]::Empty, $r.Size); $g.Dispose()
    return $bmp
}

# ---------- Subtítulos en directo (UI Automation) ----------
$caja = $null; $emitidas = New-Object System.Collections.Generic.List[string]; $pendiente = ""; $quieto = 0
if ($Audio) {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    if (-not (Get-Process LiveCaptions -ErrorAction SilentlyContinue)) { Start-Process LiveCaptions.exe }
}
function Buscar-Caja {
    $raiz = [System.Windows.Automation.AutomationElement]::RootElement
    $cv = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "LiveCaptionsDesktopWindow")
    $v = $raiz.FindFirst([System.Windows.Automation.TreeScope]::Children, $cv)
    if (-not $v) { return $null }
    $ct = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, "CaptionsTextBlock")
    return $v.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $ct)
}
function Normal($t) { return ($t -replace '\s+', ' ').Trim() }
# Los subtítulos muestran el final de la transcripción y reescriben las últimas palabras.
# Guardamos lo ya emitido ($hecho) y buscamos su final dentro del texto visible: lo que va detrás es nuevo.
$script:hecho = $null
function Clave($t) { return ($t.ToLower() -replace '[^\p{L}\p{N} ]', '' -replace '\s+', ' ').Trim() }
function Parte-Nueva($visible) {
    if (-not $script:hecho) { return $visible }
    $cv = Clave $visible
    foreach ($largo in 60, 35, 18) {
        $ch = Clave $script:hecho
        if ($ch.Length -lt $largo) { $largo = $ch.Length }
        if ($largo -lt 8) { break }
        $cola = $ch.Substring($ch.Length - $largo)
        $pos = $cv.LastIndexOf($cola)
        if ($pos -ge 0) {
            # Pasar la posición del texto "clave" al texto visible contando letras y números.
            $objetivo = ($cv.Substring(0, $pos + $largo) -replace ' ', '').Length; $cont = 0; $i = 0
            while ($i -lt $visible.Length -and $cont -lt $objetivo) {
                if ($visible[$i] -match '[\p{L}\p{N}]') { $cont++ }; $i++ }
            return $visible.Substring($i).TrimStart(' ', ',', '.', ';')
        }
    }
    return $visible
}
function Revisar-Voz {
    if (-not $script:caja) {
        $script:caja = Buscar-Caja
        if (-not $script:caja) { return }
        Emitir @{ tipo = "aviso"; texto = "Escuchando los Subtítulos en directo de Windows." }
        # Lo que ya hubiera en pantalla es de antes: no se apunta.
        try { $script:hecho = Normal $script:caja.Current.Name } catch { }
        return
    }
    try { $visible = Normal $script:caja.Current.Name } catch { $script:caja = $null; return }
    if (-not $visible) { return }
    $nuevo = Parte-Nueva $visible
    if (-not $nuevo) { $script:quieto = 0; return }
    if ($nuevo -eq $script:pendiente) { $script:quieto++ } else { $script:pendiente = $nuevo; $script:quieto = 0 }
    # Frases ya cerradas (terminan en . ? !) salen enseguida; el resto, tras ~3 s sin cambios.
    $corte = $nuevo.LastIndexOfAny([char[]]'.?!')
    if ($script:quieto -ge 3) { $corte = $nuevo.Length - 1 }
    if ($corte -ge 0 -and ($script:quieto -ge 3 -or $corte -lt $nuevo.Length - 1 -or $script:quieto -ge 1)) {
        $frase = $nuevo.Substring(0, $corte + 1).Trim()
        if ($frase) {
            Emitir @{ tipo = "voz"; texto = $frase }
            $script:hecho = (("$($script:hecho) $frase").Trim())
            if ($script:hecho.Length -gt 3000) { $script:hecho = $script:hecho.Substring($script:hecho.Length - 3000) }
        }
        $script:pendiente = ""; $script:quieto = 0
    }
}

# ---------- Bucle principal ----------
$ultimaGuardada = $null; $anterior = $null; $estable = 0; $textoAnterior = ""; $n = 0
$pasos = [Math]::Max(1, [int]($Intervalo))
while ($true) {
    if ($Pantalla) {
        try {
            $bmp = Capturar
            $mini = Miniatura $bmp
            if ((Diferencia $mini $anterior) -lt 0.06) { $estable++ } else { $estable = 0 }
            $anterior = $mini
            # Nueva "diapositiva": la imagen está quieta y es bastante distinta de la última guardada.
            if ($estable -ge 1 -and (Diferencia $mini $ultimaGuardada) -gt 0.2) {
                $n++; $ruta = Join-Path $Carpeta ("pantalla_{0:yyyyMMdd_HHmmss}.png" -f (Get-Date))
                $bmp.Save($ruta, [System.Drawing.Imaging.ImageFormat]::Png)
                $ultimaGuardada = $mini
                $t = Leer-Texto $ruta
                if ($t -and $t -eq $textoAnterior) { Remove-Item $ruta } else {
                    $textoAnterior = $t; Emitir @{ tipo = "diapo"; png = $ruta; texto = $t } }
            }
            $bmp.Dispose()
        } catch { Emitir @{ tipo = "aviso"; texto = "Error al capturar la pantalla: $($_.Exception.Message)" } }
    }
    for ($k = 0; $k -lt $pasos; $k++) {
        if ($Audio) { try { Revisar-Voz } catch { } }
        Start-Sleep -Milliseconds 1000
    }
}
