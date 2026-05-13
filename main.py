import fitz
import camelot
import os
import json
import re
import argparse
import sys
import shutil

# Silence harmless Windows temp cleanup errors from Camelot/Ghostscript
_rmtree = shutil.rmtree
shutil.rmtree = lambda p, **kw: _rmtree(p, onerror=lambda *a: None, **kw)

# --- Configuracion ---

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDFS_DIR = os.path.join(BASE_DIR, "documentos")
OUTPUT_DIR = os.path.join(BASE_DIR, "imagenes")
OUTPUT_BASE = "extracted_drawing"
DPI = 150
CATALOGS_JSON = os.path.join(OUTPUT_DIR, "catalogs.json")

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


def extract_drawing(page, page_num, output_dir, base_name, dpi, catalog_id):
    section = {}
    section["drawing_page_num"] = page_num
    section["pdf_page_width"] = round(page.rect.width, 2)
    section["pdf_page_height"] = round(page.rect.height, 2)

    filename = f"{base_name}_p{page_num}.png"
    path = os.path.join(output_dir, filename)
    pix = page.get_pixmap(dpi=dpi)
    pix.save(path)
    section["image_path"] = f"imagenes/{catalog_id}/{filename}"
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


_CID_RE = re.compile(r"\(cid:\d+\)")

_CANON_RULES = [
    (re.compile(r"^(POS\.|POS|ITEM)$", re.I), "POS."),
    (re.compile(r"(PIEZA|PART NUMBER)", re.I), "N\u00ba PIEZA / PART NUMBER"),
    (re.compile(r"DESCRIPCI", re.I), "DESCRIPCI\u00d3N"),
    (re.compile(r"^(PART NAME|NAME)$", re.I), "PART NAME"),
    (re.compile(r"CTD|QTY|QTTY", re.I), "CTD. / QTY."),
]


def _canonical(headers):
    """Normaliza headers al esquema comun. Retorna None si no detecta columna POS."""
    canon = []
    has_pos = False
    for h in headers:
        key = _CID_RE.sub("", str(h).replace("\n", " ").strip())
        mapped = key
        for pat, name in _CANON_RULES:
            if pat.search(key):
                mapped = name
                break
        canon.append(mapped)
        if mapped == "POS.":
            has_pos = True
    return canon if has_pos else None


def _parse_camelot_tables(tables, label=""):
    rows = []
    for t in tables:
        df = t.df
        if len(df) < 2:
            continue
        canon = _canonical(df.iloc[1].tolist())
        if canon is None:
            continue
        df.columns = canon
        df = df[2:].reset_index(drop=True)
        df["POS."] = df["POS."].apply(normalize_pos)
        records = df.to_dict(orient="records")
        rows.extend(records)
        print(f"    {label}Filas extraidas: {len(records)}")
    return rows


def extract_table(pdf_path, page_num):
    try:
        tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor="lattice")
        print(f"    Tablas encontradas: {tables.n}")
    except Exception as e:
        print(f"    ERROR Camelot: {e}")
        return []

    rows = _parse_camelot_tables(tables)
    if rows:
        return rows

    # Fallback: probar con stream por si la tabla no tiene bordes
    try:
        tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor="stream")
        print(f"    Sin POS con lattice, stream encuentra: {tables.n} tablas")
    except Exception as e:
        print(f"    ERROR Camelot stream: {e}")
        return []

    return _parse_camelot_tables(tables)


def update_catalogs_json(catalog_id, pdf_filename):
    catalogs = {"catalogs": []}
    if os.path.exists(CATALOGS_JSON):
        with open(CATALOGS_JSON, encoding="utf-8") as f:
            catalogs = json.load(f)
    existing = [c for c in catalogs["catalogs"] if c["id"] == catalog_id]
    if not existing:
        catalogs["catalogs"].append({
            "id": catalog_id,
            "name": catalog_id,
            "file": pdf_filename
        })
        catalogs["catalogs"].sort(key=lambda c: c["id"])
        with open(CATALOGS_JSON, "w", encoding="utf-8") as f:
            json.dump(catalogs, f, indent=2, ensure_ascii=False)


def process(pdf_path, pairs, output_dir, base_name, dpi, catalog_id, dry_run=False):
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
        sec = extract_drawing(page, drawing_idx + 1, output_dir, base_name, dpi, catalog_id)

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

def list_available_pdfs():
    pdfs = []
    if os.path.isdir(PDFS_DIR):
        for f in sorted(os.listdir(PDFS_DIR)):
            if f.lower().endswith(".pdf"):
                pdfs.append(f)
    return pdfs


def choose_pdf_interactive():
    pdfs = list_available_pdfs()
    if not pdfs:
        print("No hay PDFs en la carpeta 'documentos/'.")
        alt = input("  Ruta manual (o Enter para salir): ").strip()
        return alt if alt else None
    print("\nPDFs disponibles en 'documentos/':")
    for i, f in enumerate(pdfs, 1):
        size = os.path.getsize(os.path.join(PDFS_DIR, f)) / (1024 * 1024)
        print(f"  [{i}] {f} ({size:.0f} MB)")
    print(f"  [0] Especificar otra ruta")
    choice = input(f"\nElige (1-{len(pdfs)}, 0 manual): ").strip()
    if choice == "0":
        alt = input("  Ruta al PDF: ").strip()
        return alt if alt else None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(pdfs):
            return os.path.join(PDFS_DIR, pdfs[idx])
    except ValueError:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Extrae dibujos y tablas de PDFs tecnicos")
    parser.add_argument("--pdf", help="Nombre del PDF en 'documentos/' (ej: manual_ca9.pdf)")
    parser.add_argument("--pairs", nargs="+", help="Pares dibujo,tabla (ej: 8,9 10,11)")
    parser.add_argument("--dpi", type=int, default=DPI, help="Resolucion de imagenes")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar que se haria sin ejecutar")
    parser.add_argument("--list", action="store_true", help="Listar paginas del PDF y salir")
    args = parser.parse_args()

    # ── Localizar PDF ──
    pdf_path = None
    pdf_filename = None
    if args.pdf:
        # Buscar en documentos/
        candidate = os.path.join(PDFS_DIR, args.pdf)
        if os.path.exists(candidate):
            pdf_path = candidate
            pdf_filename = args.pdf
        else:
            print(f"ERROR: No se encuentra '{args.pdf}' en la carpeta 'documentos/'.")
            sys.exit(1)
    else:
        chosen = choose_pdf_interactive()
        if not chosen or not os.path.exists(chosen):
            print("Cancelado.")
            return
        pdf_path = chosen
        pdf_filename = os.path.basename(chosen)

    # ── Directorio de salida por catalogo ──
    catalog_id = os.path.splitext(pdf_filename)[0]
    catalog_output_dir = os.path.join(OUTPUT_DIR, catalog_id)
    os.makedirs(catalog_output_dir, exist_ok=True)

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

    # ── Resumen y confirmacion ──
    print(f"\n-- Resumen --")
    print(f"  Catalogo:  {catalog_id}")
    print(f"  PDF:       {pdf_path}")
    print(f"  Imagenes:  {catalog_output_dir}")
    print(f"  DPI:       {args.dpi}")
    print(f"  Secciones: {len(pairs)}")
    for i, (d, t) in enumerate(pairs):
        print(f"    {i+1}. Dibujo P.{d+1} -> Tabla P.{t}")

    if args.dry_run:
        print("\n  [DRY-RUN] No se ejecutara ninguna accion real.")
        process(pdf_path, pairs, catalog_output_dir, OUTPUT_BASE, args.dpi, catalog_id, dry_run=True)
        return

    confirm = input("\nProceder? (s/N): ").strip().lower()
    if confirm != "s":
        print("  Cancelado.")
        return

    process(pdf_path, pairs, catalog_output_dir, OUTPUT_BASE, args.dpi, catalog_id)
    update_catalogs_json(catalog_id, pdf_filename)


if __name__ == "__main__":
    main()
