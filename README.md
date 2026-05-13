# Catálogo Interactivo

Extrae dibujos y tablas de un PDF técnico y los publica como catálogo web interactivo con navegación por secciones, zonas cliqueables y carrito de compra.

---

## ¿Cómo funciona?

**1. Extraer datos del PDF**

El script `main.py` abre un PDF, localiza las páginas que indicas (dibujo + tabla) y extrae:

- **Imagen del dibujo** → se guarda en `imagenes/`
- **Números POS** → coordenadas de cada pieza sobre el dibujo
- **Tabla de piezas** → número de pieza, descripción, cantidad, etc.

```bash
python main.py --pairs 8,9 10,11
```

Esto procesa: Pág.8 (dibujo) + Pág.9 (tabla) como sección 1, y Pág.10 + Pág.11 como sección 2.

**2. Publicar en web**

Los datos extraídos se suben a GitHub Pages y se ven automáticamente en:

```
https://alexrequeni81.github.io/interactive_web/
```

---

## Formas de usar el script

```
python main.py                          →  Modo interactivo (pide PDF y pares)
python main.py --pairs 8,9 10,11 12,13 →  Directo (varios pares)
python main.py --dry-run                →  Ensayo (muestra qué haría sin ejecutar)
python main.py --list                   →  Lista todas las páginas del PDF
python main.py --pdf otro.pdf           →  Usar otro archivo PDF
```

El script muestra un resumen y pide confirmación antes de empezar.

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

- **Secciones**: botones `<<` y `>>` para cambiar entre dibujos
- **POS**: al pasar el ratón sobre un número en el dibujo, se resalta su fila en la tabla
- **Tabla**: al pasar sobre una fila, se marca su posición en el dibujo
- **Zoom**: rueda del ratón para acercar/alejar
- **Arrastre**: clic y arrastrar para mover el dibujo ampliado
- **Carrito**: añade piezas con cantidad, modifica o elimina

---

## Requisitos para ejecutar el script

```bash
pip install -r requirements.txt
```

Necesitas Python 3.8+ y Ghostscript instalado en el sistema (Camelot lo requiere para leer tablas).
