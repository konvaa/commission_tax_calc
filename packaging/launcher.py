"""Entry script for PyInstaller.

PyInstaller needs a plain script, not ``python -m``; importing the package
(instead of pointing PyInstaller at ``gui/app.py``) keeps relative imports
inside the package working in the frozen .exe.
"""

from commission_tax_calc.gui.app import main

raise SystemExit(main())
