# Dossier documentation

Type: GUIDE
Authority: Map of this guide. Behavior lives in [status](status.md).

Dossier is a local-first locker for professional evidence. It turns records you
already have into claim cards you could paste into a CV or letter. Each claim
cites a record. If the record will not carry the sentence, the claim is refused.
You approve a card before it is paste-ready.

Ask-the-corpus — “what did I actually do?” — is `dossier ask`. It answers from
records already in the locker and prints citation URIs. A posting-shaped CV
or letter is `dossier tailor`. What either command includes is in
[status](status.md).

The product page and this guide share one sticky header. Build both with
`make pages-site`.

```{toctree}
:maxdepth: 2
:caption: Start here

install
cli
prove
adapters
```

```{toctree}
:maxdepth: 2
:caption: How it works

architecture
vocab
seekers
zotero-rag-pubs
privacy
```

```{toctree}
:maxdepth: 1
:caption: Product

status
roadmap
prior-art
```
