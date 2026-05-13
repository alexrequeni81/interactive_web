import fitz  # PyMuPDF
import camelot
import os
import json # Para guardar en formato JSON
import re   # Para expresiones regulares (opcional, para filtrar)

# --- Configuración ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
pdf_file_path = os.path.join(BASE_DIR, "documento_ejemplo.pdf")
# Lista de pares: (índice_página_dibujo (0-based), número_página_tabla (1-based))
page_pairs = [
    (7, 9),  # Página 8 (dibujo), Página 9 (tabla)
    (9, 11)  # Página 10 (dibujo), Página 11 (tabla)
]
output_base_name = "extracted_drawing" # Nombre base para archivos
output_dir = os.path.join(BASE_DIR, "imagenes") # Directorio de salida
output_json_path = os.path.join(output_dir, f"{output_base_name}_data.json") # Un único JSON para todos los datos
dpi_render = 150 # Resolución para renderizar imágenes
# -------------------

def normalize_pos(pos_text):
    """Normaliza un texto POS a formato XX.Y"""
    # Reemplazar espacios múltiples o entre números por un punto
    normalized = re.sub(r'(\d)\s+(\d)', r'\1.\2', str(pos_text).strip())
    # Reemplazar comas por puntos (por si acaso)
    normalized = normalized.replace(',', '.')
    # Podríamos añadir más reglas si aparecen otros formatos
    return normalized

# --- Crear directorio de salida si no existe ---
os.makedirs(output_dir, exist_ok=True)

# Verificar si el archivo PDF existe
if not os.path.exists(pdf_file_path):
    print(f"Error: El archivo PDF '{pdf_file_path}' no se encontró.")
    exit()


# --- Inicializar datos de salida globales ---
output_json_data = {
    "sections": []
}

try:
    print(f"Abriendo documento: {pdf_file_path}")
    doc = fitz.open(pdf_file_path)
    print(f"Documento con {len(doc)} páginas.")

    # --- Bucle principal: Procesar cada par de páginas --- 
    for pair_index, (drawing_page_index, table_page_number) in enumerate(page_pairs):
        section_data = {
            "drawing_page_num": drawing_page_index + 1,
            "table_page_num": table_page_number,
            "image_path": "",
            "pos_locations": {},
            "table_data": [],
            "pdf_page_width": 0,
            "pdf_page_height": 0
        }
        print(f"\n--- Procesando Sección {pair_index + 1} (Dibujo P.{section_data['drawing_page_num']}, Tabla P.{section_data['table_page_num']}) ---")

        # --- 1. Procesar Página de Dibujo --- 
        if drawing_page_index < len(doc):
            page = doc.load_page(drawing_page_index)
            section_data["pdf_page_width"] = round(page.rect.width, 2)
            section_data["pdf_page_height"] = round(page.rect.height, 2)
            
            # --- a) Renderizar y guardar imagen ---
            image_filename = f"{output_base_name}_p{section_data['drawing_page_num']}.png"
            output_image_path_section = os.path.join(output_dir, image_filename)
            pix = page.get_pixmap(dpi=dpi_render)
            pix.save(output_image_path_section)
            # Guardar ruta relativa para el JSON (asumiendo que HTML está un nivel arriba)
            section_data["image_path"] = f"imagenes/{image_filename}"
            print(f"  Imagen guardada como '{output_image_path_section}'")
            print(f"  Dimensiones PDF guardadas: {section_data['pdf_page_width']} x {section_data['pdf_page_height']}")

            # --- b) Extraer palabras y coordenadas POS ---
            words = page.get_text("words") 
            pos_locations_dict = {}
            num_pos_found = 0
            pos_pattern = re.compile(r"^(\d+|\d+[\.\s]\d+)$", re.IGNORECASE)

            for word_info in words:
                x0, y0, x1, y1, text, _, _, _ = word_info
                text = text.strip()
                match = pos_pattern.match(text)
                if match:
                    pos_num_str = normalize_pos(text)
                    bbox = [round(coord, 2) for coord in [x0, y0, x1, y1]] 
                    if pos_num_str not in pos_locations_dict:
                        pos_locations_dict[pos_num_str] = [bbox]
                    else:
                        pos_locations_dict[pos_num_str].append(bbox)
                    num_pos_found += 1
            
            section_data["pos_locations"] = pos_locations_dict
            print(f"  Se identificaron {num_pos_found} ubicaciones para {len(pos_locations_dict)} números POS distintos.")

        else:
            print(f"  ERROR: Índice de página de dibujo {drawing_page_index} fuera de rango.")
            continue # Saltar al siguiente par si la página de dibujo no existe

        # --- 2. Procesar Página de Tabla --- 
        print(f"  Procesando página de tabla {table_page_number}...")
        try:
            tables = camelot.read_pdf(pdf_file_path, pages=str(table_page_number), flavor='lattice')
            print(f"  Camelot encontró {tables.n} tabla(s) en la página {table_page_number}.")
        except Exception as camelot_error:
             print(f"  ERROR al leer tablas de página {table_page_number} con Camelot: {camelot_error}")
             tables = None # Indicar que no se pudieron leer tablas
             
        all_table_rows_section = []
        if tables and tables.n > 0:
            for i in range(tables.n):
                 print(f"    Procesando Tabla {i+1} de {tables.n} en P.{table_page_number}")
                 df_raw = tables[i].df
                 
                 # Limpieza (misma lógica, adaptada para logs)
                 if len(df_raw) > 1: 
                     potential_headers = df_raw.iloc[1].tolist()
                     if 'POS.' in potential_headers or 'POS' in potential_headers:
                         # ... (limpieza de encabezados, normalización POS, etc. igual) ...
                         df_clean = df_raw.copy()
                         df_clean.columns = df_clean.iloc[1]
                         df_clean = df_clean[2:].reset_index(drop=True)
                         df_clean.columns = [str(col).replace('\n', ' ').strip() if col else f"col_{j}" for j, col in enumerate(df_clean.columns)]
                         pos_column_name = 'POS.'
                         if pos_column_name not in df_clean.columns and 'POS' in df_clean.columns:
                             pos_column_name = 'POS'
                         if pos_column_name in df_clean.columns:
                             df_clean[pos_column_name] = df_clean[pos_column_name].apply(normalize_pos)
                             table_records = df_clean.to_dict(orient='records')
                             all_table_rows_section.extend(table_records)
                             print(f"      Se añadieron {len(table_records)} filas de esta tabla.")
                         else:
                             print(f"      WARN: No se encontró columna POS en Tabla {i+1} de P.{table_page_number}.")
                     else:
                         print(f"      WARN: Fila 1 de Tabla {i+1} (P.{table_page_number}) no parece cabecera. Saltando.")
                 else:
                     print(f"      WARN: Tabla {i+1} (P.{table_page_number}) demasiado corta. Saltando.")
        
        section_data["table_data"] = all_table_rows_section
        print(f"  Total filas extraídas para esta sección: {len(all_table_rows_section)}.")
        
        # Añadir los datos de esta sección a la lista global
        output_json_data["sections"].append(section_data)

    # --- FIN Bucle Principal --- 
    
    # --- 3. Guardar Datos Globales en JSON --- 
    print(f"\nGuardando datos combinados de {len(output_json_data['sections'])} secciones en '{output_json_path}'")
    with open(output_json_path, 'w', encoding='utf-8') as f_json:
        json.dump(output_json_data, f_json, indent=4, ensure_ascii=False)
    print(f"Archivo JSON guardado.")

except Exception as e:
    print(f"\nOcurrió un error GENERAL durante el procesamiento:")
    print(e)
finally:
    if 'doc' in locals() and doc:
        print("Cerrando documento PDF.")
        doc.close()

print("\nScript finalizado.")
