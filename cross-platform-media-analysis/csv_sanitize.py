"""Neutralize spreadsheet formula injection in CSV cells carrying untrusted text.

Scraped comment text is written verbatim into downloadable CSVs (see issue
#147). A hostile commenter can plant a leading ``=``, ``+``, ``-`` or ``@``
(also tab / CR) that spreadsheet apps evaluate as a formula when the file is
opened directly. The standard mitigation (OWASP) is to prefix such cells with
a single quote: Excel/LibreOffice then treat the cell as plain text.

Apply at CSV *generation* time, e.g.::

    from csv_sanitize import sanitize_csv_row
    w.writerows(sanitize_csv_row(r) for r in rows)
"""

#: Characters that make spreadsheet apps treat a cell as a formula when first.
TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value):
    """Prefix a single quote when *value* starts with a formula-trigger char.

    Non-string values (None, numbers, bools) pass through unchanged. The
    single-quote prefix is a spreadsheet convention, not part of the data:
    Excel/LibreOffice display the cell as text and do not evaluate it.
    """
    if isinstance(value, str) and value[:1] in TRIGGER_CHARS:
        return "'" + value
    return value


def sanitize_csv_row(row):
    """Return a copy of a mapping row with every cell passed through
    :func:`sanitize_csv_cell` (for use with ``csv.DictWriter``)."""
    return {key: sanitize_csv_cell(value) for key, value in row.items()}
