"""benchmark_ext — an additive overlay over AppWorld (patch, don't delete).

Nothing here edits AppWorld's own code; we import, subclass and wrap at its seams. Prime invariant: with
our features unused, AppWorld behaves byte-for-byte as stock.
"""
