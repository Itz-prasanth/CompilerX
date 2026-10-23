from .gnu import GnuAdapter


class CAdapter(GnuAdapter):
    language = "c"; extension = ".c"; display = "C (GCC)"
    compiler = "gcc"; std = "-std=c11"; filename = "main.c"
