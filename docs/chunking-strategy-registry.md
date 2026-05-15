# Chunking Strategy Registry (Draft)

Vector Passport intentionally does **not** standardize how chunking is performed. Different documents, modalities, and retrieval tasks need different strategies, and the field is moving too fast for a fixed rule.

But every passport must record `chunk.strategy` as a string. If two teams write `"recursive-character-512-50"` and `"recursive_char_512/50"` for the same idea, the metadata loses most of its value. The point of this registry is to give common strategies stable, versioned names so that passports from different pipelines can be compared and migrated without guesswork.

## Naming convention

```
<family>-<parameter-summary>@<version>
```

- **family**: short identifier of the algorithm family
- **parameter-summary**: a short, deterministic summary of the parameters that affect chunk boundaries
- **version**: semantic version of the strategy implementation. Bump the major version when output is no longer compatible with previous chunks (different boundary rules, different tokenizer, etc.)

Examples:

```
recursive-character-512-50@1.0.0
sentence-window-3@1.0.0
token-cl100k-512-50@1.0.0
markdown-headers@1.1.0
semantic-percentile-95@1.0.0
```

Free-form names are still legal; the registry exists so teams can pick a consistent name when one applies.

## Common strategies

| Name | Family | Description |
| --- | --- | --- |
| `recursive-character-512-50@1.0.0` | Recursive character splitter | LangChain-style recursive split. 512-character target chunks, 50-character overlap. Splits on `\n\n`, `\n`, `. `, ` `. |
| `recursive-character-1024-100@1.0.0` | Recursive character splitter | Same family, larger window. |
| `token-cl100k-512-50@1.0.0` | Token splitter | 512-token chunks with 50-token overlap, using OpenAI `cl100k_base` tokenizer. |
| `token-o200k-1024-100@1.0.0` | Token splitter | 1024-token chunks with 100-token overlap, using OpenAI `o200k_base` tokenizer. |
| `sentence-window-3@1.0.0` | Sentence window | One sentence per chunk, expanded with 3 sentences of context on each side at retrieval time. Common in LlamaIndex. |
| `markdown-headers@1.0.0` | Structural | Splits at Markdown headings. Chunk boundaries follow the document outline. |
| `markdown-headers@1.1.0` | Structural | Same family, also splits on code fences and tables. |
| `html-elements@1.0.0` | Structural | Splits at block-level HTML elements (`<p>`, `<li>`, `<h1>`–`<h6>`, `<table>`, etc.). |
| `pdf-page@1.0.0` | Structural | One chunk per PDF page. Use `chunk.unit = "page"`. |
| `pdf-layout-block@1.0.0` | Structural | One chunk per layout block detected by a PDF parser (paragraph, list, table). |
| `semantic-percentile-95@1.0.0` | Semantic | Splits where consecutive sentence embeddings differ above the 95th percentile of pairwise distances. |
| `fixed-time-30s@1.0.0` | Time-based | 30-second windows for audio or video. Use `chunk.unit = "time"`. |
| `frame-sample-1fps@1.0.0` | Frame-based | One chunk per sampled video frame at 1 frame per second. Use `chunk.unit = "frame"`. |

## Recording strategy parameters

Anything that affects chunk boundaries should be in the name *or* in `chunk.metadata`. If two pipelines using `recursive-character-512-50@1.0.0` would produce different chunks for the same input, the strategy name is too coarse — bump the version or pick a more specific name.

For parameters that don't affect boundaries (e.g., a downstream cleaner, a stopword filter), put them in `chunk.metadata` and leave the strategy name alone.

## Adding a strategy

Open a pull request that:

1. Adds a row to the table above.
2. Includes a short description that uniquely identifies the boundary rules.
3. Picks a version. New entries start at `1.0.0`. Backward-incompatible changes bump the major version.

The registry is intentionally informal in v1.0 of the spec — these names are recommendations, not requirements. The goal is convergence over time, not enforcement.
