import os
import json
from datetime import datetime
from fpdf import FPDF

# Import charting functions
from modules.charts import (
    render_gauge,
    render_dot,
    render_bars,
    render_text,
    create_trend_chart,
    create_bp_trend_chart,
    create_multi_trend_chart,
)

# ==========================================
# 1. HELPER: HEX TO RGB CONVERTER
# ==========================================
def hex_to_rgb(hex_color):
    """Converts Streamlit #RRGGBB hex colors to FPDF (R, G, B) tuples."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

# ==========================================
# 2. WIREFRAME BASE PARAMETERS
# ==========================================
PAGE_W, PAGE_H = 210, 297
PAGE_MARGIN, INNER_PADDING, SPACING = 5, 10, 8
LINE_WIDTH = 0.5     

ELEM_PAD_H, ELEM_PAD_V, TITLE_BODY_GAP = 5, 4, 2       
FONT_SIZE_H1, FONT_SIZE_H2, FONT_SIZE_BODY = 14, 11, 10
LINE_H_H1, LINE_H_H2, LINE_H_BODY = 8, 6, 5          

TEST_PAD_H, TEST_PAD_V, TEST_LINE_GAP = 3, 4, 3
TEST_VAL_W, TEST_UNIT_W = 20, 20
FONT_SIZE_LARGE, LINE_H_LARGE = 16, 8
FONT_SIZE_SMALL, LINE_H_SMALL = 9, 4

LOGO_W, LOGO_H, LOGO_ALIGN = 50, 15, 'RIGHT'     
INNER_BOX_GAP, INFO_BOX_RATIO = 4, 0.4     

FOOTER_MARGIN_BOTTOM, FOOTER_LINE_W, FOOTER_GAP, FOOTER_LINE_H, FONT_SIZE_FOOTER = 20, 0.2, 2, 4, 8

BOTTOM_LIMIT = PAGE_H - FOOTER_MARGIN_BOTTOM - PAGE_MARGIN
BANNER_X = PAGE_MARGIN + INNER_PADDING
BANNER_W = PAGE_W - (2 * PAGE_MARGIN) - (2 * INNER_PADDING)

# ==========================================
# 3. HELPER FUNCTIONS (Now reading from theme)
# ==========================================

def get_text_height(pdf_obj, text, max_width, line_height):
    if not text: return 0
    total_lines = sum(math_lines(pdf_obj, para, max_width) if para else 1 for para in text.split('\n'))
    return total_lines * line_height

def math_lines(pdf_obj, text, max_width):
    lines, current_w = 1, 0
    for word in text.split(' '):
        w = pdf_obj.get_string_width(word + " ")
        if current_w + w > max_width:
            lines += 1; current_w = w
        else:
            current_w += w
    return lines

def draw_dynamic_text_block(pdf_obj, y_pos, title, body_text):
    if not body_text: return y_pos
    
    font_fam = pdf_obj.theme.get('font', 'Helvetica')
    pdf_obj.set_font(font_fam, '', FONT_SIZE_BODY)
    text_width = BANNER_W - (2 * ELEM_PAD_H)
    
    box_h = ELEM_PAD_V + LINE_H_H2 + TITLE_BODY_GAP + get_text_height(pdf_obj, body_text, text_width, LINE_H_BODY) + ELEM_PAD_V
    
    if y_pos + box_h > BOTTOM_LIMIT:
        pdf_obj.add_page(); y_pos = PAGE_MARGIN + INNER_PADDING
        
    pdf_obj.set_fill_color(*hex_to_rgb(pdf_obj.theme['banner_bg']))
    pdf_obj.set_draw_color(*hex_to_rgb(pdf_obj.theme['border']))
    pdf_obj.rect(x=BANNER_X, y=y_pos, w=BANNER_W, h=box_h, style='FD', round_corners=True, corner_radius=pdf_obj.theme['radius'])
    
    pdf_obj.set_xy(BANNER_X + ELEM_PAD_H, y_pos + ELEM_PAD_V)
    pdf_obj.set_font(font_fam, 'B', FONT_SIZE_H2)
    pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_primary']))
    pdf_obj.cell(w=text_width, h=LINE_H_H2, text=title, align='L')
    
    pdf_obj.set_xy(BANNER_X + ELEM_PAD_H, y_pos + ELEM_PAD_V + LINE_H_H2 + TITLE_BODY_GAP)
    pdf_obj.set_font(font_fam, '', FONT_SIZE_BODY)
    pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_muted']))
    pdf_obj.multi_cell(w=text_width, h=LINE_H_BODY, text=body_text, align='L')
    return y_pos + box_h + pdf_obj.theme.get('spacing', 8)

def draw_test_block(pdf_obj, y_pos, title, val, unit, date, target, note="", img_gauge=None, img_trend=None, chart_box_h=42, history=None):
    is_double = bool(img_gauge) and bool(img_trend)
    font_fam = pdf_obj.theme.get('font', 'Helvetica')
    
    inner_w = BANNER_W - (2 * ELEM_PAD_H)
    info_w = (inner_w - INNER_BOX_GAP) * INFO_BOX_RATIO
    chart_w = (inner_w - INNER_BOX_GAP) * (1 - INFO_BOX_RATIO)
    info_h = (chart_box_h * 2) + INNER_BOX_GAP if is_double else chart_box_h
    
    note_h = 0
    if note:
        pdf_obj.set_font(font_fam, 'I', FONT_SIZE_BODY)
        note_h = ELEM_PAD_V + get_text_height(pdf_obj, note, inner_w - (2 * ELEM_PAD_H), LINE_H_BODY) + ELEM_PAD_V

    block_h = ELEM_PAD_V + info_h + (INNER_BOX_GAP if note else 0) + note_h + ELEM_PAD_V
    
    if y_pos + block_h > BOTTOM_LIMIT:
        pdf_obj.add_page(); y_pos = PAGE_MARGIN + INNER_PADDING

    # Outer Box
    pdf_obj.set_fill_color(*hex_to_rgb(pdf_obj.theme['banner_bg']))
    pdf_obj.set_draw_color(*hex_to_rgb(pdf_obj.theme['border']))
    pdf_obj.rect(x=BANNER_X, y=y_pos, w=BANNER_W, h=block_h, style='FD', round_corners=True, corner_radius=pdf_obj.theme['radius'])

    info_x, inner_y, chart_x = BANNER_X + ELEM_PAD_H, y_pos + ELEM_PAD_V, BANNER_X + ELEM_PAD_H + info_w + INNER_BOX_GAP

    # Info Box Background
    pdf_obj.set_fill_color(*hex_to_rgb(pdf_obj.theme['inner_box']))
    pdf_obj.rect(x=info_x, y=inner_y, w=info_w, h=info_h, style='FD', round_corners=True, corner_radius=pdf_obj.theme['radius'])
    
    y_title, y_val = inner_y + TEST_PAD_V, inner_y + TEST_PAD_V + LINE_H_H2 + TEST_LINE_GAP
    text_w = info_w - (2 * TEST_PAD_H)

    # Title
    pdf_obj.set_xy(info_x + TEST_PAD_H, y_title)
    pdf_obj.set_font(font_fam, 'B', FONT_SIZE_H2)
    pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_primary']))
    pdf_obj.cell(w=text_w, h=LINE_H_H2, text=title, align='L')
    
    # Value & Unit
    pdf_obj.set_text_color(0, 0, 0)
    if '\n' in val:
        pdf_obj.set_font(font_fam, 'B', 11)
        pdf_obj.set_xy(info_x + TEST_PAD_H, y_val)
        pdf_obj.multi_cell(w=text_w, h=6, text=val, align='L')
        y_date = pdf_obj.get_y() + TEST_LINE_GAP
    else:
        pdf_obj.set_xy(info_x + TEST_PAD_H, y_val)
        pdf_obj.set_font(font_fam, 'B', 22)
        val_width = pdf_obj.get_string_width(val) + 2
        pdf_obj.cell(w=val_width, h=LINE_H_LARGE, text=val, align='L')
        pdf_obj.set_font(font_fam, 'B', FONT_SIZE_BODY)
        pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_muted']))
        pdf_obj.cell(w=TEST_UNIT_W, h=LINE_H_LARGE, text=unit, align='L')
        y_date = y_val + LINE_H_LARGE + TEST_LINE_GAP
    
    # Date & Target
    y_target = y_date + LINE_H_SMALL
    pdf_obj.set_font(font_fam, '', FONT_SIZE_SMALL)
    pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_muted']))
    pdf_obj.set_xy(info_x + TEST_PAD_H, y_date)
    pdf_obj.cell(w=text_w, h=LINE_H_SMALL, text=f"Date: {date}", align='L')
    pdf_obj.set_xy(info_x + TEST_PAD_H, y_target)
    pdf_obj.cell(w=text_w, h=LINE_H_SMALL, text=f"Target: {target}", align='L')

    # History Table
    if is_double and history and len(history) > 1:
        table_y = inner_y + chart_box_h + INNER_BOX_GAP 
        pdf_obj.set_xy(info_x + TEST_PAD_H, table_y + 2)
        pdf_obj.set_font(font_fam, 'B', 8)
        pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_primary']))
        pdf_obj.cell(w=text_w * 0.5, h=4, text="Previous Dates", align='L')
        pdf_obj.cell(w=text_w * 0.5, h=4, text="Result", align='R')
        pdf_obj.set_font(font_fam, '', 8)
        pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_muted']))
        current_table_y = table_y + 6
        for h_date, h_val in history[1:5]:
            pdf_obj.set_xy(info_x + TEST_PAD_H, current_table_y)
            pdf_obj.cell(w=text_w * 0.5, h=4, text=h_date, align='L')
            pdf_obj.cell(w=text_w * 0.5, h=4, text=f"{h_val} {unit}".strip(), align='R')
            current_table_y += 4

    # Chart Boxes
    pdf_obj.set_fill_color(*hex_to_rgb(pdf_obj.theme['inner_box'])) 
    pdf_obj.rect(x=chart_x, y=inner_y, w=chart_w, h=chart_box_h, style='FD', round_corners=True, corner_radius=pdf_obj.theme['radius'])
    if img_gauge:
        pdf_obj.image(img_gauge, x=chart_x, y=inner_y, w=chart_w)
    else:
        pdf_obj.set_xy(chart_x, inner_y)
        pdf_obj.set_font(font_fam, 'B', FONT_SIZE_BODY)
        pdf_obj.set_text_color(180, 200, 220)
        pdf_obj.cell(w=chart_w, h=chart_box_h, text="[ TEXT ONLY ]", align='C')

    if is_double:
        chart_y2 = inner_y + chart_box_h + INNER_BOX_GAP
        pdf_obj.rect(x=chart_x, y=chart_y2, w=chart_w, h=chart_box_h, style='FD', round_corners=True, corner_radius=pdf_obj.theme['radius'])
        if img_trend:
            pdf_obj.image(img_trend, x=chart_x, y=chart_y2, w=chart_w)

    # Note Box
    if note:
        note_y = inner_y + info_h + INNER_BOX_GAP
        pdf_obj.rect(x=info_x, y=note_y, w=inner_w, h=note_h, style='FD', round_corners=True, corner_radius=pdf_obj.theme['radius'])
        pdf_obj.set_xy(info_x + ELEM_PAD_H, note_y + ELEM_PAD_V)
        pdf_obj.set_font(font_fam, 'I', FONT_SIZE_BODY)
        pdf_obj.set_text_color(*hex_to_rgb(pdf_obj.theme['text_muted']))
        pdf_obj.multi_cell(w=inner_w - (2 * ELEM_PAD_H), h=LINE_H_BODY, text=note, align='L')

    return y_pos + block_h + pdf_obj.theme.get('spacing', 8)

# ==========================================
# 4. PDF GENERATOR CLASS
# ==========================================

class WireframePDF(FPDF):
    def header(self):
        # Read colors and styles from the injected theme dictionary
        self.set_fill_color(*hex_to_rgb(self.theme['page_bg']))
        self.set_draw_color(*hex_to_rgb(self.theme['border']))
        self.set_line_width(LINE_WIDTH)
        self.rect(x=PAGE_MARGIN, y=PAGE_MARGIN, w=PAGE_W - 2*PAGE_MARGIN, h=PAGE_H - 2*PAGE_MARGIN, style='FD', round_corners=True, corner_radius=self.theme['radius'])

    def footer(self):
        self.set_y(-FOOTER_MARGIN_BOTTOM)
        self.set_draw_color(*hex_to_rgb(self.theme['border']))
        self.set_line_width(FOOTER_LINE_W)
        self.line(BANNER_X, self.get_y(), PAGE_W - BANNER_X, self.get_y())
        self.ln(FOOTER_GAP)
        
        font_fam = self.theme.get('font', 'Helvetica')
        self.set_font(font_fam, 'I', FONT_SIZE_FOOTER)
        self.set_text_color(*hex_to_rgb(self.theme['text_muted']))
        
        f_text = getattr(self, 'custom_footer_text', "Medical Report") 
        self.cell(0, FOOTER_LINE_H, f_text, 0, 1, 'C')
        self.cell(0, FOOTER_LINE_H, f'Page {self.page_no()}', 0, 0, 'C')

# ==========================================
# 5. TEST-ONLY PREVIEW GENERATOR
# ==========================================

def create_test_preview_pdf(tests, report_config, theme_config=None):
    """Renders just the test block — no logo, no patient banner, no footer text."""
    if not theme_config:
        theme_config = {
            "page_bg": "#E6F5FF", "banner_bg": "#FFFFFF",
            "inner_box": "#F8FBFF", "border": "#B4D2E6",
            "text_primary": "#003366", "text_muted": "#505050",
            "radius": 5, "spacing": 8, "font": "Helvetica"
        }

    pdf = WireframePDF(format='A4')
    pdf.theme = theme_config
    pdf.custom_footer_text = ""
    font_fam = theme_config.get('font', 'Helvetica')

    CUSTOM_FONTS = ["Roboto", "Montserrat", "Open Sans"]
    if font_fam in CUSTOM_FONTS:
        try:
            pdf.add_font(font_fam, '', f'assets/fonts/{font_fam}-Regular.ttf', uni=True)
            pdf.add_font(font_fam, 'B', f'assets/fonts/{font_fam}-Bold.ttf', uni=True)
            pdf.add_font(font_fam, 'I', f'assets/fonts/{font_fam}-Italic.ttf', uni=True)
        except Exception:
            font_fam = 'Helvetica'
            pdf.theme['font'] = 'Helvetica'

    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    current_y = PAGE_MARGIN + INNER_PADDING

    for item in report_config:
        group_name = item['test']
        group_data = [t for t in tests if t[4] == group_name]
        if not group_data:
            continue

        group_data.sort(key=lambda x: x[0], reverse=True)
        latest = group_data[0]

        test_name = latest[1]
        val = latest[2]
        unit = latest[3]
        config_str = latest[5]
        display_target = latest[7] if latest[7] else 'N/A'

        try:
            config = json.loads(config_str) if config_str else {}
        except json.JSONDecodeError:
            config = {}

        graph_type = config.get("graph_type", "none")
        trend_chart_type = latest[16] if len(latest) > 16 else 'line'
        _tc_raw = latest[17] if len(latest) > 17 else None
        try:
            trend_config_parsed = json.loads(_tc_raw) if _tc_raw else {}
        except (json.JSONDecodeError, TypeError):
            trend_config_parsed = {}

        img_gauge, img_trend = None, None
        display_title = group_name
        display_val = str(val)
        display_unit = unit if unit else ''
        history_data = []
        dynamic_chart_h = 42

        if graph_type == 'none':
            display_target = "N/A"
            img_gauge = render_text(val, unit)
            if trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)
            history_data = [(t[0].split()[0], str(t[2])) for t in group_data]

        elif graph_type == 'gauge':
            img_gauge = render_gauge(val, config, test_name, unit)
            if trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)
            history_data = [(t[0].split()[0], str(t[2])) for t in group_data]

        elif graph_type == 'dot':
            values_dict = {}
            for t in group_data:
                if t[2] is not None and t[1] not in values_dict:
                    try:
                        values_dict[t[1]] = float(t[2])
                    except (ValueError, TypeError):
                        pass
            primary_config = config
            for t in group_data:
                try:
                    t_cfg = json.loads(t[5] or '{}')
                    if t_cfg.get("dots"):
                        primary_config = t_cfg
                        break
                except json.JSONDecodeError:
                    pass
            img_gauge = render_dot(values_dict, primary_config, test_name, unit)
            dots_cfg = primary_config.get("dots", [])
            dot_vals = [str(values_dict.get(d["test_name"], "?")) for d in dots_cfg if d["test_name"] in values_dict]
            display_val = "/".join(dot_vals) if dot_vals else str(val)
            _dot_names = [d["test_name"] for d in dots_cfg if d.get("test_name")]
            if len(_dot_names) >= 2:
                sys_data = sorted([t for t in group_data if t[1] == _dot_names[0]], key=lambda x: x[0], reverse=True)
                dia_data = sorted([t for t in group_data if t[1] == _dot_names[1]], key=lambda x: x[0], reverse=True)
            else:
                sys_data = sorted([t for t in group_data if "Systolic" in t[1]], key=lambda x: x[0], reverse=True)
                dia_data = sorted([t for t in group_data if "Diastolic" in t[1]], key=lambda x: x[0], reverse=True)
            if trend_chart_type == 'bp_trend' and len(sys_data) > 1 and len(dia_data) > 1:
                img_trend = create_bp_trend_chart(sys_data, dia_data, primary_config, trend_config=trend_config_parsed)
            elif trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)
            history_dict = {}
            sys_key = _dot_names[0] if len(_dot_names) >= 1 else None
            dia_key = _dot_names[1] if len(_dot_names) >= 2 else None
            for t in group_data:
                d_key = t[0].split()[0]
                if d_key not in history_dict:
                    history_dict[d_key] = {"sys": "?", "dia": "?"}
                if t[1] == sys_key:
                    history_dict[d_key]["sys"] = t[2]
                elif t[1] == dia_key:
                    history_dict[d_key]["dia"] = t[2]
            history_data = [(d_key, f"{history_dict[d_key]['sys']}/{history_dict[d_key]['dia']}")
                            for d_key in sorted(history_dict.keys(), reverse=True)]

        elif graph_type == 'bar':
            panel_items = []
            for t_name in list(set([t[1] for t in group_data])):
                t_data = sorted([t for t in group_data if t[1] == t_name], key=lambda x: x[0], reverse=True)
                latest_t = t_data[0]
                try:
                    t_config = json.loads(latest_t[5] or '{}') if latest_t[5] else {}
                except json.JSONDecodeError:
                    t_config = {}
                panel_items.append({
                    "name": latest_t[1], "value": latest_t[2], "unit": latest_t[3],
                    "target": latest_t[7] if latest_t[7] else "", "config": t_config
                })
            panel_items.sort(key=lambda x: x["name"])
            img_gauge = render_bars(panel_items)
            display_val = "\n".join([
                f"{item['name'].replace(f' {group_name}', '').replace('Cholesterol', '').strip()}: "
                f"{item['value']} {item['unit']}"
                for item in panel_items
            ])
            display_unit = ""
            display_target = "See Chart"
            dynamic_chart_h = max(42, 20 + (len(panel_items) * 10))
            if trend_chart_type == 'multi_trend':
                unique_dates = list(set([t[0].split()[0] for t in group_data]))
                if len(unique_dates) > 1:
                    img_trend = create_multi_trend_chart(group_data, trend_config=trend_config_parsed)
            elif trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)
            history_dict = {}
            for t in group_data:
                d_key = t[0].split()[0]
                t_clean = t[1].replace(f" {group_name}", "").replace("Cholesterol", "").strip()
                if d_key not in history_dict:
                    history_dict[d_key] = []
                history_dict[d_key].append(f"{t_clean}: {t[2]}")
            history_data = [(d_key, " | ".join(sorted(history_dict[d_key])))
                            for d_key in sorted(history_dict.keys(), reverse=True)]

        history_data = [(t[0], str(t[2])) for t in group_data]

        current_y = draw_test_block(
            pdf_obj=pdf,
            y_pos=current_y,
            title=display_title,
            val=display_val,
            unit=display_unit,
            date=latest[0],
            target=display_target,
            note="Sample result note - reflects how notes appear on the printed report.",
            img_gauge=img_gauge,
            img_trend=img_trend,
            chart_box_h=dynamic_chart_h,
            history=history_data
        )

    return bytes(pdf.output())


# ==========================================
# 6. MAIN REPORT GENERATOR
# ==========================================

def create_custom_report_pdf(patient, tests, report_config, note_overrides, start_d, end_d, practitioner_statement, next_steps, footer_text, creator_name, theme_config=None):
    """Orchestrates data parsing and places it into the wireframe."""
    
    # 1. Provide a default fallback theme if none is passed
    if not theme_config:
        theme_config = {
            "page_bg": "#E6F5FF",
            "banner_bg": "#FFFFFF",
            "inner_box": "#F8FBFF",
            "border": "#B4D2E6",
            "text_primary": "#003366",
            "text_muted": "#505050",
            "radius": 5,
            "font": "Helvetica"
        }

    pdf = WireframePDF(format='A4')
    pdf.theme = theme_config # INJECT THE THEME!
    pdf.custom_footer_text = footer_text 
    font_fam = theme_config.get('font', 'Helvetica')
    
    # ==========================================
    # --- NEW: CUSTOM FONT REGISTRATION ---
    # ==========================================
    CUSTOM_FONTS = ["Roboto", "Montserrat", "Open Sans"]
    if font_fam in CUSTOM_FONTS:
        try:
            # Tell FPDF where the .ttf files live
            pdf.add_font(font_fam, '', f'assets/fonts/{font_fam}-Regular.ttf', uni=True)
            pdf.add_font(font_fam, 'B', f'assets/fonts/{font_fam}-Bold.ttf', uni=True)
            pdf.add_font(font_fam, 'I', f'assets/fonts/{font_fam}-Italic.ttf', uni=True)
        except Exception as e:
            # If the admin selects Roboto but forgot to download the .ttf file, safely fallback!
            print(f"Warning: Could not load custom font {font_fam}. Falling back to Helvetica. Error: {e}")
            font_fam = 'Helvetica'
            pdf.theme['font'] = 'Helvetica' # Update the theme object so the rest of the script knows
            
    # ==========================================

    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # 1. HEADER & LOGO
    current_y = PAGE_MARGIN + INNER_PADDING
    logo_x = BANNER_X if LOGO_ALIGN.upper() == 'LEFT' else PAGE_W - PAGE_MARGIN - INNER_PADDING - LOGO_W
    logo_path = os.path.join("assets", "logo.png")
    
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=logo_x, y=current_y, w=LOGO_W, h=LOGO_H)
    else:
        # Fallback Logo Box using Theme Colors
        pdf.set_fill_color(*hex_to_rgb(theme_config['inner_box']))
        pdf.set_draw_color(*hex_to_rgb(theme_config['border']))
        pdf.rect(x=logo_x, y=current_y, w=LOGO_W, h=LOGO_H, style='FD', round_corners=True, corner_radius=theme_config['radius'])

    # ==========================================
    # 2. PATIENT BANNER
    # ==========================================
    current_y += LOGO_H + theme_config.get('spacing', 8)
    
    # --- FIXED: Expanded the box height to fit a 3rd line of text ---
    banner_h = ELEM_PAD_V + LINE_H_H1 + TITLE_BODY_GAP + LINE_H_BODY + TITLE_BODY_GAP + LINE_H_BODY + ELEM_PAD_V
    
    pdf.set_fill_color(*hex_to_rgb(theme_config['banner_bg']))
    pdf.set_draw_color(*hex_to_rgb(theme_config['border']))
    pdf.rect(x=BANNER_X, y=current_y, w=BANNER_W, h=banner_h, style='FD', round_corners=True, corner_radius=theme_config['radius'])
    
    # Line 1: Name
    pdf.set_xy(BANNER_X + ELEM_PAD_H, current_y + ELEM_PAD_V)
    pdf.set_font(font_fam, 'B', FONT_SIZE_H1)
    pdf.set_text_color(*hex_to_rgb(theme_config['text_primary']))
    
    f_name = patient.get('first_name', patient.get('First Name', ''))
    l_name = patient.get('last_name', patient.get('Last Name', ''))
    pdf.cell(w=BANNER_W - (2*ELEM_PAD_H), h=LINE_H_H1, text=f"Health Report: {f_name} {l_name}", align='L')
    
    # Line 2: Patient Demographics
    pdf.set_xy(BANNER_X + ELEM_PAD_H, current_y + ELEM_PAD_V + LINE_H_H1 + TITLE_BODY_GAP)
    pdf.set_font(font_fam, '', FONT_SIZE_BODY)
    pdf.set_text_color(*hex_to_rgb(theme_config['text_muted']))
    
    p_dob = patient.get('date_of_birth', patient.get('dob', patient.get('DOB', '')))
    p_id = patient.get('patient_id', patient.get('Patient ID', patient.get('id', 'N/A')))
    
    try:
        if isinstance(p_dob, str):
            dob_obj = datetime.strptime(p_dob, '%Y-%m-%d').date()
        else:
            dob_obj = p_dob 
        age = (datetime.now().date() - dob_obj).days // 365
    except Exception:
        age = "N/A"
        
    patient_info = f"DOB: {p_dob}  |  Age: {age} yrs  |  Patient ID: {p_id}"
    pdf.cell(w=BANNER_W - (2*ELEM_PAD_H), h=LINE_H_BODY, text=patient_info, align='L')

    # --- NEW: Line 3: Report Metadata (Creator & Date) ---
    y_meta = current_y + ELEM_PAD_V + LINE_H_H1 + TITLE_BODY_GAP + LINE_H_BODY + TITLE_BODY_GAP
    pdf.set_xy(BANNER_X + ELEM_PAD_H, y_meta)
    
    # Give it a slightly bolder font or distinct look if you want, but standard body text keeps it clean
    report_meta = f"Generated by: {creator_name}  |  Date: {datetime.now().strftime('%d %b %Y, %H:%M')}"
    pdf.cell(w=BANNER_W - (2*ELEM_PAD_H), h=LINE_H_BODY, text=report_meta, align='L')

    current_y += banner_h + theme_config.get('spacing', 8)

    # 3. PRACTITIONER STATEMENT 
    if practitioner_statement:
        current_y = draw_dynamic_text_block(pdf, current_y, "Practitioner's Statement", practitioner_statement)
    # 4. DYNAMIC TEST ROUTER
    for item in report_config:
        group_name = item['test'] 
        
        group_data = [t for t in tests if t[4] == group_name]
        if not group_data: continue 

        group_data.sort(key=lambda x: x[0], reverse=True)
        latest = group_data[0] 
        
        test_name = latest[1]
        val = latest[2]
        unit = latest[3]
        config_str = latest[5]
        display_target = latest[7] if latest[7] else 'N/A'

        try:
            config = json.loads(config_str) if config_str else {}
        except json.JSONDecodeError:
            config = {}

        graph_type = config.get("graph_type", "none")
        trend_chart_type = latest[16] if len(latest) > 16 else 'line'
        _tc_raw = latest[17] if len(latest) > 17 else None
        try:
            trend_config_parsed = json.loads(_tc_raw) if _tc_raw else {}
        except (json.JSONDecodeError, TypeError):
            trend_config_parsed = {}

        img_gauge, img_trend = None, None
        display_title = group_name
        display_val = str(val)
        display_unit = unit if unit else ''
        history_data = []

        # Standard Wireframe Height
        dynamic_chart_h = 42

        # --- ROUTING ENGINE (reads graph_type from chart_config JSON) ---
        if graph_type == 'none':
            display_target = "N/A"
            img_gauge = render_text(val, unit)

            if trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)

            history_data = [(t[0].split()[0], str(t[2])) for t in group_data]

        elif graph_type == 'gauge':
            img_gauge = render_gauge(val, config, test_name, unit)

            if trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)

            history_data = [(t[0].split()[0], str(t[2])) for t in group_data]

        elif graph_type == 'dot':
            # Collect all latest values for this group (one per test_name)
            values_dict = {}
            for t in group_data:
                if t[2] is not None and t[1] not in values_dict:
                    try:
                        values_dict[t[1]] = float(t[2])
                    except (ValueError, TypeError):
                        pass

            # Use the config that carries the "dots" array (primary test)
            primary_config = config
            for t in group_data:
                try:
                    t_cfg = json.loads(t[5] or '{}')
                    if t_cfg.get("dots"):
                        primary_config = t_cfg
                        break
                except json.JSONDecodeError:
                    pass

            img_gauge = render_dot(values_dict, primary_config, test_name, unit)

            # Build display value from dots array order
            dots_cfg = primary_config.get("dots", [])
            dot_vals = [str(values_dict.get(d["test_name"], "?")) for d in dots_cfg
                        if d["test_name"] in values_dict]
            display_val = "/".join(dot_vals) if dot_vals else str(val)

            # Trend — split by actual dot names from config, falling back to keyword matching
            _dot_names = [d["test_name"] for d in dots_cfg if d.get("test_name")]
            if len(_dot_names) >= 2:
                sys_data = sorted([t for t in group_data if t[1] == _dot_names[0]],
                                   key=lambda x: x[0], reverse=True)
                dia_data = sorted([t for t in group_data if t[1] == _dot_names[1]],
                                   key=lambda x: x[0], reverse=True)
            else:
                sys_data = sorted([t for t in group_data if "Systolic" in t[1]],
                                   key=lambda x: x[0], reverse=True)
                dia_data = sorted([t for t in group_data if "Diastolic" in t[1]],
                                   key=lambda x: x[0], reverse=True)
            if trend_chart_type == 'bp_trend' and len(sys_data) > 1 and len(dia_data) > 1:
                img_trend = create_bp_trend_chart(sys_data, dia_data, primary_config, trend_config=trend_config_parsed)
            elif trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)

            # Stitch history: first/second dot per date
            history_dict = {}
            sys_key = _dot_names[0] if len(_dot_names) >= 1 else next((d["test_name"] for d in dots_cfg if "Sys" in d.get("test_name", "")), None)
            dia_key = _dot_names[1] if len(_dot_names) >= 2 else next((d["test_name"] for d in dots_cfg if "Dia" in d.get("test_name", "")), None)
            for t in group_data:
                d_key = t[0].split()[0]
                if d_key not in history_dict:
                    history_dict[d_key] = {"sys": "?", "dia": "?"}
                if t[1] == sys_key:
                    history_dict[d_key]["sys"] = t[2]
                elif t[1] == dia_key:
                    history_dict[d_key]["dia"] = t[2]
            history_data = [(d_key, f"{history_dict[d_key]['sys']}/{history_dict[d_key]['dia']}")
                            for d_key in sorted(history_dict.keys(), reverse=True)]

        elif graph_type == 'bar':
            panel_items = []
            for t_name in list(set([t[1] for t in group_data])):
                t_data = sorted([t for t in group_data if t[1] == t_name],
                                 key=lambda x: x[0], reverse=True)
                latest_t = t_data[0]
                try:
                    t_config = json.loads(latest_t[5] or '{}') if latest_t[5] else {}
                except json.JSONDecodeError:
                    t_config = {}
                panel_items.append({
                    "name": latest_t[1], "value": latest_t[2], "unit": latest_t[3],
                    "target": latest_t[7] if latest_t[7] else "", "config": t_config
                })

            panel_items.sort(key=lambda x: x["name"])
            img_gauge = render_bars(panel_items)

            display_val = "\n".join([
                f"{item['name'].replace(f' {group_name}', '').replace('Cholesterol', '').strip()}: "
                f"{item['value']} {item['unit']}"
                for item in panel_items
            ])
            display_unit = ""
            display_target = "See Chart"
            dynamic_chart_h = max(42, 20 + (len(panel_items) * 10))

            if trend_chart_type == 'multi_trend':
                unique_dates = list(set([t[0].split()[0] for t in group_data]))
                if len(unique_dates) > 1:
                    img_trend = create_multi_trend_chart(group_data, trend_config=trend_config_parsed)
            elif trend_chart_type == 'line' and len(group_data) > 1:
                img_trend = create_trend_chart(group_data, test_name, unit, trend_config=trend_config_parsed)

            # Stitch panel history per date
            history_dict = {}
            for t in group_data:
                d_key = t[0].split()[0]
                t_clean = t[1].replace(f" {group_name}", "").replace("Cholesterol", "").strip()
                if d_key not in history_dict:
                    history_dict[d_key] = []
                history_dict[d_key].append(f"{t_clean}: {t[2]}")
            history_data = [
                (d_key, " | ".join(sorted(history_dict[d_key])))
                for d_key in sorted(history_dict.keys(), reverse=True)
            ]

        # --- SMART GRANULAR NOTE AGGREGATION ---

        # ==========================================
        # --- SMART GRANULAR NOTE AGGREGATION ---
        # ==========================================
        latest_date = group_data[0][0]
        latest_records = [t for t in group_data if t[0] == latest_date]
        latest_records.sort(key=lambda x: x[1])
        
        final_notes_list = []
        
        for record in latest_records:
            t_name = record[1]
            original_note = record[6].strip() if record[6] else ""
            
            current_note = original_note
            if note_overrides and t_name in note_overrides:
                user_text = note_overrides[t_name]
                if user_text == "EXCLUDE":
                    current_note = ""
                elif user_text:
                    current_note = user_text
            
            if current_note:
                if group_name != t_name:
                    clean_name = t_name.replace(f" {group_name}", "") 
                    final_notes_list.append(f"{clean_name}: {current_note}")
                else:
                    final_notes_list.append(current_note)
                    
        final_note = "\n".join(final_notes_list)
        
        # --- Extract the sorted history mapping (Date, Value) ---
        history_data = [(t[0], str(t[2])) for t in group_data]

        # --- DRAW THE COMPONENT ---
        current_y = draw_test_block(
            pdf_obj=pdf, 
            y_pos=current_y, 
            title=display_title, 
            val=display_val, 
            unit=display_unit, 
            date=latest[0], 
            target=display_target, 
            note=final_note, 
            img_gauge=img_gauge, 
            img_trend=img_trend,
            chart_box_h=dynamic_chart_h,
            history=history_data 
        )

    # 5. NEXT STEPS
    if next_steps:
        current_y = draw_dynamic_text_block(pdf, current_y, "Next Steps & Clinical Recommendations", next_steps)

    return bytes(pdf.output())