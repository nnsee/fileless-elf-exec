#!/usr/bin/env python3

# written-by: neonsea 2020
# for license, check LICENSE file

from base64 import b64encode
import argparse
import sys
import zlib

def print_help(parser):
    # custom print handler because we don't want any non-python
    # output to be printed to stdout
    parser.print_help(file=sys.stderr)
    sys.exit()

class CodeGenerator():
    def __init__(self):
        self.output = ""

    def generate(self, elf: bytes, syscall: int, argv: str) -> str:
        self.add_header()
        self.add_elf(elf)
        self.add_dump_elf(syscall)
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
        self.add("s = l.syscall")

    def add_elf(self, elf: bytes):
        compressed_elf = zlib.compress(elf, 9)
        encoded = b64encode(compressed_elf)
        self.add(f"c = base64.b64decode({encoded})")
        self.add(f"e = zlib.decompress(c)")
    
    def add_dump_elf(self, syscall: int):
        self.add(f"f = s({syscall}, '', 1)")
        self.add("os.write(f, e)")
    
    def add_call_elf(self, argv: str):
        self.add(f"c = '/proc/self/fd/%d' % f")
        args = argv.strip()
        args = args.replace("'", "\\'")
        args = args.replace(" ", "', '")
        self.add(f"os.execle(c, '{args}', {{}})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Print Python code to stdout to execute an ELF without dropping files.",
        add_help=False)
    parser.add_argument('-h', '--help', action='store_true', 
      help="print this help message and exit")
    parser.add_argument('path', type=argparse.FileType("rb"), 
      help="path to the ELF file")
    parser.add_argument('-s', '--syscall', metavar='NUM', type=int, 
      help="syscall number for memfd_create for the target platform (default: 319)", default=319)
    parser.add_argument('-a', '--argv',
      help="space-separated arguments (including argv[0]) supplied to execle (default: path to file as argv[0])")
    parser.add_argument('-c', '--with-command', action='store_true',
      help="wrap the generated code in a call to Python, for piping directly into ssh")
    parser.add_argument('-p', '--python-path', metavar='PYPATH', default='/usr/bin/env python3',
      help="path to python on target if '-c' is used (default: '/usr/bin/env python3')")
    args = parser.parse_args()

    if args.help:
        # todo: don't require positional args
        print_help(parser) # exits with 0

    argv = args.argv
    if not argv:
        argv = args.path.name
    
    elf = args.path.read()
    args.path.close()
    
    CG = CodeGenerator()
    out = CG.generate(elf, args.syscall, argv)
    if args.with_command:
        out = CG.with_command(args.python_path)
    
    print(out)