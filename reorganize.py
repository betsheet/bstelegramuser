import os
import shutil

base = "/Users/espinosa012/bs/bstelegramuser"
pkg = os.path.join(base, "bstelegramuser")

os.makedirs(os.path.join(pkg, "_mixins"), exist_ok=True)

for f in ["__init__.py", "bstelegramuser.py"]:
    src = os.path.join(base, f)
    dst = os.path.join(pkg, f)
    if os.path.exists(src):
        shutil.copy2(src, dst)

for f in os.listdir(os.path.join(base, "_mixins")):
    if f.endswith(".py"):
        shutil.copy2(
            os.path.join(base, "_mixins", f),
            os.path.join(pkg, "_mixins", f),
        )

for root, dirs, files in os.walk(pkg):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    level = root.replace(pkg, "").count(os.sep)
    print("  " * level + os.path.basename(root) + "/")
    for f in sorted(files):
        print("  " * (level + 1) + f)

