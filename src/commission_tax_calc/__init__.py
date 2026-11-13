"""Commission Tax Calc - sums FinTrust commission statements for the Czech tax return.

The package is split into two layers on purpose:

* ``commission_tax_calc.core`` - pure Python domain logic (parsing, validation,
  aggregation, flat-rate expense rules). It has no Qt dependency, so it can be
  unit-tested quickly and reused from the CLI.
* ``commission_tax_calc.gui`` - a thin PySide6 front-end on top of the core.
"""

__version__ = "0.2.0"
