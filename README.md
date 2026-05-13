# Catálogo Interactivo

Extrae dibujos y tablas de PDFs técnicos y los publica como catálogo web interactivo con navegación por secciones, zonas cliqueables, carrito de compra y soporte para múltiples catálogos.

---

## ¿Cómo funciona?

**1. Colocar PDFs en `documentos/`**

Cada PDF debe estar en la carpeta `documentos/` (ignorada por git — no se sube a GitHub).

**2. Ejecutar `main.py` para extraer los datos**

El script escanea `documentos/` y te deja elegir qué PDF procesar y qué pares de páginas (dibujo + tabla) extraer:

```bash
python main.py                          →  Modo interactivo (elige PDF, pares)
python main.py --pdf archivo.pdf        →  Usar un PDF concreto de documentos/
python main.py --pairs 8,9 10,11        →  Directo (varios pares)
python main.py --dry-run                →  Ensayo (muestra qué haría)
python main.py --list                   →  Lista páginas del PDF
```

Por cada sección extrae:
- **Imagen del dibujo** → `imagenes/<catalog_name>/extracted_drawing_pN.png`
- **Números POS** → coordenadas de cada pieza sobre el dibujo
- **Tabla de piezas** → número de pieza, descripción, cantidad

El script genera automáticamente `imagenes/catalogs.json` con la lista de catálogos disponibles.

**3. Publicar en web**

Los datos extraídos se suben a GitHub Pages (seguimiento de `imagenes/`) y se ven en:

```
https://alexrequeni81.github.io/interactive_web/
```

---

## Estructura del proyecto

```
pdf_interactivo/
├── main.py                    → Script de extracción
├── index.html                 → Web del catálogo
├── requirements.txt           → Dependencias Python
├── documentos/                → PDFs fuente (ignorados por git)
│   ├── catalogo1.pdf
│   └── catalogo2.pdf
└── imagenes/                  → Datos extraídos (trackeados por git)
    ├── catalogs.json           → Índice de catálogos (generado automáticamente)
    ├── catalogo1/
    │   ├── extracted_drawing_data.json
    │   ├── extracted_drawing_p1.png
    │   └── extracted_drawing_p2.png
    └── catalogo2/
        ├── extracted_drawing_data.json
        ├── extracted_drawing_p1.png
        └── extracted_drawing_p2.png
```

---

## Gestión de tablas

El script se adapta automáticamente al formato de tabla que encuentra:

| En el PDF se llama... | En la web se ve como... |
|---|---|
| `POS.` o `ITEM` | `POS.` |
| `Nº PIEZA / PART NUMBER` o `PIEZA / PART` | `Nº PIEZA / PART NUMBER` |
| `DESCRIPCIÓN` | `DESCRIPCIÓN` |
| `PART NAME` o `NAME` | `PART NAME` |
| `CTD. / QTY.`, `CTD.`, `QTY.` o `QTTY` | `CTD. / QTY.` |

Si una tabla no tiene ninguna de estas columnas, se salta y sigue con la siguiente sección.

---

## Navegación web

Una vez publicado:

- **Catálogos**: desplegable en la parte superior para cambiar entre catálogos
- **Secciones**: botones `<<` y `>>` para cambiar entre dibujos de un catálogo
- **POS**: al pasar el ratón sobre un número en el dibujo, se resalta su fila en la tabla
- **Tabla**: al pasar sobre una fila, se marca su posición en el dibujo
- **Zoom**: rueda del ratón para acercar/alejar
- **Arrastre**: clic y arrastrar para mover el dibujo ampliado
- **Carrito**: añade piezas con cantidad, modifica o elimina; se mantiene al cambiar de catálogo

---

## Requisitos para ejecutar el script

```bash
pip install -r requirements.txt
```

Necesitas Python 3.8+ y Ghostscript instalado en el sistema (Camelot lo requiere para leer tablas).
