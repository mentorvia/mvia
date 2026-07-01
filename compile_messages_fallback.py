"""
Pure-Python fallback to compile .po -> .mo without the gettext binary.
Used by build.sh if `manage.py compilemessages` fails (e.g. gettext missing
on the build image). Requires polib (in requirements.txt).
"""
import glob
import polib

for po_path in glob.glob("locale/**/LC_MESSAGES/*.po", recursive=True):
    mo_path = po_path[:-3] + ".mo"
    try:
        polib.pofile(po_path).save_as_mofile(mo_path)
        print(f"compiled {po_path} -> {mo_path}")
    except Exception as e:  # noqa: BLE001
        print(f"WARN: could not compile {po_path}: {e}")
