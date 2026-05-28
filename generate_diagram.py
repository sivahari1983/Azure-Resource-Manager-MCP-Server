"""
Generates ARM MCP Server architecture flow diagram as PDF.
Run: python generate_diagram.py
Output: ARM_MCP_Server_Architecture.pdf
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.patheffects as pe

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
C = {
    "foundry":    "#0078D4",   # Azure blue
    "human":      "#C75000",   # Orange — human caller
    "entra":      "#5C2D91",   # Purple
    "envoy":      "#107C10",   # Green
    "auth":       "#006494",   # Teal-blue — middleware
    "route":      "#004E89",   # Dark blue
    "obo":        "#C75000",   # Amber — OBO path
    "mi":         "#1B5E20",   # Dark green — MI path
    "dispatch":   "#1A237E",   # Indigo
    "tool":       "#00695C",   # Dark teal
    "arg":        "#2E7D32",   # Green
    "arm":        "#388E3C",   # Medium green
    "sub":        "#81C784",   # Light green
    "arrow":      "#37474F",
    "obo_arrow":  "#BF360C",
    "mi_arrow":   "#1B5E20",
    "bg":         "#F8FBFF",
    "bg_caller":  "#E3F2FD",
    "bg_server":  "#EDF4FB",
    "bg_azure":   "#E8F5E9",
    "white":      "#FFFFFF",
    "dark":       "#1A1A1A",
    "light":      "#FFFFFF",
    "gray":       "#607D8B",
}

FIG_W, FIG_H = 24, 16
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
fig.patch.set_facecolor(C["bg"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def rbox(ax, cx, cy, w, h, text, sub=None,
         fc=C["white"], ec=C["route"], tc=C["dark"],
         fs=8.5, bold=False, radius=0.25, lw=1.5):
    ax.add_patch(FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=3,
    ))
    fw = "bold" if bold else "normal"
    if sub:
        ax.text(cx, cy + h * 0.16, text, ha="center", va="center",
                fontsize=fs, color=tc, fontweight=fw, zorder=4)
        ax.text(cx, cy - h * 0.24, sub, ha="center", va="center",
                fontsize=fs - 1.5, color=tc, fontstyle="italic", zorder=4)
    else:
        ax.text(cx, cy, text, ha="center", va="center",
                fontsize=fs, color=tc, fontweight=fw, zorder=4)


def section(ax, x, y, w, h, title, fc, ec):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.3",
        facecolor=fc, edgecolor=ec, linewidth=2, linestyle="--",
        zorder=1, alpha=0.45,
    ))
    ax.text(x + 0.2, y + h - 0.25, title,
            ha="left", va="top", fontsize=9, color=ec,
            fontweight="bold", zorder=2)


def harrow(ax, x0, y, x1, label="", color=C["arrow"], lw=1.8,
           dashed=False, label_above=True):
    ls = (0, (5, 3)) if dashed else "solid"
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                linestyle=ls), zorder=5)
    if label:
        my = y + 0.18 if label_above else y - 0.28
        ax.text((x0 + x1) / 2, my, label,
                ha="center", va="bottom" if label_above else "top",
                fontsize=7, color=color, zorder=6,
                bbox=dict(fc=C["bg"], ec="none", pad=1))


def varrow(ax, x, y0, y1, label="", color=C["arrow"], lw=1.8,
           dashed=False, label_right=True):
    ls = (0, (5, 3)) if dashed else "solid"
    ax.annotate("", xy=(x, y1), xytext=(x, y0),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                linestyle=ls), zorder=5)
    if label:
        mx = x + 0.18 if label_right else x - 0.18
        ax.text(mx, (y0 + y1) / 2, label,
                ha="left" if label_right else "right",
                va="center", fontsize=7, color=color, zorder=6,
                bbox=dict(fc=C["bg"], ec="none", pad=1))


def bent_arrow(ax, x0, y0, x1, y1, label="", color=C["arrow"], lw=1.8,
               dashed=False):
    """L-shaped arrow: go right to x1, then up/down to y1."""
    ls = (0, (5, 3)) if dashed else "solid"
    # horizontal leg
    ax.annotate("", xy=(x1, y0), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-", color=color, lw=lw,
                                linestyle=ls), zorder=5)
    # vertical leg with arrowhead
    ax.annotate("", xy=(x1, y1), xytext=(x1, y0),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                linestyle=ls), zorder=5)
    if label:
        ax.text((x0 + x1) / 2, y0 + 0.18, label,
                ha="center", va="bottom", fontsize=7, color=color, zorder=6,
                bbox=dict(fc=C["bg"], ec="none", pad=1))


# ============================================================================
# TITLE
# ============================================================================
ax.text(FIG_W / 2, 15.55,
        "ARM MCP Server — Architecture Flow Diagram",
        ha="center", va="center", fontsize=17, fontweight="bold",
        color=C["route"])
ax.text(FIG_W / 2, 15.1,
        "Azure AI Foundry  ·  Azure Container Apps  ·  Streamable HTTP  ·  On-Behalf-Of (OBO)",
        ha="center", va="center", fontsize=10, color=C["gray"])

# ============================================================================
# COLUMN POSITIONS
# Col A — Callers        x:  0.3 – 5.7   centre 3.0
# Col B — Container App  x:  6.0 – 17.2  centre 11.6
# Col C — Azure Services x: 17.5 – 23.7  centre 20.6
# ============================================================================

# ── COLUMN A: Callers ───────────────────────────────────────────────────────
section(ax, 0.3, 1.4, 5.4, 13.3,
        "Callers & Identity", fc=C["bg_caller"], ec=C["foundry"])

# Foundry Agent
rbox(ax, 3.0, 13.2, 4.4, 0.85,
     "Foundry Agent", "Managed Identity (M2M)",
     fc=C["foundry"], ec=C["foundry"], tc=C["light"], bold=True)
ax.text(3.0, 12.57, "token type: roles claim",
        ha="center", fontsize=7.5, color=C["foundry"], style="italic")

# Human User
rbox(ax, 3.0, 11.5, 4.4, 0.85,
     "Human User", "Interactive login",
     fc=C["human"], ec=C["human"], tc=C["light"], bold=True)
ax.text(3.0, 10.87, "token type: scp claim  (delegated)",
        ha="center", fontsize=7.5, color=C["human"], style="italic")

# Separator
ax.plot([0.6, 5.4], [10.3, 10.3], color="#BBDEFB", lw=1.2, ls="--", zorder=2)

# Entra ID
rbox(ax, 3.0, 9.7, 4.4, 0.85,
     "Entra App", "api://3fbf7d06-...",
     fc=C["entra"], ec=C["entra"], tc=C["light"], bold=True)

rbox(ax, 3.0, 8.35, 4.4, 0.85,
     "JWKS Endpoint", "login.microsoftonline.com",
     fc="#7B1FA2", ec="#7B1FA2", tc=C["light"])

ax.text(3.0, 7.6, "① Foundry MI requests token", ha="center",
        fontsize=7.5, color=C["entra"])
ax.text(3.0, 7.25, "    audience: api://3fbf7d06-...", ha="center",
        fontsize=7.5, color=C["entra"])
ax.text(3.0, 6.85, "② Human user authenticates", ha="center",
        fontsize=7.5, color=C["human"])
ax.text(3.0, 6.5, "    and receives scp token", ha="center",
        fontsize=7.5, color=C["human"])
ax.text(3.0, 6.05, "③ Both callers POST /mcp", ha="center",
        fontsize=7.5, color=C["arrow"], fontweight="bold")
ax.text(3.0, 5.7, "    with Authorization: Bearer ...", ha="center",
        fontsize=7.5, color=C["arrow"])

# JWKS note
rbox(ax, 3.0, 4.7, 4.4, 1.3,
     "JWT Validation\n\n"
     "· Signature via JWKS\n"
     "· Keys cached 1 hour\n"
     "· Returns 401 if invalid",
     fc="#F3E5F5", ec=C["entra"], tc=C["dark"], fs=7.5)

# Connections within col A
varrow(ax, 3.0, 9.28, 8.93, color=C["entra"], lw=1.2, dashed=True,
       label="keys")

# ── COLUMN B: Container App ─────────────────────────────────────────────────
section(ax, 6.0, 1.4, 11.2, 13.3,
        "Azure Container App — arm-mcp-server  (mcp_server.py)",
        fc=C["bg_server"], ec=C["route"])

BW = 9.4   # box width for full-width server boxes
BX = 11.6  # centre x

# Envoy
rbox(ax, BX, 13.2, BW, 0.85,
     "Envoy Proxy",
     "TLS termination  ·  HTTPS → HTTP:8080  ·  proxy_headers=True",
     fc=C["envoy"], ec=C["envoy"], tc=C["light"], bold=True)

# EntraAuthMiddleware
rbox(ax, BX, 11.8, BW, 0.85,
     "EntraAuthMiddleware  (pure ASGI)",
     "Validates JWT · stores caller_token in scope · passes receive unchanged",
     fc=C["auth"], ec=C["auth"], tc=C["light"], bold=True)

# mcp_endpoint
rbox(ax, BX, 10.4, BW, 0.85,
     "POST /mcp  —  mcp_endpoint()",
     "Reads JSON-RPC body · calls _make_request_credential(caller_token)",
     fc=C["route"], ec=C["route"], tc=C["light"], bold=True)

# ── OBO Decision box
rbox(ax, BX, 8.8, BW, 1.15,
     "_make_request_credential(caller_token)",
     None,
     fc="#1A237E", ec="#1A237E", tc=C["light"], bold=True, fs=9)

# YES / NO lines inside decision box
ax.text(BX, 8.6,
        "scp claim present  AND  ENTRA_APP_CLIENT_SECRET configured?",
        ha="center", va="center", fontsize=8, color="#BBDEFB", zorder=4)

# YES label
ax.text(BX + 1.8, 9.05, "YES  →  OnBehalfOfCredential",
        ha="center", va="center", fontsize=8,
        color="#FFAB91", fontweight="bold", zorder=4)

# NO label
ax.text(BX - 1.8, 9.05, "NO  →  DefaultAzureCredential (MI)",
        ha="center", va="center", fontsize=8,
        color="#A5D6A7", fontweight="bold", zorder=4)

# contextvars sticky note
ax.add_patch(FancyBboxPatch((6.2, 7.35), 3.8, 0.9,
                             boxstyle="round,pad=0,rounding_size=0.15",
                             facecolor="#FFFDE7", edgecolor="#F9A825",
                             linewidth=1.2, zorder=3))
ax.text(8.1, 7.8, "contextvars  (per request, async-safe)",
        ha="center", va="center", fontsize=7.5,
        color="#5D4037", fontweight="bold", zorder=4)
ax.text(8.1, 7.55, "_ctx_credential  /  _ctx_rg_client",
        ha="center", va="center", fontsize=7.2,
        color="#5D4037", style="italic", zorder=4)

# _dispatch_message
rbox(ax, BX, 6.8, BW, 0.85,
     "_dispatch_message()",
     "initialize · tools/list · tools/call · ping",
     fc=C["dispatch"], ec=C["dispatch"], tc=C["light"], bold=True)

# MCP Methods (3 small boxes)
mw, mh, my = 2.7, 0.72, 5.7
for i, (lbl, sub) in enumerate([
        ("initialize", "→ capabilities"),
        ("tools/list", "→ 6 schemas"),
        ("tools/call", "→ dispatch"),
]):
    cx = 8.5 + i * 3.1
    rbox(ax, cx, my, mw, mh, lbl, sub,
         fc=C["auth"], ec=C["auth"], tc=C["light"], fs=8)

# Tool Functions (2 rows × 3 cols)
tw, th = 2.7, 0.75
for col, (name, detail) in enumerate([
        ("generate_query",                  "KQL templates"),
        ("validate_query",                  "syntax check"),
        ("execute_query",                   "→ Resource Graph"),
]):
    rbox(ax, 8.5 + col * 3.1, 4.35, tw, th, name, detail,
         fc=C["tool"], ec=C["tool"], tc=C["light"], fs=7.8)

for col, (name, detail) in enumerate([
        ("create_template_deployment",      "→ Resource Manager"),
        ("get_arm_template_deployment_status", "→ Resource Manager"),
        ("cancel_arm_template_deployment",  "→ Resource Manager"),
]):
    rbox(ax, 8.5 + col * 3.1, 3.3, tw, th, name, detail,
         fc=C["tool"], ec=C["tool"], tc=C["light"], fs=7.5)

# ── COLUMN C: Azure Services ────────────────────────────────────────────────
section(ax, 17.5, 1.4, 6.2, 13.3,
        "Azure Services", fc=C["bg_azure"], ec="#1B5E20")

# OBO credential
rbox(ax, 20.6, 12.1, 5.4, 0.85,
     "OnBehalfOfCredential", "OBO path — user's own RBAC",
     fc=C["obo"], ec=C["obo"], tc=C["light"], bold=True)
ax.text(20.6, 11.47, "User only sees what their\nAzure RBAC permits",
        ha="center", fontsize=7.5, color=C["obo"])

# MI credential
rbox(ax, 20.6, 10.1, 5.4, 0.85,
     "DefaultAzureCredential", "MI path — User-Assigned MI",
     fc=C["mi"], ec=C["mi"], tc=C["light"], bold=True)
ax.text(20.6, 9.47, "Subscription Reader — all\nauthenticated callers share this view",
        ha="center", fontsize=7.5, color=C["mi"])

# Divider
ax.plot([17.8, 23.4], [8.9, 8.9], color="#A5D6A7", lw=1.2, ls="--", zorder=2)

# Resource Graph
rbox(ax, 20.6, 8.3, 5.4, 0.80,
     "Azure Resource Graph", "ResourceGraphClient",
     fc=C["arg"], ec=C["arg"], tc=C["light"])

# Resource Manager
rbox(ax, 20.6, 7.15, 5.4, 0.80,
     "Azure Resource Manager", "ResourceManagementClient",
     fc=C["arm"], ec=C["arm"], tc=C["light"])

# ARM Subscriptions
rbox(ax, 20.6, 4.65, 5.4, 3.5,
     "ARM Subscriptions\n\n"
     "Resource Graph queries\n"
     "Template deployments\n"
     "Deployment status/cancel\n\n"
     "OBO  →  caller's own scope\n"
     "MI    →  sub-wide Reader",
     fc="#E8F5E9", ec="#52B788", tc=C["dark"], fs=8)

# ============================================================================
# ARROWS
# ============================================================================

# Callers → Envoy
harrow(ax, 5.22, 13.2, 6.2, "③ POST /mcp + Bearer token", color=C["foundry"])
harrow(ax, 5.22, 11.5, 6.2, "③ POST /mcp + Bearer token", color=C["human"],
       label_above=False)

# Envoy → Middleware
varrow(ax, BX, 12.78, 12.23, "④ HTTP:8080", color=C["envoy"])

# Middleware → /mcp
varrow(ax, BX, 11.38, 10.83, "⑤ JWT valid · token in scope", color=C["auth"])

# /mcp → OBO decision
varrow(ax, BX, 9.98, 9.38, "⑥ credential check", color=C["route"])

# OBO decision → contextvars + dispatch
varrow(ax, BX, 8.23, 7.23, "⑦ credential set in contextvars", color=C["dispatch"])

# dispatch → methods
varrow(ax, BX, 6.38, 6.07, color=C["dispatch"])

# methods → tools (top row)
for cx in [8.5, 11.6, 14.7]:
    varrow(ax, cx, 5.34, 4.73, color=C["tool"], lw=1.3)

# top tools → bottom tools
for cx in [8.5, 11.6, 14.7]:
    varrow(ax, cx, 3.98, 3.68, color=C["tool"], lw=1.1)

# OBO decision → OBO credential (YES path — bent arrow)
bent_arrow(ax, BX + 4.7, 8.8, 17.8, 12.1,
           label="YES (scp)", color=C["obo_arrow"], lw=2.0)

# OBO decision → MI credential (NO path — bent arrow)
bent_arrow(ax, BX + 4.7, 8.8, 17.8, 10.1,
           label="NO (roles / no secret)", color=C["mi_arrow"], lw=2.0)

# execute_query → Resource Graph
harrow(ax, 14.7 + 1.35, 4.35, 17.8, "KQL query",
       color=C["arg"], dashed=True, lw=1.6)

# ARM tools → Resource Manager
harrow(ax, 13.35 + 1.35, 3.3, 17.8, "deploy / status / cancel",
       color=C["arm"], dashed=True, lw=1.6, label_above=False)

# Both credentials → Resource Graph / Manager
varrow(ax, 20.6, 11.68, 8.73, color=C["obo_arrow"], lw=1.4, dashed=True)
varrow(ax, 20.6, 9.68, 8.73, color=C["mi_arrow"], lw=1.4, dashed=True)
varrow(ax, 20.6, 7.75, 7.56, color="#388E3C", lw=1.5)
varrow(ax, 20.6, 6.75, 6.41, color="#388E3C", lw=1.5)

# JWKS ↔ Middleware (dashed — cache miss)
ax.annotate("", xy=(6.3, 11.8), xytext=(5.22, 8.35),
            arrowprops=dict(arrowstyle="-|>", color="#7B1FA2", lw=1.3,
                            linestyle=(0, (5, 3)),
                            connectionstyle="arc3,rad=-0.25"), zorder=5)
ax.text(4.8, 10.2, "cache miss:\nfetch JWKS", ha="center",
        fontsize=7, color="#7B1FA2", style="italic")

# ============================================================================
# LEGEND  — full-width, two rows, generous spacing
# ============================================================================
# Background spanning full figure width
ax.add_patch(FancyBboxPatch((0.3, 0.05), FIG_W - 0.6, 1.1,
                             boxstyle="round,pad=0,rounding_size=0.2",
                             facecolor="#F5F5F5", edgecolor="#BDBDBD",
                             linewidth=1.2, zorder=2))

ax.text(0.75, 1.0, "Legend", fontsize=8.5, fontweight="bold",
        color=C["dark"], va="center")

# Row 1 — 4 items;  Row 2 — 4 items (last row centred)
legend_items = [
    (C["foundry"], "Foundry Agent  (roles / M2M)"),
    (C["human"],   "Human User  (scp / delegated)"),
    (C["obo"],     "OnBehalfOfCredential  (OBO)"),
    (C["mi"],      "DefaultAzureCredential  (MI)"),
    (C["envoy"],   "Envoy Proxy  (TLS)"),
    (C["tool"],    "MCP Tool Functions"),
    (C["arg"],     "Azure Resource Graph"),
    (C["arm"],     "Azure Resource Manager"),
]

cols = 4
item_w = (FIG_W - 1.5) / cols   # width allocated per item
swatch_w, swatch_h = 0.32, 0.22

for i, (color, label) in enumerate(legend_items):
    row = i // cols
    col = i % cols
    # centre the last row if it has fewer items than cols
    n_in_row = min(cols, len(legend_items) - row * cols)
    offset = (cols - n_in_row) * item_w / 2
    sx = 1.5 + offset + col * item_w
    sy = 0.82 - row * 0.36

    ax.add_patch(FancyBboxPatch((sx, sy - swatch_h / 2), swatch_w, swatch_h,
                                 boxstyle="round,pad=0", facecolor=color,
                                 edgecolor="none", zorder=3))
    ax.text(sx + swatch_w + 0.15, sy, label,
            fontsize=7.8, va="center", color=C["dark"], zorder=4)

# ============================================================================
# Save
# ============================================================================
import os, shutil
repo_path = (
    r"c:\Users\hnataraj\OneDrive - Capgemini\Dokument\Sandbox Folder"
    r"\Azure-Resource-Manager-MCP-main\ARM_MCP_Server_Architecture.pdf"
)
# Write to Desktop first (never locked by OneDrive), then copy into repo
out_path = r"c:\Users\hnataraj\OneDrive - Capgemini\Skrivbordet\ARM_MCP_Server_Architecture.pdf"
try:
    os.remove(out_path)
except FileNotFoundError:
    pass
with PdfPages(out_path) as pdf:
    pdf.savefig(fig, bbox_inches="tight", facecolor=fig.get_facecolor())
    d = pdf.infodict()
    d["Title"]   = "ARM MCP Server — Architecture Flow Diagram"
    d["Author"]  = "Azure-Resource-Manager-MCP"
    d["Subject"] = "Landscape architecture: Callers | Container App | Azure Services"

plt.close(fig)
# Copy from Desktop into repo (overwrite even if OneDrive has it locked)
try:
    shutil.copy2(out_path, repo_path)
    print(f"Saved: {repo_path}")
except Exception as e:
    print(f"Saved to Desktop: {out_path}  (copy to repo failed: {e})")
