# Reader plugins

A reader subclasses `scivalid.readers.base.DatasetReader` and implements:

```python
class ExampleReader(DatasetReader):
    format_name = "example"
    extensions = (".example",)

    def inspect_metadata(self) -> ReaderMetadata:
        ...

    def iterate_chunks(self, required_fields=None):
        yield DataChunk(values=arrays, locations=locations, start=0)
```

`values` maps field names to NumPy arrays. The first axis represents rows;
`locations` maps those rows back to a source line, row, or index. Readers must
raise `ReaderError` for malformed input and must not execute embedded content.

Register a distribution entry point:

```toml
[project.entry-points."scivalid.readers"]
example = "package.module:ExampleReader"
```

The core registry keeps built-ins available if an unrelated third-party entry
point fails to load. Heavy formats should live in optional packages and raise
`OptionalDependencyError` when their dependency is missing.

