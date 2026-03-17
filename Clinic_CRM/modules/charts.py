import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Wedge
import matplotlib.dates as mdates
import io
import re
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

# Apply strict Matplotlib global formatting
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['text.color'] = COLOR_TEXT
plt.rcParams['axes.labelcolor'] = COLOR_TEXT
plt.rcParams['xtick.color'] = COLOR_TEXT
plt.rcParams['ytick.color'] = COLOR_TEXT
plt.rcParams['font.size'] = TICK_SIZE

# --- Update the _export function ---
def _export(fig, ax, is_trend=False, target_height=1.65):
    """The master formatting and export engine."""
    fig.set_size_inches(3.92, target_height)
    
    # Strip borders
    for spine in ['top', 'right', 'left', 'bottom']: 
        ax.spines[spine].set_visible(False)
    
    ax.tick_params(axis='both', which='both', length=0)
    
    if is_trend:
        ax.grid(axis='y', linestyle='-', alpha=0.5, color=COLOR_AXIS)
        ax.grid(axis='x', visible=False)
    else:
        ax.grid(False)
        
    # --- INCREASE PADDING HERE ---
    # Changed from 0.2 to 1.5 for a wider, comfortable transparent margin
    plt.tight_layout(pad=1.5) 
    
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=200, transparent=True)
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer

# ==========================================
# 2. CHART GENERATORS (Pure Matplotlib)
# ==========================================

def create_gauge_chart(value, config, test_name="", unit=""):
    """Standard half-donut gauge chart with dynamic safe zones and outlier expansion."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import numpy as np
    
    try:
        val = float(value)
    except ValueError:
        return None

    # 1. Extract base config
    axis_min = float(config.get("axis_min", 0))
    axis_max = float(config.get("axis_max", 100))
    safe_min = float(config.get("safe_min", 20))
    safe_max = float(config.get("safe_max", 80))

    # 2. Dynamic Outlier Expansion (The Elastic Magic)
    if val < axis_min:
        # Push the left edge out and add 10% padding so the needle isn't perfectly flat
        padding = (axis_max - val) * 0.1
        axis_min = val - padding
    elif val > axis_max:
        # Push the right edge out and add 10% padding
        padding = (val - axis_min) * 0.1
        axis_max = val + padding

    # Prevent absolute zero crossing if the original min was >= 0 (e.g. Glucose can't be negative)
    if axis_min < 0 and float(config.get("axis_min", 0)) >= 0:
        axis_min = 0.0

    fig, ax = plt.subplots()
    ax.axis('equal')
    ax.axis('off')

    bg_arc = patches.Wedge((0, 0), 1, 0, 180, width=0.3, color='#E0E0E0', zorder=1)
    ax.add_patch(bg_arc)

    def val_to_angle(v):
        v = max(axis_min, min(axis_max, v)) # Safety clamp to the new dynamic bounds
        fraction = (v - axis_min) / (axis_max - axis_min) if axis_max > axis_min else 0
        return 180 - (fraction * 180)

    angle_safe_min = val_to_angle(safe_min)
    angle_safe_max = val_to_angle(safe_max)

    safe_arc = patches.Wedge((0, 0), 1, angle_safe_max, angle_safe_min, width=0.3, color='#2E8B57', zorder=2)
    ax.add_patch(safe_arc)

    needle_angle = val_to_angle(val)
    needle_rad = np.deg2rad(needle_angle)
    
    x = 0.8 * np.cos(needle_rad)
    y = 0.8 * np.sin(needle_rad)
    
    needle_color = '#DC143C' if (val < safe_min or val > safe_max) else '#003366'
    
    ax.annotate('', xy=(x, y), xytext=(0, 0),
                arrowprops=dict(arrowstyle='wedge,tail_width=0.2', color=needle_color, shrinkA=0, shrinkB=0), zorder=3)

    center_circle = patches.Circle((0, 0), 0.15, color=needle_color, zorder=4)
    ax.add_patch(center_circle)

    def fmt(v): return str(int(v)) if float(v).is_integer() else f"{v:.1f}"
    ax.text(-0.95, -0.15, fmt(axis_min), ha='center', va='top', fontsize=9, color='#555555')
    ax.text(0.95, -0.15, fmt(axis_max), ha='center', va='top', fontsize=9, color='#555555')

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-0.3, 1.1)

    return _export(fig, ax)


def create_bmi_chart(value_str, config):
    """2. Segmented Bullet Chart for BMI (JSON Driven)"""
    try: val = float(value_str)
    except: val = 0.0

    fig, ax = plt.subplots()
    
    axis_min = config.get("axis_min", 10.0)
    axis_max = config.get("axis_max", 40.0)
    
    # Map text colors from JSON to our Python color variables
    color_map = {
        "blue": COLOR_BLUE_BG,
        "green": COLOR_SAFE_BG,
        "warning": COLOR_WARN_BG,
        "alert": COLOR_ALERT_BG
    }
    
    zones = config.get("zones", [])
    
    # Draw background segments dynamically based on the JSON payload
    current_left = axis_min
    for zone in zones:
        limit = zone.get("limit", current_left)
        color_key = zone.get("color", "green")
        fill_color = color_map.get(color_key, COLOR_SAFE_BG)
        
        width = limit - current_left
        if width > 0:
            ax.barh(0, width, left=current_left, color=fill_color, height=0.4)
            current_left = limit
    
    # Indicator Line
    ax.plot([val, val], [-0.4, 0.4], color=COLOR_PRIMARY, lw=4, zorder=5)
    
    ax.set_xlim(axis_min, axis_max)
    ax.set_ylim(-1, 1)
    ax.set_yticks([])
    
    return _export(fig, ax)


def create_multi_bar_panel(panel_items):
    """Generic Horizontal Bar Panel (100% JSON & Data Driven)"""
    if not panel_items: return None
    
    fig, ax = plt.subplots()
    labels, values, colors = [], [], []
    max_val_seen = 0.0
    
    # Loop through however many tests are in this panel (3, 5, 10, etc.)
    for i, item in enumerate(panel_items):
        try: val = float(item["value"])
        except: val = 0.0
        max_val_seen = max(max_val_seen, val)
        
        # Read the JSON config for this specific sub-test
        config = item.get("config", {})
        safe_min = config.get("safe_min", 0.0)
        safe_max = config.get("safe_max", val * 2 if val > 0 else 10.0)
        
        # Draw the safe zone background (the pale green box)
        width = safe_max - safe_min
        if width > 0:
            ax.add_patch(patches.Rectangle((safe_min, i - 0.4), width, 0.8, color=COLOR_SAFE_BG, zorder=1))
        
        # Color the bar red if it breaks the boundaries
        color = COLOR_ALERT if (val < safe_min or val > safe_max) else COLOR_PRIMARY
            
        labels.append(f"{item['name']} ({item['target']})")
        values.append(val)
        colors.append(color)
        
        # Print the exact number next to the bar
        ax.text(val + 0.1, i, str(val), va='center', fontweight='bold', color=color, zorder=4)
        
    # Draw the actual horizontal bars
    ax.barh(range(len(panel_items)), values, color=colors, height=0.4, zorder=3)
    
    # Format the Y-axis labels
    ax.set_yticks(range(len(panel_items)))
    ax.set_yticklabels(labels)
    
    # Dynamically scale the X-axis so the longest bar and its text always fit
    ax.set_xlim(0, max_val_seen + (max_val_seen * 0.2) + 1.0)
    ax.set_xticks([]) 

    ax.invert_yaxis()
    
    # Calculate dynamic height so bars don't get squished if there are lots of them
    # Base height of 0.8 inches + 0.4 inches per bar
    dynamic_h = max(1.65, 0.8 + (len(panel_items) * 0.4))
    
    return _export(fig, ax, target_height=dynamic_h)


def create_trend_chart(history, title, unit=""):
    """4. Standard Line Trend Chart"""
    dates, values = [], []
    history_sorted = sorted(history, key=lambda x: datetime.strptime(x[0], "%Y-%m-%d"))
    
    for h in history_sorted:
        dates.append(datetime.strptime(h[0], "%Y-%m-%d"))
        try: values.append(float(h[2]))
        except: values.append(0.0)

    fig, ax = plt.subplots()
    
    ax.plot(dates, values, marker='o', color=COLOR_PRIMARY, lw=2, zorder=3)
    
    # Fill under curve
    if values:
        bottom_val = min(values) * 0.9 if min(values) > 0 else 0
        ax.fill_between(dates, values, bottom_val, color=COLOR_PRIMARY, alpha=0.1, zorder=2)
        ax.set_ylim(bottom=bottom_val)

    # X-Axis formatting & padding
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))

    ax.tick_params(axis='both', which='both', labelbottom=False, labelleft=False)

    if dates:
        pad = timedelta(days=5)
        ax.set_xlim(min(dates) - pad, max(dates) + pad)
        
    return _export(fig, ax, is_trend=True)


def create_bp_chart(systolic, diastolic, config, test_name="Blood Pressure", unit="mmHg"):
    """BP Dumbbell Chart with elastic bounds for outliers."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    
    try:
        systolic, diastolic = float(systolic), float(diastolic)
    except: return None

    min_scale = float(config.get("axis_min", 40))
    max_scale = float(config.get("axis_max", 200))
    safe_min = float(config.get("safe_min", 60)) 
    safe_max = float(config.get("safe_max", 120))

    # Dynamic Outlier Expansion
    lowest_val = min(systolic, diastolic)
    highest_val = max(systolic, diastolic)

    if lowest_val < min_scale:
        min_scale = lowest_val - (max_scale - lowest_val) * 0.1
    if highest_val > max_scale:
        max_scale = highest_val + (highest_val - min_scale) * 0.1

    if min_scale < 0 and float(config.get("axis_min", 40)) >= 0:
        min_scale = 0.0

    fig, ax = plt.subplots()
    ax.plot([min_scale, max_scale], [0, 0], color='#B0BEC5', linewidth=2, zorder=1)
    ax.add_patch(patches.Rectangle((safe_min, -0.4), safe_max - safe_min, 0.8, color='#E8F5E9', zorder=0))
    
    color = '#DC143C' if (systolic > 120 or diastolic > 80) else '#003366'

    ax.plot([diastolic, systolic], [0, 0], color=color, linewidth=4, zorder=2)
    ax.scatter([diastolic, systolic], [0, 0], color=['white', color], edgecolor=color, s=120, linewidth=2, zorder=3)
    
    def fmt(v): return str(int(v)) if float(v).is_integer() else f"{v:.1f}"
    
    ax.text(diastolic, -0.55, fmt(diastolic), ha='center', va='top', fontweight='bold', color=color)
    ax.text(diastolic, 0.45, "DIA", ha='center', va='bottom', fontsize=8)
    ax.text(systolic, -0.55, fmt(systolic), ha='center', va='top', fontweight='bold', color=color)
    ax.text(systolic, 0.45, "SYS", ha='center', va='bottom', fontsize=8)
    
    ax.set_yticks([])
    ax.set_xlim(min_scale, max_scale)
    ax.set_ylim(-1.0, 1.0)
    return _export(fig, ax)


def create_bp_trend_chart(sys_history, dia_history, config):
    """6. BP River Trend Chart (Accepts two separate history arrays)"""
    if not sys_history or not dia_history: return None

    dates, systolics, diastolics = [], [], []
    
    # Match dates between systolic and diastolic arrays
    sys_dict = {h[0].split()[0]: float(h[2]) for h in sys_history if h[2]}
    dia_dict = {h[0].split()[0]: float(h[2]) for h in dia_history if h[2]}
    
    common_dates = sorted(list(set(sys_dict.keys()) & set(dia_dict.keys())))
    if len(common_dates) < 2: return None

    for d in common_dates:
        dates.append(datetime.strptime(d, "%Y-%m-%d"))
        systolics.append(sys_dict[d])
        diastolics.append(dia_dict[d])

    fig, ax = plt.subplots()
    # Broad safe zone for BP river chart
    ax.axhspan(60, 120, color=COLOR_SAFE_BG, alpha=0.4, linewidth=0, zorder=0)

    ax.plot(dates, systolics, marker='o', markersize=5, color=COLOR_PRIMARY, linewidth=2, zorder=3)
    ax.plot(dates, diastolics, marker='o', markersize=5, color=COLOR_PRIMARY, linewidth=2, zorder=3)
    ax.fill_between(dates, diastolics, systolics, color=COLOR_PRIMARY, alpha=0.1, zorder=2)
    
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.tick_params(axis='both', which='both', labelbottom=False, labelleft=False)

    if dates:
        pad = timedelta(days=5)
        ax.set_xlim(min(dates) - pad, max(dates) + pad)
    return _export(fig, ax, is_trend=True)


def create_multi_trend_chart(group_data):
    """Line chart with multiple lines for panels like Cholesterol"""
    if not group_data: return None

    from datetime import datetime, timedelta
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    # Extract unique dates and test names
    raw_dates = sorted(list(set([t[0].split()[0] for t in group_data])))
    test_names = sorted(list(set([t[1] for t in group_data])))

    if len(raw_dates) < 2: return None # Need at least 2 points for a trend

    dates = [datetime.strptime(d, "%Y-%m-%d") for d in raw_dates]
    fig, ax = plt.subplots()

    # Distinct colors for the lines (Primary Blue, Green, Red, Orange, Purple)
    colors = ['#003366', '#2E8B57', '#DC143C', '#FF8C00', '#8A2BE2']

    for idx, t_name in enumerate(test_names):
        # Extract values for this specific test
        t_history = [t for t in group_data if t[1] == t_name]
        val_dict = {t[0].split()[0]: float(t[2]) for t in t_history if t[2]}

        # Build arrays matching the dates where this test was actually taken
        t_dates = []
        t_vals = []
        for d in raw_dates:
            if d in val_dict:
                t_dates.append(datetime.strptime(d, "%Y-%m-%d"))
                t_vals.append(val_dict[d])

        if t_dates:
            # Clean up name for the legend (e.g. "Total Cholesterol" -> "Total")
            label_name = t_name.replace("Cholesterol", "").replace("Panel", "").strip()
            if not label_name: label_name = t_name
            
            ax.plot(t_dates, t_vals, marker='o', markersize=5, linewidth=2, label=label_name, color=colors[idx % len(colors)])

    # Format the axes
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.tick_params(axis='both', which='both', labelbottom=False, labelleft=False)

    # Add a clean legend below the chart
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3, frameon=False, fontsize=8)

    if dates:
        pad = timedelta(days=8) # Slightly larger pad to make room for the legend
        ax.set_xlim(min(dates) - pad, max(dates) + pad)
        
    return _export(fig, ax, is_trend=True)


def create_text_only_display(value, unit):
    """Generates a sleek, modern typographic 'chart' for text-only values like Weight."""
    import matplotlib.pyplot as plt
    
    fig, ax = plt.subplots(figsize=(4, 2)) # Keeps the aspect ratio consistent with the gauges
    ax.axis('off')
    
    # Clean up formatting to remove trailing .0 if it's a whole number
    try:
        val_float = float(value)
        display_val = str(int(val_float)) if val_float.is_integer() else f"{val_float:.1f}"
    except ValueError:
        display_val = str(value) # Fallback if it's actual text

    # Draw the large value in the primary theme color
    ax.text(0.5, 0.6, display_val, ha='center', va='center', fontsize=46, fontweight='bold', color='#003366')
    
    # Draw the unit nicely formatted below it
    unit_text = unit if unit and unit != "N/A" else ""
    if unit_text:
        ax.text(0.5, 0.2, unit_text, ha='center', va='center', fontsize=14, color='#757575', fontweight='bold')
        
    return _export(fig, ax)
