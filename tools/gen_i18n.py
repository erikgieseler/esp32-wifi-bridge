#!/usr/bin/env python3
"""
gen_i18n.py – JSON -> C header for i18n (NVS-only, reboot after change)
Reads locales/*.json, generates include/i18n_keys.h + include/i18n_data.h
 - Fallback EN, completeness check
 - Placeholder {0} consistency
 - UTF-8, C string escaping (quotes, backslash, newline)
 - Sorted keys for binary search
 - Used as standalone or as PlatformIO extra_script (pre)
"""
import json
import os
import sys
import re
from pathlib import Path

# Project root – lazy init for SCons (no __file__)
TOOLS_DIR = None
PROJECT_ROOT = None
LOCALES_DIR = None
INCLUDE_DIR = None
SRC_DIR = None

def _init_paths():
    global TOOLS_DIR, PROJECT_ROOT, LOCALES_DIR, INCLUDE_DIR, SRC_DIR
    if PROJECT_ROOT is not None and LOCALES_DIR is not None:
        return
    try:
        td = Path(__file__).parent
        pr = td.parent
    except NameError:
        try:
            pr = Path(env.get("PROJECT_DIR"))  # type: ignore
            td = pr / "tools"
        except Exception:
            pr = Path.cwd()
            td = pr / "tools"
    TOOLS_DIR = td
    PROJECT_ROOT = pr
    LOCALES_DIR = pr / "locales"
    INCLUDE_DIR = pr / "include"
    SRC_DIR = pr / "src"

def c_escape(s: str) -> str:
    # Escape for C string literal (keep UTF-8, only " \ and control chars)
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return "".join(out)

def placeholder_count(s: str) -> int:
    # count {0}, {1} etc.
    return len(re.findall(r"\{\d+\}", s))

def load_locales():
    _init_paths()
    if not LOCALES_DIR.is_dir():
        print(f"ERROR: locales dir not found: {LOCALES_DIR}", file=sys.stderr)
        sys.exit(1)
    json_files = sorted(LOCALES_DIR.glob("*.json"))
    if not json_files:
        print(f"ERROR: no json in {LOCALES_DIR}", file=sys.stderr)
        sys.exit(1)
    locales = {}
    for p in json_files:
        code = p.stem  # en, de
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERROR: failed to parse {p}: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(data, dict):
            print(f"ERROR: {p} root must be object", file=sys.stderr)
            sys.exit(1)
        locales[code] = data
    # en first, then alphabetical
    ordered = {}
    if "en" in locales:
        ordered["en"] = locales.pop("en")
    for k in sorted(locales.keys()):
        ordered[k] = locales[k]
    return ordered

def generate(check_only=False):
    _init_paths()
    locales = load_locales()
    codes = list(locales.keys())  # en, de, ...
    print(f"i18n: found locales {codes}")
    # Union keys
    all_keys = set()
    for data in locales.values():
        all_keys.update(data.keys())
    sorted_keys = sorted(all_keys)
    # Completeness: en must contain all keys
    missing_in_en = [k for k in sorted_keys if k not in locales.get("en", {})]
    if missing_in_en:
        print(f"ERROR: missing keys in en.json: {missing_in_en}", file=sys.stderr)
        sys.exit(1)
    # Warning for missing in others
    for code in codes:
        if code == "en":
            continue
        missing = [k for k in sorted_keys if k not in locales[code]]
        if missing:
            print(f"WARN: missing keys in {code}.json (fallback to en): {missing}", file=sys.stderr)
            # fallback
            for k in missing:
                locales[code][k] = locales["en"][k]
    # Placeholder consistency
    for k in sorted_keys:
        counts = {code: placeholder_count(locales[code][k]) for code in codes}
        if len(set(counts.values())) != 1:
            print(f"WARN: placeholder mismatch for key '{k}': {counts}", file=sys.stderr)
    # Percent check: locales should not contain unescaped % that would be interpreted as printf
    # We keep % as is, but warn for single % not followed by % or s/d
    for code in codes:
        for k, v in locales[code].items():
            # single % not escaped as %% and not part of %s/%d etc. -> warn
            if "%" in v:
                # only %% is allowed in locales (not needed, we use {0})
                print(f"WARN: '%' in {code}.json key '{k}': {repr(v)} – ensure not printf-escaped incorrectly", file=sys.stderr)

    if check_only:
        print(f"i18n: check ok – {len(sorted_keys)} keys, {len(codes)} langs")
        return

    # Generate i18n_keys.h
    INCLUDE_DIR.mkdir(parents=True, exist_ok=True)
    if SRC_DIR:
        SRC_DIR.mkdir(parents=True, exist_ok=True)
    keys_h = INCLUDE_DIR / "i18n_keys.h"
    data_h = INCLUDE_DIR / "i18n_data.h"
    data_c = SRC_DIR / "i18n_data.c" if SRC_DIR else PROJECT_ROOT / "src" / "i18n_data.c"

    # Enum names: I18N_<UPPER_SNAKE>
    def key_to_enum(k):
        return "I18N_" + re.sub(r"[^a-zA-Z0-9]", "_", k).upper()

    with keys_h.open("w", encoding="utf-8", newline="\n") as f:
        f.write("#pragma once\n")
        f.write("// AUTO-GENERATED by tools/gen_i18n.py – do not edit\n")
        f.write(f"// Sources: {', '.join(f'{c}.json' for c in codes)}\n")
        f.write(f"#define I18N_KEY_COUNT {len(sorted_keys)}\n")
        f.write("typedef enum {\n")
        for i, k in enumerate(sorted_keys):
            enum = key_to_enum(k)
            f.write(f"    {enum} = {i},\n")
        f.write("} i18n_key_t;\n")

    # i18n_data.h – extern declarations (no duplication)
    with data_h.open("w", encoding="utf-8", newline="\n") as f:
        f.write("#pragma once\n")
        f.write("// AUTO-GENERATED by tools/gen_i18n.py – do not edit\n")
        f.write('#include "i18n_keys.h"\n')
        f.write(f"// Langs: {', '.join(codes)}\n")
        f.write(f"#define I18N_LANG_COUNT {len(codes)}\n")
        f.write("extern const char *I18N_KEYS[I18N_KEY_COUNT];\n")
        for code in codes:
            var = f"I18N_{code.upper()}"
            f.write(f"extern const char *{var}[I18N_KEY_COUNT];\n")
        f.write("extern const char *I18N_LANG_CODES[I18N_LANG_COUNT];\n")
        f.write("extern const char **I18N_TABLE[I18N_LANG_COUNT];\n")
        f.write("// LANG enum mapping: LANG_EN=0 must match order en,de,...\n")

    # i18n_data.c – single definition (saves 9KB flash)
    with data_c.open("w", encoding="utf-8", newline="\n") as f:
        f.write("// AUTO-GENERATED by tools/gen_i18n.py – do not edit\n")
        f.write('#include "i18n_data.h"\n')
        f.write("const char *I18N_KEYS[I18N_KEY_COUNT] = {\n")
        for k in sorted_keys:
            f.write(f'    "{c_escape(k)}",\n')
        f.write("};\n")
        for code in codes:
            var = f"I18N_{code.upper()}"
            f.write(f"const char *{var}[I18N_KEY_COUNT] = {{\n")
            for k in sorted_keys:
                v = locales[code][k]
                f.write(f'    "{c_escape(v)}",\n')
            f.write("};\n")
        f.write("const char *I18N_LANG_CODES[I18N_LANG_COUNT] = {\n")
        for code in codes:
            f.write(f'    "{c_escape(code)}",\n')
        f.write("};\n")
        f.write("const char **I18N_TABLE[I18N_LANG_COUNT] = {\n")
        for code in codes:
            f.write(f"    I18N_{code.upper()},\n")
        f.write("};\n")

    print(f"i18n: generated {keys_h} ({len(sorted_keys)} keys)")
    print(f"i18n: generated {data_h} + {data_c} ({len(codes)} langs, extern saves ~9KB)")

def main():
    check = "--check" in sys.argv or "-c" in sys.argv
    generate(check_only=check)

# PlatformIO extra_script hook: try Import env
try:
    Import("env")
    # When run as extra_script, generate immediately (pre-build)
    print("i18n: PlatformIO pre-build – generating headers...")
    generate(check_only=False)
    # Ensure rebuild if locales change: add dependency
    # (SCons will watch these files if we add to CPPPATH? We just print)
except Exception:
    # standalone run
    if __name__ == "__main__":
        main()
