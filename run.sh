#!/bin/bash
# CardioScan AI — startup script
# Usage: bash run.sh
# Works on both Raspberry Pi and development machines.

set -e
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        CardioScan AI — Startup       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Pick the best available Python ──────────────────────────────────────
PYTHON=""

# Prefer venv if its Python is a native binary for this machine
if [ -f ".venv/bin/python" ]; then
    if .venv/bin/python -c "import sys; sys.exit(0)" 2>/dev/null; then
        PYTHON=".venv/bin/python"
        echo "[+] Using venv Python: $(.venv/bin/python --version 2>&1)"
    else
        echo "[-] .venv/bin/python is not runnable on this machine (wrong arch?), falling back..."
    fi
fi

if [ -z "$PYTHON" ]; then
    # Fall back to system python3
    PYTHON="$(which python3)"
    echo "[+] Using system Python: $($PYTHON --version 2>&1)"
fi

# ── 2. Check & install missing packages ────────────────────────────────────
REQUIRED="flask serial pandas numpy scipy matplotlib reportlab"
MISSING=""

for pkg in $REQUIRED; do
    if ! "$PYTHON" -c "import $pkg" 2>/dev/null; then
        MISSING="$MISSING $pkg"
    fi
done

if [ -n "$MISSING" ]; then
    echo ""
    echo "[!] Missing packages:$MISSING"
    echo "[+] Installing via pip..."
    echo ""

    # Try standard pip first, then --break-system-packages (PEP 668 distros)
    if ! "$PYTHON" -m pip install -q -r requirements.txt 2>/dev/null; then
        "$PYTHON" -m pip install -q --break-system-packages -r requirements.txt
    fi

    echo "[+] Packages installed."
fi

# ── 3. Verify all imports succeed ──────────────────────────────────────────
echo ""
echo "[+] Verifying imports..."
"$PYTHON" -c "
import flask, serial, pandas, numpy, scipy, matplotlib, reportlab
print('    flask      OK')
print('    pyserial   OK')
print('    pandas     OK')
print('    numpy      OK')
print('    scipy      OK')
print('    matplotlib OK')
print('    reportlab  OK')
"

# ── 4. Launch ───────────────────────────────────────────────────────────────
echo ""
echo "[+] Starting CardioScan AI on http://0.0.0.0:5000"
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$LOCAL_IP" ] && LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '/src/{print $7}' | head -1)
echo "    Access from phone: http://${LOCAL_IP:-<pi-ip>}:5000"
echo ""
exec "$PYTHON" ui/app.py
