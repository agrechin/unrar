# Extraction fixtures

The uuencoded RAR4 and compressed RAR5 archives are from
[libarchive](https://github.com/libarchive/libarchive/tree/caacb791cc9487eacc2a8826875871a77f57bdf0/libarchive/test),
revision `caacb791cc9487eacc2a8826875871a77f57bdf0`. Its license is retained in
`LICENSE.libarchive`.

`manifest.json` pins the decoded archives and extracted contents. Expected
contents come from upstream `test_read_format_rar.c` and
`test_read_format_rar5.c`, independently of the UnRAR binary under test:

- RAR4: both text files contain `test text document\r\n`.
- RAR5: `test.bin` contains 300 little-endian uint32 values, where element
  `k - 1` is `max(0, k*k - 3*k + 1)` for `k` from 1 through 300.

These tests exercise decoding only. They do not create RAR archives.
