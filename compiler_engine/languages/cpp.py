from .gnu import GnuAdapter


class CppAdapter(GnuAdapter):
    language = "cpp"; extension = ".cpp"; display = "C++ (G++)"
    compiler = "g++"; std = "-std=c++17"; filename = "main.cpp"
