#!/usr/bin/env python3

# written-by: neonsea 2020
# for license, check LICENSE file

from base64 import b64encode
import argparse
import sys
import zlib

class CodeGenerator():
    def __init__(self):
        self.output = ""
        self.zCompressionLevel = 9
        self.wrap = 0
        self.syscall = None

    def generate(self, elf: bytes, argv: str) -> str:
        self.add_header()
        self.add_elf(elf)
        self.add_dump_elf()
        self.add_call_elf(argv)
        return self.output
    
    def with_command(self, path: str):
        escaped = self.output.replace('"', '\\"')
        return f'{path} -c "{escaped}"'
    
    def add(self, line: str):
        self.output += f"{line}\n"
    
    def add_header(self):
        self.add("import ctypes, os, base64, zlib")
        self.add("l = ctypes.CDLL(None)")
        if self.syscall:
            self.add("s = l.syscall")
        else:
            self.add("s = l.memfd_create")

    def add_elf(self, elf: bytes):
        compressed_elf = zlib.compress(elf, self.zCompressionLevel)
        encoded = f"{b64encode(compressed_elf)}"

        # wrap if necessary
        if self.wrap > 3:
            chars = self.wrap - 3 # two quotes and byte literal identifier
            length = len(encoded)
            encoded = "'\nb'".join(encoded[i:i+chars] for i in range(0, length, chars))

        self.add(f"c = base64.b64decode(\n{encoded}\n)")
        self.add(f"e = zlib.decompress(c)")
    
    def add_dump_elf(self):
        if self.syscall:
            self.add(f"f = s({self.syscall}, '', 1)")
        else:
            self.add("f = s('', 1)")
        self.add("os.write(f, e)")
    
    def add_call_elf(self, argv: str):
        self.add(f"c = '/proc/self/fd/%d' % f")
        args = argv.strip()
        args = args.replace("'", "\\'")
        args = args.replace(" ", "', '")
        self.add(f"os.execle(c, '{args}', {{}})")

if __name__ == "__main__":
    # we need to monkeypatch the help function to print to stderr
    # as we want nothing but executable code being printed to stdout
    def patched_help_call(self, parser, namespace, values, option_string=None):
        parser.print_help(file=sys.stderr)
        parser.exit()
    
    argparse._HelpAction.__call__ = patched_help_call

    parser = argparse.ArgumentParser(
        description="Print Python code to stdout to execute an ELF without dropping files.")
    parser.add_argument('path', type=argparse.FileType("rb"), 
      help="path to the ELF file")
    parser.add_argument('-s', '--syscall', metavar='NUM', type=int, 
      help="syscall number for memfd_create for the target platform (default: resolve symbol via libc)")
    parser.add_argument('-a', '--argv',
      help="space-separated arguments (including argv[0]) supplied to execle (default: path to file as argv[0])")
    parser.add_argument('-c', '--with-command', action='store_true',
      help="wrap the generated code in a call to Python, for piping directly into ssh")
    parser.add_argument('-p', '--python-path', metavar='PATH', default='/usr/bin/env python3',
      help="path to python on target if '-c' is used (default: '/usr/bin/env python3')")
    parser.add_argument('-w', '--wrap', metavar='CHARS', type=int,
      help="when base64-encoding the elf, how many characters to wrap to a newline (default: 0)", default=0)
    parser.add_argument('-z', '--compression-level', metavar='LEVEL', type=int,
      help="zlib compression level, 0-9 (default: 9)", choices=range(0, 10), default=9)
    args = parser.parse_args()

    argv = args.argv
    if not argv:
        argv = args.path.name
    
    elf = args.path.read()
    args.path.close()
    
    CG = CodeGenerator()

    CG.zCompressionLevel = args.compression_level
    CG.wrap = args.wrap
    CG.syscall = args.syscall

    out = CG.generate(elf, argv)
    if args.with_command:
        out = CG.with_command(args.python_path)
    
    print(out)