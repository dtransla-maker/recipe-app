"""
Double-click this file (or run it) to create recipesnap.zip
ready for uploading to Replit.
"""
import zipfile
import os

# Files and folders to include
base = os.path.dirname(os.path.abspath(__file__))
output_zip = os.path.join(base, "recipesnap.zip")

include = [
    "app.py",
    "requirements.txt",
    ".replit",
    os.path.join("templates", "index.html"),
    os.path.join("templates", "library.html"),
    os.path.join("templates", "recipe.html"),
    os.path.join("static", "styles.css"),
    os.path.join("static", "app.js"),
    "supabase_setup.sql",
]

with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel_path in include:
        full_path = os.path.join(base, rel_path)
        if os.path.exists(full_path):
            zf.write(full_path, rel_path)
            print(f"  ✓ Added {rel_path}")
        else:
            print(f"  ✗ MISSING: {rel_path}")

print(f"\nDone! Zip saved to:\n  {output_zip}")
input("\nPress Enter to close...")
