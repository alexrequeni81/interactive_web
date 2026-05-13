import fitz
import camelot
import os
import json
import re
import argparse
import sys

# --- Configuracion ---

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PDF = os.path.join(BASE_DIR, "documento_ejemplo.pdf")
OUTPUT_DIR = os.path.join(BASE_DIR, "imagenes")
OUTPUT_BASE = "extracted_drawing"
DPI = 150

# --- Funciones ---

def normalize_pos(text):
    normalized = re.sub(r'(\d)\s+(\d)', r'\1.\2', str(text).strip())
    normalized = normalized.replace(',', '.')
    return normalized


def show_pdf_info(doc):
    print(f"  Páginas: {len(doc)}")
    print(f"  Tamaño:  {doc[0].rect.width:.0f} x {doc[0].rect.height:.0f} pts (aprox)")
    print(f"  Metadatos: {doc.metadata.get('title', '-') or '-'} / {doc.metadata.get('author', '-') or '-'}")
    print()
    print("  Vista rápida de páginas (primeras 30 líneas de texto):")
    for i in range(min(len(doc), 132)):
        raw = doc[i].get_text("text").strip()[:80].replace("\n", " | ")
        text = raw.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        text = re.sub(r"[^\x20-\x7E\xA0-\xFF\u00F1\u00D1]", "?", text)
        if text.strip():
            print(f"    [{i+1:>3}] {text}")


def list_pages(doc):
    for i in range(len(doc)):
        raw = doc[i].get_text("text").strip()[:100].replace("\n", " | ")
        text = re.sub(r"[^\x20-\x7E\xA0-\xFF\u00F1\u00D1]", "?", raw)
        print(f"  Pag.{i+1:>3}: {text}")


def parse_pairs(raw):
    pairs = []
    for arg in raw:
        parts = arg.split(",")
        if len(parts) != 2:
            print(f"  ERROR: Formato inválido '{arg}'. Usa: dibujo,tabla (ej: 7,9)")
            sys.exit(1)
        try:
            drawing = int(parts[0]) - 1
            table = int(parts[1])
            pairs.append((drawing, table))
        except ValueError:
            print(f"  ERROR: Los valores deben ser números: '{arg}'")
            sys.exit(1)
    return pairs


def ask_pairs_interactive(doc):
    pairs = []
    print("\n  Introduce los pares Dibujo,Tabla (ej: 8,9).")
    print("  Vacío para terminar.")
    print("  Puedes ver el listado completo con --list")
    while True:
        raw = input(f"  Par {len(pairs)+1} (dibujo,tabla): ").strip()
        if not raw:
            if not pairs:
                print("  Debes introducir al menos un par.")
                continue
            break
        try:
            parts = raw.split(",")
            if len(parts) != 2:
                print("  Formato: dibujo,tabla (ej: 8,9)")
                continue
            drawing = int(parts[0]) - 1
            table = int(parts[1])
            if drawing < 0 or drawing >= len(doc):
                print(f"  Página de dibujo {parts[0]} fuera de rango (1-{len(doc)})")
                continue
            if table < 1 or table > len(doc):
                print(f"  Página de tabla {table} fuera de rango (1-{len(doc)})")
                continue
            pairs.append((drawing, table))
        except ValueError:
            print("  Solo números separados por coma.")
    return pairs


def extract_drawing(page, page_num, output_dir, base_name, dpi):
    section = {}
    section["drawing_page_num"] = page_num
    section["pdf_page_width"] = round(page.rect.width, 2)
    section["pdf_page_height"] = round(page.rect.height, 2)

    filename = f"{base_name}_p{page_num}.png"
    path = os.path.join(output_dir, filename)
    pix = page.get_pixmap(dpi=dpi)
    pix.save(path)
    section["image_path"] = f"imagenes/{filename}"
    print(f"    Imagen: {path}")

    words = page.get_text("words")
    locations = {}
    count = 0
    pattern = re.compile(r"^(\d+|\d+[\.\s]\d+)$")
    for w in words:
        x0, y0, x1, y1, text, _, _, _ = w
        text = text.strip()
        if pattern.match(text):
            key = normalize_pos(text)
            bbox = [round(c, 2) for c in [x0, y0, x1, y1]]
            locations.setdefault(key, []).append(bbox)
            count += 1

    section["pos_locations"] = locations
    print(f"    POS detectados: {count} -> {len(locations)} unicos")
    return section


def _parse_camelot_tables(tables, label=""):
    """Intenta extraer filas con POS de tablas Camelot. Retorna (rows, ok)."""
    rows = []
    for t in tables:
        df = t.df
        if len(df) < 2:
            continue
        headers = df.iloc[1].tolist()
        if "POS." not in headers and "POS" not in headers:
            continue
        df.columns = df.iloc[1]
        df = df[2:].reset_index(drop=True)
        df.columns = [
            str(c).replace("\n", " ").strip() if c else f"col_{j}"
            for j, c in enumerate(df.columns)
        ]
        pos_col = "POS." if "POS." in df.columns else "POS"
        df[pos_col] = df[pos_col].apply(normalize_pos)
        records = df.to_dict(orient="records")
        rows.extend(records)
        print(f"    {label}Filas extraidas: {len(records)}")
    return rows


def extract_table(pdf_path, page_num):
    flavors = ["lattice", "stream"]

    for i, flavor in enumerate(flavors):
        try:
            tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor=flavor)
            label = f"[{flavor}] " if len(flavors) > 1 else ""
            print(f"    {label}Tablas encontradas: {tables.n}")
        except Exception as e:
            print(f"    {label}ERROR Camelot: {e}")
            continue

        rows = _parse_camelot_tables(tables, label=label)
        if rows:
            if i > 0:
                print(f"    -> stream recupero {len(rows)} filas con POS")
            return rows
        if i == 0 and len(flavors) > 1:
            print(f"    Sin POS con lattice, probando stream...")

    return []


def process(pdf_path, pairs, output_dir, base_name, dpi, dry_run=False):
    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    output = {"sections": []}

    for idx, (drawing_idx, table_num) in enumerate(pairs):
        print(f"\n-- Seccion {idx+1}: Dibujo P.{drawing_idx+1} / Tabla P.{table_num} --")

        if drawing_idx >= len(doc):
            print(f"  ERROR: Página de dibujo {drawing_idx+1} fuera de rango.")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Se procesaría: dibujo={drawing_idx+1}, tabla={table_num}")
            continue

        page = doc.load_page(drawing_idx)

        print("  [Dibujo]")
        sec = extract_drawing(page, drawing_idx + 1, output_dir, base_name, dpi)

        print("  [Tabla]")
        sec["table_data"] = extract_table(pdf_path, table_num)
        sec["table_page_num"] = table_num

        output["sections"].append(sec)

    if not dry_run and output["sections"]:
        json_path = os.path.join(output_dir, f"{base_name}_data.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        print(f"\nOK - JSON guardado: {json_path}")
        print(f"  Secciones: {len(output['sections'])}")
        total_rows = sum(len(s.get("table_data", [])) for s in output["sections"])
        print(f"  Filas totales: {total_rows}")

    doc.close()
    return output


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="Extrae dibujos y tablas de un PDF")
    parser.add_argument("--pdf", default=DEFAULT_PDF, help="Ruta al PDF")
    parser.add_argument("--pairs", nargs="+", help="Pares dibujo,tabla (ej: 8,9 10,11)")
    parser.add_argument("--dpi", type=int, default=DPI, help="Resolución de imágenes")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar qué se haría sin ejecutar")
    parser.add_argument("--list", action="store_true", help="Listar páginas del PDF y salir")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Directorio de salida")
    parser.add_argument("--base", default=OUTPUT_BASE, help="Nombre base archivos")
    args = parser.parse_args()

    pdf_path = args.pdf
    if not os.path.exists(pdf_path):
        print(f"ERROR: No se encuentra el PDF: {pdf_path}")
        alt = input("  Ruta alternativa (o Enter para salir): ").strip()
        if alt and os.path.exists(alt):
            pdf_path = alt
        else:
            sys.exit(1)

    print(f"\n--- PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    show_pdf_info(doc)

    if args.list:
        print("\n-- Listado completo --")
        list_pages(doc)
        doc.close()
        return

    # ── Definir pares ──
    if args.pairs:
        pairs = parse_pairs(args.pairs)
    else:
        print("\n-- Configuracion interactiva --")
        pairs = ask_pairs_interactive(doc)

    doc.close()

    if not pairs:
        print("  No hay pares que procesar.")
        return

    # ── Resumen y confirmación ──
    print(f"\n-- Resumen --")
    print(f"  PDF:       {pdf_path}")
    print(f"  Imágenes:  {args.output}")
    print(f"  DPI:       {args.dpi}")
    print(f"  Secciones: {len(pairs)}")
    for i, (d, t) in enumerate(pairs):
        print(f"    {i+1}. Dibujo P.{d+1} -> Tabla P.{t}")

    if args.dry_run:
        print("\n  [DRY-RUN] No se ejecutará ninguna acción real.")
        process(pdf_path, pairs, args.output, args.base, args.dpi, dry_run=True)
        return

    confirm = input("\n¿Proceder? (s/N): ").strip().lower()
    if confirm != "s":
        print("  Cancelado.")
        return

    process(pdf_path, pairs, args.output, args.base, args.dpi)


if __name__ == "__main__":
    main()
