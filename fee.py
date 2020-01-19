#!/usr/bin/env python3

# written-by: neonsea 2020
# for license, check LICENSE file

from base64 import b64encode
import os.path
import argparse
import sys
import zlib

def printOut(what: str):
    sys.stdout.write(what)
    sys.stdout.flush()

def printErr(what: str):
    sys.stderr.write(what)
    sys.stderr.flush()

class CodeGenerator():
    def __init__(self):
        self.zCompressionLevel = 9
        self.wrap = 0
        self.syscall = None
        self._meta = self._Python
        self._generator = None
    
    def set_lang(self, lang: str):
        if lang.lower() in ["py", "python"]:
            self._meta = self._Python
        else:
            raise LanguageNotImplementedException(f"Language '{lang}' is not implemented")

    def generate(self, elf: bytes, argv: str) -> str:
        self._generator = self._meta(self)
        self._generator.add_header()
        self._generator.add_elf(elf)
        self._generator.add_dump_elf()
        self._generator.add_call_elf(argv)
        return self._generator.output
    
    def with_command(self, **kwargs):
        if not self._generator:
            raise NotGeneratedException("Code not yet generated.")

        if kwargs.get("path") is None:
            # this is stupid
            kwargs.pop("path", None)

        return self._generator.with_command(**kwargs)
    
    class _Python():
        # Python generator metaclass
        def __init__(self, outer):
            self.output = ""
            self.zCompressionLevel = outer.zCompressionLevel
            self.wrap = outer.wrap
            self.syscall = outer.syscall
        
        def with_command(self, path="/usr/bin/env python3"):
            escaped = self.output.replace('"', '\\"')
            return f'{path} -c "{escaped}"'

        def add(self, line: str):
            self.output += f"{line}\n"

        def add_header(self):
            self.add("import ctypes, os, base64, zlib")
            self.add("l = ctypes.CDLL(None)")
            if self.syscall:
                self.add("s = l.syscall") # we specify the syscall manually
            else:
                self.add("s = l.memfd_create") # dynamic

        def add_elf(self, elf: bytes):
            # compress the binary and encode it with base64
            # base64 is required so we don't put any funky characters in an 
            # otherwise human-readable script
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
            # we create the fd with no name
            if self.syscall:
                self.add(f"f = s({self.syscall}, '', 1)")
            else:
                self.add("f = s('', 1)")
            self.add("os.write(f, e)")

        def add_call_elf(self, argv: str):
            self.add(f"c = '/proc/self/fd/%d' % f")
            args = argv.strip()
            args = args.replace("'", "\\'") # escape single quotes, we use them
            args = args.replace(" ", "', '") # split argv into separate words
            self.add(f"os.execle(c, '{args}', {{}})")

class LanguageNotImplementedException(Exception):
    pass

class NotGeneratedException(Exception):
    pass

if __name__ == "__main__":
    # we need to monkeypatch the help function to print to stderr
    # as we want nothing but executable code being printed to stdout
    def patched_help_call(self, parser, namespace, values, option_string=None):
        parser.print_help(file=sys.stderr)
        parser.exit()
    
    argparse._HelpAction.__call__ = patched_help_call

    # map of memfd_create syscall numbers for different architectures
    syscall_numbers = {
        **dict.fromkeys(['386'], 356), 
        **dict.fromkeys(['amd64'], 319),
        **dict.fromkeys(['arm'], 385),
        **dict.fromkeys(['arm64', 'riscv64'], 279),
        **dict.fromkeys(['mips'], 4354),
        **dict.fromkeys(['mips64', 'mips64le'], 5314),
        **dict.fromkeys(['ppc', 'ppc64'], 360),
        **dict.fromkeys(['s390x'], 350),
        **dict.fromkeys(['sparc64'], 348),
    }

    parser = argparse.ArgumentParser(
      description="Print code to stdout to execute an ELF without dropping files.")
    parser.add_argument('path', type=argparse.FileType("rb"), 
      help="path to the ELF file")
    arch_or_syscall_group = parser.add_mutually_exclusive_group()
    arch_or_syscall_group.add_argument('-t', '--target-architecture', metavar='ARCH',
      help="target platform for resolving memfd_create (default: resolve symbol via libc)", choices=syscall_numbers)
    arch_or_syscall_group.add_argument('-s', '--syscall', metavar='NUM', type=int, 
      help="syscall number for memfd_create for the target platform")
    parser.add_argument('-a', '--argv',
      help="space-separated arguments (including argv[0]) supplied to execle (default: path to file as argv[0])")
    parser.add_argument('-l', '--language', metavar='LANG',
      help="language for the generated code (default: python)")
    parser.add_argument('-c', '--with-command', action='store_true',
      help="wrap the generated code in a call to an interpreter, for piping directly into ssh")
    parser.add_argument('-p', '--interpreter-path', metavar='PATH',
      help="path to interpreter on target if '-c' is used, otherwise a sane default is used")
    parser.add_argument('-w', '--wrap', metavar='CHARS', type=int,
      help="when base64-encoding the elf, how many characters to wrap to a newline (default: 0)", default=0)
    parser.add_argument('-z', '--compression-level', metavar='LEVEL', type=int,
      help="zlib compression level, 0-9 (default: 9)", choices=range(0, 10), default=9)
    args = parser.parse_args()

    argv = args.argv
    if not argv:
        # argv not specified, so let's just call it with the basename on the host
        argv = os.path.basename(args.path.name)
    
    if args.target_architecture:
        # map to syscall number
        syscall = syscall_numbers.get(args.target_architecture)
    else:
        syscall = args.syscall # None if not specified
    
    if args.interpreter_path and not args.with_command:
        printErr("note: '-p' flag meaningless without '-c'\n")

    # read the elf
    elf = args.path.read()
    args.path.close()
    
    CG = CodeGenerator()

    CG.zCompressionLevel = args.compression_level # defaults to 9
    CG.wrap = args.wrap # defaults to 0, no wrap
    CG.syscall = syscall

    if args.language:
        try:
            CG.set_lang(args.language)
        except LanguageNotImplementedException as e:
            printErr(f"{e.__str__()}\n")
            sys.exit(1)

    out = CG.generate(elf, argv)
    if args.with_command:
        out = CG.with_command(path=args.interpreter_path)
    
    # explicitly write to stdout
    printOut(out)