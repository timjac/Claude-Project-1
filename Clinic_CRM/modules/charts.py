import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Wedge
import matplotlib.dates as mdates
import io
import math
from datetime import datetime, timedelta

# ==========================================
# 1. GLOBAL DESIGN SYSTEM
# ==========================================
COLOR_PRIMARY  = '#003366'  # Navy
COLOR_TEXT     = '#323232'  # Dark Grey
COLOR_SAFE_BG  = '#d4edda'  # Soft Green
COLOR_ALERT_BG = '#ffcccb'  # Soft Red
COLOR_WARN_BG  = '#ffe4b5'  # Orange/Warning
COLOR_BLUE_BG  = '#add8e6'  # Light Blue
COLOR_ALERT    = '#dc3545'  # Strong Red
COLOR_AXIS     = '#e0e0e0'  # Unified grid lines

TICK_SIZE = 9

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['text.color'] = COLOR_TEXT
plt.rcParams['axes.labelcolor'] = COLOR_TEXT
plt.rcParams['xtick.color'] = COLOR_TEXT
plt.rcParams['ytick.color'] = COLOR_TEXT
plt.rcParams['font.size'] = TICK_SIZE


def _export(fig, ax, is_trend=False, target_height=1.65):
    """The master formatting and export engine."""
    fig.set_size_inches(3.92, target_height)

    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)

    ax.tick_params(axis='both', which='both', length=0)

    if is_trend:
        ax.grid(axis='y', linestyle='-', alpha=0.5, color=COLOR_AXIS)
        ax.grid(axis='x', visible=False)
    else:
        ax.grid(False)

    plt.tight_layout(pad=1.5)

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=200, transparent=True)
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer


# ==========================================
# 2. HELPERS
# ==========================================

def _darken_color(hex_color, factor=0.65):
    """Darken a hex color by scaling each RGB component."""
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f'#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}'


def _find_zone_color(value, zones):
    """Return the color of the zone the value falls in, skipping transparent. Grey if none match."""
    for zone in zones:
        color = zone.get('color', '#D4EDDA')
        if color != 'transparent' and float(zone['from']) <= value <= float(zone['to']):
            return color
    return '#888888'


def _parse_target(target_str):
    """Parse '> X' or '< X' target string. Returns (operator, float_value) or (None, None)."""
    if not target_str:
        return None, None
    t = str(target_str).strip()
    try:
        if t.startswith('>='):
            return '>=', float(t[2:].strip())
        elif t.startswith('<='):
            return '<=', float(t[2:].strip())
        elif t.startswith('>'):
            return '>', float(t[1:].strip())
        elif t.startswith('<'):
            return '<', float(t[1:].strip())
    except (ValueError, TypeError):
        pass
    return None, None


def _is_alert_value(value, target_str):
    """True when the value fails to meet its target (alert bar colour should apply)."""
    op, thresh = _parse_target(target_str)
    if op is None:
        return False
    v = float(value)
    if op == '>':  return v <= thresh
    if op == '>=': return v < thresh
    if op == '<':  return v >= thresh
    if op == '<=': return v > thresh
    return False


# ==========================================
# 3. NEW CHART GENERATORS
# ==========================================

def render_gauge(value, config, test_name="", unit=""):
    """Renders a gauge. gauge_style='curved' → half-donut; 'straight' → segmented bar."""
    import numpy as np

    try:
        val = float(value)
    except (ValueError, TypeError):
        return None

    zones = config.get("zones", [])
    gauge_style = config.get("gauge_style", "curved")
    axis_min = float(config.get("axis_min", 0))
    axis_max = float(config.get("axis_max", 100))

    # Elastic axis expansion
    if val < axis_min:
        padding = (axis_max - val) * 0.1
        axis_min = val - padding
        if float(config.get("axis_min", 0)) >= 0:
            axis_min = max(axis_min, 0.0)
    elif val > axis_max:
        padding = (val - axis_min) * 0.1
        axis_max = val + padding

    zone_color = _find_zone_color(val, zones)
    indicator_color = _darken_color(zone_color)

    def fmt(v):
        return str(int(v)) if float(v).is_integer() else f"{v:.1f}"

    show_labels = config.get("show_axis_labels", True)

    if gauge_style == "straight":
        fig, ax = plt.subplots()
        total_range = axis_max - axis_min

        for zone in zones:
            z_from = max(float(zone['from']), axis_min)
            z_to = min(float(zone['to']), axis_max)
            color = zone.get('color', '#D4EDDA')
            if z_to > z_from and color != 'transparent':
                ax.barh(0, z_to - z_from, left=z_from, color=color, height=0.4, zorder=1)

        # Indicator line
        ax.plot([val, val], [-0.35, 0.35], color=indicator_color, lw=4, zorder=5)

        if show_labels:
            ax.text(axis_min, -0.55, fmt(axis_min), ha='left', va='top', fontsize=9, color='#555555')
            ax.text(axis_max, -0.55, fmt(axis_max), ha='right', va='top', fontsize=9, color='#555555')

        for zone in zones:
            z_mid = (float(zone['from']) + float(zone['to'])) / 2
            if axis_min <= z_mid <= axis_max and zone.get('label'):
                ax.text(z_mid, 0.52, zone['label'], ha='center', va='bottom', fontsize=7, color='#555555')

        pad = total_range * 0.02
        ax.set_xlim(axis_min - pad, axis_max + pad)
        ax.set_ylim(-1, 1)
        ax.set_yticks([])
        ax.set_xticks([])

        return _export(fig, ax)

    else:  # curved half-donut
        fig, ax = plt.subplots()
        ax.axis('equal')
        ax.axis('off')

        def val_to_angle(v):
            v = max(axis_min, min(axis_max, v))
            fraction = (v - axis_min) / (axis_max - axis_min) if axis_max > axis_min else 0
            return 180 - (fraction * 180)

        # Grey background arc
        bg_arc = patches.Wedge((0, 0), 1, 0, 180, width=0.3, color='#E0E0E0', zorder=1)
        ax.add_patch(bg_arc)

        # Coloured zone arcs
        for zone in zones:
            z_from = max(float(zone['from']), axis_min)
            z_to = min(float(zone['to']), axis_max)
            color = zone.get('color', '#D4EDDA')
            if z_to > z_from and color != 'transparent':
                angle_start = val_to_angle(z_to)
                angle_end = val_to_angle(z_from)
                arc = patches.Wedge((0, 0), 1, angle_start, angle_end,
                                    width=0.3, color=color, zorder=2)
                ax.add_patch(arc)

        # Needle
        needle_angle = val_to_angle(val)
        needle_rad = np.deg2rad(needle_angle)
        x = 0.8 * np.cos(needle_rad)
        y = 0.8 * np.sin(needle_rad)

        ax.annotate('', xy=(x, y), xytext=(0, 0),
                    arrowprops=dict(arrowstyle='wedge,tail_width=0.2',
                                   color=indicator_color, shrinkA=0, shrinkB=0), zorder=3)
        ax.add_patch(patches.Circle((0, 0), 0.15, color=indicator_color, zorder=4))

        if show_labels:
            ax.text(-0.95, -0.15, fmt(axis_min), ha='center', va='top', fontsize=9, color='#555555')
            ax.text(0.95, -0.15, fmt(axis_max), ha='center', va='top', fontsize=9, color='#555555')

        ax.set_xlim(-1.1, 1.1)
        ax.set_ylim(-0.3, 1.1)

        return _export(fig, ax)


def render_dot(values_dict, config, test_name="", unit=""):
    """Renders a dumbbell/dot chart. values_dict = {test_name: value, ...}"""
    zones = config.get("zones", [])
    dots_config = config.get("dots", [])
    axis_min = float(config.get("axis_min", 0))
    axis_max = float(config.get("axis_max", 200))

    # Resolve ordered dot positions
    dot_positions = []
    for dot_def in dots_config:
        t_name = dot_def["test_name"]
        if t_name in values_dict and values_dict[t_name] is not None:
            try:
                dot_positions.append((float(values_dict[t_name]), dot_def))
            except (ValueError, TypeError):
                pass

    if not dot_positions:
        return None

    all_vals = [p[0] for p in dot_positions]
    min_val, max_val = min(all_vals), max(all_vals)

    # Elastic axis expansion
    if min_val < axis_min:
        axis_min = min_val - (axis_max - min_val) * 0.1
        if float(config.get("axis_min", 0)) >= 0:
            axis_min = max(axis_min, 0.0)
    if max_val > axis_max:
        axis_max = max_val + (max_val - axis_min) * 0.1

    fig, ax = plt.subplots()

    # Baseline
    ax.plot([axis_min, axis_max], [0, 0], color='#B0BEC5', linewidth=2, zorder=1)

    # Zone background bands
    for zone in zones:
        z_from = max(float(zone['from']), axis_min)
        z_to = min(float(zone['to']), axis_max)
        color = zone.get('color', '#D4EDDA')
        if z_to > z_from and color != 'transparent':
            ax.add_patch(patches.Rectangle(
                (z_from, -0.4), z_to - z_from, 0.8,
                color=color, alpha=0.5, zorder=0))

    # Connecting line between outermost dots
    if len(dot_positions) >= 2:
        x_sorted = sorted(all_vals)
        ax.plot([x_sorted[0], x_sorted[-1]], [0, 0],
                color=COLOR_PRIMARY, linewidth=4, zorder=2)

    def fmt(v):
        return str(int(v)) if float(v).is_integer() else f"{v:.1f}"

    for pos_val, dot_def in dot_positions:
        fill = dot_def.get("fill_color", COLOR_PRIMARY)
        stroke = dot_def.get("stroke_color", COLOR_PRIMARY)
        label = dot_def.get("label", dot_def.get("test_name", ""))

        ax.scatter([pos_val], [0], color=fill, edgecolors=stroke,
                   s=120, linewidths=2, zorder=3)
        ax.text(pos_val, -0.55, fmt(pos_val), ha='center', va='top',
                fontweight='bold', color=stroke)
        ax.text(pos_val, 0.45, label, ha='center', va='bottom', fontsize=8)

    ax.set_yticks([])
    ax.set_xlim(axis_min, axis_max)
    ax.set_ylim(-1.0, 1.0)

    return _export(fig, ax)


def render_bars(panel_items, config=None):
    """Renders a horizontal bar panel. Each item carries its own config with zones."""
    if not panel_items:
        return None

    def fmt(v):
        return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip('0').rstrip('.')

    # Determine axis end from the maximum zone 'to' across all items.
    # This ensures zones are never clipped, regardless of current values.
    max_zone_to  = max(
        (float(item.get("config", {}).get("zones", [{}])[-1].get("to", 0))
         for item in panel_items),
        default=0.0
    )
    max_val_seen = max(
        (float(item.get("value", 0)) for item in panel_items),
        default=0.0
    )
    axis_end = max(max_zone_to, max_val_seen)
    padding  = axis_end * 0.15 + 0.5

    fig, ax = plt.subplots()

    for i, item in enumerate(panel_items):
        try:
            val = float(item["value"])
        except (ValueError, TypeError):
            val = 0.0

        item_config = item.get("config", {})
        zones = item_config.get("zones", [])
        bar_color       = item_config.get("bar_color",       COLOR_PRIMARY)
        bar_alert_color = item_config.get("bar_alert_color", COLOR_ALERT)

        # Zone background bands (extend to full axis width)
        for zone in zones:
            z_from = float(zone['from'])
            z_to   = float(zone['to'])
            color  = zone.get('color', '#D4EDDA')
            if z_to > z_from and color != 'transparent':
                ax.add_patch(patches.Rectangle(
                    (z_from, i - 0.4), z_to - z_from, 0.8,
                    color=color, zorder=1))

        # Alert when the value misses its target (> or < in target string)
        is_alert = _is_alert_value(val, item.get('target', ''))
        color    = bar_alert_color if is_alert else bar_color

        ax.barh(i, val, color=color, height=0.4, zorder=3)
        ax.text(val + padding * 0.08, i, fmt(val), va='center',
                fontweight='bold', color=color, zorder=4)

    ax.set_yticks(range(len(panel_items)))
    ax.set_yticklabels([f"{item['name']} ({item.get('target', '')})"
                        for item in panel_items])
    ax.set_xlim(0, axis_end + padding)
    ax.set_xticks([])
    ax.invert_yaxis()

    dynamic_h = max(1.65, 0.8 + (len(panel_items) * 0.4))
    return _export(fig, ax, target_height=dynamic_h)


def render_text(value, unit):
    """Simple large-text display for non-charted values."""
    fig, ax = plt.subplots(figsize=(4, 2))
    ax.axis('off')

    try:
        val_float = float(value)
        display_val = str(int(val_float)) if val_float.is_integer() else f"{val_float:.1f}"
    except (ValueError, TypeError):
        display_val = str(value)

    ax.text(0.5, 0.6, display_val, ha='center', va='center',
            fontsize=46, fontweight='bold', color='#003366')

    unit_text = unit if unit and unit != "N/A" else ""
    if unit_text:
        ax.text(0.5, 0.2, unit_text, ha='center', va='center',
                fontsize=14, color='#757575', fontweight='bold')

    return _export(fig, ax)


# ==========================================
# 4. TREND CHARTS (Unchanged)
# ==========================================

def create_trend_chart(history, title, unit="", trend_config=None):
    """Standard Line Trend Chart"""
    tc = trend_config or {}
    line_colour = tc.get("line_colour", COLOR_PRIMARY)
    line_style   = "--" if tc.get("line_style", "solid") == "dashed" else "-"
    show_markers = tc.get("show_markers", False)
    marker = 'o' if show_markers else None

    dates, values = [], []
    history_sorted = sorted(history, key=lambda x: datetime.strptime(x[0], "%Y-%m-%d"))

    for h in history_sorted:
        dates.append(datetime.strptime(h[0], "%Y-%m-%d"))
        try:
            values.append(float(h[2]))
        except (ValueError, TypeError):
            values.append(0.0)

    fig, ax = plt.subplots()
    ax.plot(dates, values, marker=marker, linestyle=line_style, color=line_colour, lw=2, zorder=3)

    if values:
        bottom_val = min(values) * 0.9 if min(values) > 0 else 0
        ax.fill_between(dates, values, bottom_val, color=line_colour, alpha=0.1, zorder=2)
        ax.set_ylim(bottom=bottom_val)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.tick_params(axis='both', which='both', labelbottom=False, labelleft=False)

    if dates:
        pad = timedelta(days=5)
        ax.set_xlim(min(dates) - pad, max(dates) + pad)

    return _export(fig, ax, is_trend=True)


def create_bp_trend_chart(sys_history, dia_history, config, trend_config=None):
    """BP River Trend Chart (two separate history arrays)"""
    if not sys_history or not dia_history:
        return None

    tc = trend_config or {}
    line_style   = "--" if tc.get("line_style", "solid") == "dashed" else "-"
    show_markers = tc.get("show_markers", False)
    marker = 'o' if show_markers else None
    markersize = 5 if show_markers else 0

    sys_dict = {h[0].split()[0]: float(h[2]) for h in sys_history if h[2]}
    dia_dict = {h[0].split()[0]: float(h[2]) for h in dia_history if h[2]}

    common_dates = sorted(list(set(sys_dict.keys()) & set(dia_dict.keys())))
    if len(common_dates) < 2:
        return None

    dates = [datetime.strptime(d, "%Y-%m-%d") for d in common_dates]
    systolics = [sys_dict[d] for d in common_dates]
    diastolics = [dia_dict[d] for d in common_dates]

    fig, ax = plt.subplots()
    ax.axhspan(60, 120, color=COLOR_SAFE_BG, alpha=0.4, linewidth=0, zorder=0)
    ax.plot(dates, systolics, marker=marker, markersize=markersize, linestyle=line_style, color=COLOR_PRIMARY, linewidth=2, zorder=3)
    ax.plot(dates, diastolics, marker=marker, markersize=markersize, linestyle=line_style, color=COLOR_PRIMARY, linewidth=2, zorder=3)
    ax.fill_between(dates, diastolics, systolics, color=COLOR_PRIMARY, alpha=0.1, zorder=2)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.tick_params(axis='both', which='both', labelbottom=False, labelleft=False)

    if dates:
        pad = timedelta(days=5)
        ax.set_xlim(min(dates) - pad, max(dates) + pad)

    return _export(fig, ax, is_trend=True)


def create_multi_trend_chart(group_data, trend_config=None):
    """Multi-line trend chart for panels like Cholesterol"""
    if not group_data:
        return None

    tc = trend_config or {}
    line_style   = "--" if tc.get("line_style", "solid") == "dashed" else "-"
    show_markers = tc.get("show_markers", False)
    marker = 'o' if show_markers else None
    markersize = 5 if show_markers else 0

    raw_dates = sorted(list(set([t[0].split()[0] for t in group_data])))
    test_names = sorted(list(set([t[1] for t in group_data])))

    if len(raw_dates) < 2:
        return None

    dates = [datetime.strptime(d, "%Y-%m-%d") for d in raw_dates]
    fig, ax = plt.subplots()

    colors = ['#003366', '#2E8B57', '#DC143C', '#FF8C00', '#8A2BE2']

    for idx, t_name in enumerate(test_names):
        t_history = [t for t in group_data if t[1] == t_name]
        val_dict = {t[0].split()[0]: float(t[2]) for t in t_history if t[2]}

        t_dates, t_vals = [], []
        for d in raw_dates:
            if d in val_dict:
                t_dates.append(datetime.strptime(d, "%Y-%m-%d"))
                t_vals.append(val_dict[d])

        if t_dates:
            label_name = t_name.replace("Cholesterol", "").replace("Panel", "").strip()
            if not label_name:
                label_name = t_name
            ax.plot(t_dates, t_vals, marker=marker, markersize=markersize, linestyle=line_style,
                    linewidth=2, label=label_name, color=colors[idx % len(colors)])

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.tick_params(axis='both', which='both', labelbottom=False, labelleft=False)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3, frameon=False, fontsize=8)

    if dates:
        pad = timedelta(days=8)
        ax.set_xlim(min(dates) - pad, max(dates) + pad)

    return _export(fig, ax, is_trend=True)
